"""SHSID LinkedClassroom crawler — standalone port of OpenSHSID's crawler
(https://github.com/zengyuxiang0921/OpenSHSID, crawler/service.py).

Logs into SHSID's Moodle (LinkedClassroom) with a student account, walks
courses -> tile sections -> activities, and optionally downloads the files
(PDFs etc.) into raw/shsid/. Output lands in raw/shsid/index.json.

This is a scraper helper: it needs third-party packages (requests, bs4),
same ad-hoc policy as the other scraper/ scripts:

    .venv/bin/pip install requests beautifulsoup4

Usage:

    # list everything (no download)
    .venv/bin/python scraper/shsid_crawler.py --username USER --password PASS

    # only some courses, and download the files
    .venv/bin/python scraper/shsid_crawler.py -u USER -p PASS \
        --course-ids 123 456 --download

    # credentials from the environment
    export SHSID_USER=... SHSID_PASS=...
    .venv/bin/python scraper/shsid_crawler.py --download

Downloads go to raw/shsid/<course>/<section>/<file> with an index at
raw/shsid/index.json. Nothing is imported into the app automatically; turn
the PDFs into worksheets via the Worksheet tab, or push them into school
docs for your class.
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "raw" / "shsid"

# Same endpoints as OpenSHSID config.example.json -> crawler
# linkedclassroom.com 301-redirects to learningcan.com (Moodle); use the
# canonical host directly. Course CONTENT is login-gated (view.php redirects
# to the login page); only the course catalog is anonymously visible.
BASE_URL = "https://www.learningcan.com"
LOGIN_URL = f"{BASE_URL}/login/index.php"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
TIMEOUT = 15
FILE_EXTS = (".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
             ".zip", ".png", ".jpg", ".jpeg", ".txt", ".md", ".tex")


class SHSIDCrawler:
    """LinkedClassroom (Moodle) crawler — stateless, raises on failures."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.logged_in = False

    def login(self, username, password):
        resp = self.session.get(LOGIN_URL, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        token_input = soup.find("input", {"name": "logintoken"})
        if token_input is None:
            raise ValueError("no logintoken on login page — page structure changed?")
        login_resp = self.session.post(LOGIN_URL, data={
            "logintoken": token_input.get("value"),
            "username": username,
            "password": password,
            "rememberusername": "1",
            "anchor": "",
        }, timeout=TIMEOUT, allow_redirects=True)
        login_resp.raise_for_status()
        ok = (login_resp.url.rstrip("/") == BASE_URL
              or "/my" in login_resp.url or "dashboard" in login_resp.url)
        if not ok:
            soup2 = BeautifulSoup(login_resp.text, "html.parser")
            err = soup2.find("div", class_="alert-danger")
            raise ValueError(err.get_text(strip=True) if err else "login failed")
        self.logged_in = True
        return True

    def get_all_courses(self):
        """Return {course_id: course_name} for the logged-in user.

        The /my/ page lists enrolled courses inside a JS nav tree
        (<a title="G8MaH" href=".../course/view.php?id=10">), which the
        original soup selectors missed — so scan anchors with a regex first.
        """
        if not self.logged_in:
            return self.get_public_courses()
        resp = self.session.get(f"{BASE_URL}/my/", timeout=TIMEOUT)
        resp.raise_for_status()
        courses = {}
        for m in re.finditer(
                r'<a\b[^>]*?href="[^"]*?/course/view\.php\?id=(\d+)"[^>]*?>(.*?)</a>',
                resp.text, re.S | re.I):
            cid, inner = m.group(1), m.group(2)
            name = re.sub(r"<[^>]+>", "", inner).strip()
            if not name:
                tm = re.search(r'title="([^"]+)"', m.group(0))
                name = (tm.group(1) or "").strip() if tm else ""
            if cid and name:
                courses.setdefault(cid, name)
        if courses:
            return courses
        # legacy page layouts: coursebox tiles / content region
        soup = BeautifulSoup(resp.text, "html.parser")

        def _extract(tag):
            href = tag.get("href", "")
            m = re.search(r"/course/view\.php\?id=(\d+)", href)
            if m and tag.get_text(strip=True):
                courses.setdefault(m.group(1), tag.get_text(strip=True))

        for a in soup.select('li[data-key="mycourses"] a[href]'):
            _extract(a)
        for box in soup.find_all("div", class_="coursebox"):
            a = box.find("a", href=True)
            if a:
                _extract(a)
        region = soup.find(attrs={"data-region": "course-view-content"})
        if region:
            for a in region.find_all("a", href=True):
                _extract(a)
        return courses

    def get_public_courses(self):
        """Anonymous course catalog: parse /course/index.php plus every linked
        category page for view.php?id= links (works without any login)."""
        courses = {}
        seen = set()
        urls = [f"{BASE_URL}/course/index.php"]
        while urls:
            url = urls.pop()
            if url in seen:
                continue
            seen.add(url)
            try:
                resp = self.session.get(url, timeout=TIMEOUT)
                soup = BeautifulSoup(resp.text, "html.parser")
            except Exception:
                continue
            for a in soup.find_all("a", href=True):
                m = re.search(r"/course/view\.php\?id=(\d+)", a["href"])
                if m:
                    name = a.get_text(strip=True)
                    if name:
                        courses.setdefault(m.group(1), name)
                elif "/course/index.php?categoryid=" in a["href"]:
                    cat = urljoin(BASE_URL, a["href"])
                    if cat not in seen:
                        urls.append(cat)
        return courses

    @staticmethod
    def _parse_activity(act):
        classes = act.get("class", [])
        modtype = next((c.replace("modtype_", "") for c in classes if c.startswith("modtype_")), None)
        a = None
        title_span = act.find("span", class_="instancename")
        if title_span:
            a = title_span.find("a")
            title = a.get_text(strip=True) if a else title_span.get_text(strip=True)
        else:
            title = act.get("data-title", "").strip()
        if a is None:
            # Moodle 4.x tiles format: one stretched link on the whole item
            a = act.find("a", class_="aalink") or act.find("a", href=re.compile(r"/mod/"))
        url = urljoin(BASE_URL, a["href"]) if a is not None and a.get("href") else act.get("data-url")
        return {
            "modtype": modtype,
            "cmid": act.get("data-cmid"),
            "title": title,
            "url": url,
            "restricted": bool(act.find("div", class_="availabilityinfo")),
        }

    def get_course_contents(self, course_id):
        """Return {course_id, title, sections:[{title, activities:[...]}]}."""
        course_url = f"{BASE_URL}/course/view.php?id={course_id}"
        resp = self.session.get(course_url, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        h1 = soup.find("h1")
        course_title = h1.get_text(strip=True) if h1 else str(course_id)
        sections = []

        section0 = soup.find("li", {"id": "section-0"})
        if section0:
            acts = section0.find_all("li", class_="activity")
            if acts:
                sections.append({
                    "section_title": "Course home",
                    "activities": [self._parse_activity(a) for a in acts],
                })

        for tile in soup.select("li.tile.tile-clickable"):
            a = tile.find("a", class_="tile-link")
            if not a or not a.get("href"):
                continue
            section_url = urljoin(BASE_URL, a["href"])
            title_elem = tile.find("h3") or tile.find("span", class_="tile-textinner")
            section_title = title_elem.get_text(strip=True) if title_elem else "untitled"
            try:
                sec_resp = self.session.get(section_url, timeout=TIMEOUT)
                sec_soup = BeautifulSoup(sec_resp.text, "html.parser")
                acts = []
                for ul in sec_soup.find_all("ul", class_=lambda c: c and ("section" in c or "img-text" in c)):
                    acts.extend(ul.find_all("li", class_="activity"))
                if not acts:
                    acts = sec_soup.find_all("li", class_="activity")
                if not acts:
                    cc = sec_soup.find("div", class_="course-content")
                    if cc:
                        acts = cc.find_all("li", class_="activity")
                sections.append({
                    "section_title": section_title,
                    "activities": [self._parse_activity(x) for x in acts],
                })
            except Exception as exc:
                sections.append({"section_title": section_title, "activities": [], "error": str(exc)})
            time.sleep(0.5)
        return {"course_id": str(course_id), "course_title": course_title, "sections": sections}

    def scrape_folder(self, folder_url):
        """Return [{name, url}] for all files on a Moodle folder page."""
        resp = self.session.get(folder_url, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        files = []
        for item in soup.select("span.fp-filename-icon"):
            a = item.find("a")
            if not a or not a.get("href"):
                continue
            name_span = a.find("span", class_="fp-filename")
            name = name_span.get_text(strip=True) if name_span else (a.get_text(strip=True) or a.get("title", ""))
            if name:
                files.append({"name": name, "url": a["href"]})
        return files

    def download(self, url, dest: Path):
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self.session.get(url, timeout=60, stream=True) as r:
            r.raise_for_status()
            with dest.open("wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    f.write(chunk)
        return dest

    def download_resource(self, url, dest_dir: Path):
        """Download a Moodle 'resource' activity (/mod/resource/view.php?id=N).

        Follows to the real file; filename comes from Content-Disposition, the
        final URL path, or the forcedownload link on the intermediate page.
        Returns the dest Path, or None when no file could be resolved.
        """
        from urllib.parse import unquote, urlparse
        r = self.session.get(url, timeout=60, allow_redirects=True)
        r.raise_for_status()
        name = _cd_filename(r.headers.get("Content-Disposition", ""))
        if not name:
            base = unquote(urlparse(r.url).path.rsplit("/", 1)[-1])
            if "." in base:
                name = _safe(base)
        if not name and "text/html" in r.headers.get("Content-Type", ""):
            soup = BeautifulSoup(r.text, "html.parser")
            a = (soup.find("a", href=re.compile(r"forcedownload=1"))
                 or soup.find("a", href=re.compile(r"/pluginfile\.php/")))
            if a:
                return self.download_resource(urljoin(BASE_URL, a["href"]), dest_dir)
            return None
        if name.endswith(".php"):
            # landed on an intermediate Moodle page (viewer/embed) — dig out
            # the real file link instead of saving HTML as 'view.php'
            soup = BeautifulSoup(r.text, "html.parser")
            node = (soup.find("a", href=re.compile(r"forcedownload=1"))
                    or soup.find("a", href=re.compile(r"/pluginfile\.php/"))
                    or soup.find("embed", src=re.compile(r"/pluginfile\.php/"))
                    or soup.find("iframe", src=re.compile(r"/pluginfile\.php/")))
            target = None
            if node is not None:
                target = node.get("href") or node.get("src")
            if target:
                return self.download_resource(urljoin(BASE_URL, target), dest_dir)
            return None
        if not name:
            return None
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / name
        with dest.open("wb") as f:
            f.write(r.content)
        return dest


def _safe(name):
    name = re.sub(r"[^\w\-. ()\[\]+&]+", "_", str(name)).strip()[:120]
    return name or "file"


def _cd_filename(cd):
    """Decode a Content-Disposition header into a safe filename.

    Handles filename*=UTF-8''<pct-encoded> and plain filename="..."; repairs
    UTF-8 bytes that servers send raw (requests exposes headers as latin-1).
    """
    from urllib.parse import unquote
    m = re.search(r"filename\*\s*=\s*(?:UTF-8'')?\"?([^\";]+)", cd, re.I)
    if m:
        raw = unquote(m.group(1).strip().strip('"'))
    else:
        m = re.search(r"filename\s*=\s*\"?([^\";]+)", cd, re.I)
        if not m:
            return ""
        raw = m.group(1).strip().strip('"')
    try:
        raw = raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return _safe(raw)


def crawl(username, password, course_ids, do_download, force=False):
    c = SHSIDCrawler()
    if username:
        print("logging in...")
        c.login(username, password)
        print("logged in.")

    if course_ids:
        ids = [str(x) for x in course_ids]
        names = {}
    else:
        courses = c.get_all_courses()
        ids = list(courses.keys())
        names = courses
        print(f"found {len(ids)} course(s)")

    index = {"courses": []}
    # previous cycle's files, for incremental skips: (course, section, act) -> [rels]
    prev = {}
    pidx = OUT_DIR / "index.json"
    if pidx.exists() and not force:
        try:
            for pc in json.loads(pidx.read_text(encoding="utf-8")).get("courses", []):
                for ps in pc.get("sections", []):
                    for pa in ps.get("activities", []):
                        key = (pc.get("course_title"), ps.get("section_title"),
                               pa.get("url") or pa.get("title"))
                        prev[key] = [r for r in pa.get("downloaded", [])
                                     if (ROOT / r).exists() and (ROOT / r).stat().st_size > 0]
        except Exception:
            prev = {}
    for cid in ids:
        print(f"crawling course {cid} ...")
        data = c.get_course_contents(cid)
        # anonymous hits redirect to the login page and lose the real title
        if not data["sections"] and names.get(cid):
            data["course_title"] = names[cid]
        n_files = 0
        if do_download:
            course_dir = OUT_DIR / _safe(data["course_title"])
            for sec in data["sections"]:
                for act in sec.get("activities", []):
                    if act.get("modtype") == "folder" and act.get("url"):
                        try:
                            files = c.scrape_folder(act["url"])
                        except Exception as exc:
                            print(f"  ! folder {act.get('title')}: {exc}")
                            files = []
                        for f in files:
                            name = _safe(f["name"])
                            if not name.lower().endswith(FILE_EXTS):
                                name += ".bin"
                            dest = course_dir / _safe(sec["section_title"]) / name
                            rel = str(dest.relative_to(ROOT))
                            # incremental: keep finished downloads across cycles
                            if not force and dest.exists() and dest.stat().st_size > 0:
                                act.setdefault("downloaded", []).append(rel)
                                n_files += 1
                                continue
                            try:
                                c.download(f["url"], dest)
                                act.setdefault("downloaded", []).append(rel)
                                n_files += 1
                            except Exception as exc:
                                print(f"  ! download {name}: {exc}")
                    elif act.get("url") and urlparse(act["url"]).path.lower().endswith(FILE_EXTS):
                        name = _safe(act.get("title") or "file")
                        if not name.lower().endswith(FILE_EXTS):
                            name += ".bin"
                        dest = course_dir / _safe(sec["section_title"]) / name
                        rel = str(dest.relative_to(ROOT))
                        if not force and dest.exists() and dest.stat().st_size > 0:
                            act.setdefault("downloaded", []).append(rel)
                            n_files += 1
                            continue
                        try:
                            c.download(act["url"], dest)
                            act.setdefault("downloaded", []).append(rel)
                            n_files += 1
                        except Exception as exc:
                            print(f"  ! download {name}: {exc}")
                    elif act.get("modtype") in ("resource", "file") and act.get("url"):
                        key = (data["course_title"], sec["section_title"], act.get("url") or act.get("title"))
                        if prev.get(key):
                            act.setdefault("downloaded", []).extend(prev[key])
                            n_files += len(prev[key])
                            continue
                        try:
                            dest = c.download_resource(act["url"], course_dir / _safe(sec["section_title"]))
                            if dest is not None:
                                act.setdefault("downloaded", []).append(str(dest.relative_to(ROOT)))
                                n_files += 1
                        except Exception as exc:
                            print(f"  ! resource {act.get('title')}: {exc}")
        print(f"  ok: {data['course_title']} ({len(data['sections'])} sections, {n_files} files)")
        index["courses"].append(data)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    # garbage-collect: drop crawled files no longer referenced by the index
    # (e.g. renamed downloads from earlier cycles)
    keep = set()
    for course in index.get("courses", []):
        for sec in course.get("sections", []):
            for act in sec.get("activities", []):
                for rel in act.get("downloaded", []):
                    p = (ROOT / rel).resolve()
                    try:
                        keep.add(str(p.relative_to(OUT_DIR.resolve())))
                    except ValueError:
                        pass
    for f in OUT_DIR.rglob("*"):
        if f.is_file() and f.name not in ("index.json", "crawler.log"):
            if str(f.relative_to(OUT_DIR)) not in keep:
                try:
                    f.unlink()
                except OSError:
                    pass
    print(f"wrote {OUT_DIR / 'index.json'}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Crawl SHSID LinkedClassroom into raw/shsid/")
    ap.add_argument("--username", "-u", default=os.environ.get("SHSID_USER", ""))
    ap.add_argument("--password", "-p", default=os.environ.get("SHSID_PASS", ""))
    ap.add_argument("--course-ids", nargs="*", type=int, metavar="ID", default=None)
    ap.add_argument("--download", action="store_true", help="also download files (PDFs etc.)")
    ap.add_argument("--force", action="store_true", help="re-download files that already exist")
    ap.add_argument("--watch", action="store_true",
                    help="keep running: re-crawl everything every --interval minutes")
    ap.add_argument("--interval", type=int, default=30, help="minutes between watch cycles")
    args = ap.parse_args(argv)
    if not args.username or not args.password:
        if args.download:
            ap.error("--download needs credentials: course files are login-gated "
                     "(--username/--password or SHSID_USER/SHSID_PASS)")
        print("no credentials: anonymous mode — public course catalog only")
        crawl("", "", args.course_ids, False, args.force)
        return 0
    if args.watch:
        print(f"watch mode: crawling every {args.interval} min, Ctrl+C to stop")
        while True:
            try:
                crawl(args.username, args.password, args.course_ids, args.download, args.force)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                print(f"cycle failed: {exc}")
            print(f"sleeping {args.interval} min ...")
            time.sleep(max(1, args.interval) * 60)
    crawl(args.username, args.password, args.course_ids, args.download, args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
