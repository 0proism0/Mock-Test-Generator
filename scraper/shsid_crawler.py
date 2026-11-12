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
BASE_URL = "https://www.linkedclassroom.com"
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
        """Return {course_id: course_name} for the logged-in user."""
        resp = self.session.get(f"{BASE_URL}/my/", timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        courses = {}

        def _extract(tag):
            href = tag.get("href", "")
            m = re.search(r"/course/view\.php\?id=(\d+)", href)
            if m and tag.get_text(strip=True):
                courses[m.group(1)] = tag.get_text(strip=True)

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
        if not courses:
            resp2 = self.session.get(f"{BASE_URL}/course/index.php?categoryid=0", timeout=TIMEOUT)
            soup2 = BeautifulSoup(resp2.text, "html.parser")
            for box in soup2.find_all("div", class_="coursebox"):
                a = box.find("a", href=True)
                if a:
                    _extract(a)
        return courses

    @staticmethod
    def _parse_activity(act):
        classes = act.get("class", [])
        modtype = next((c.replace("modtype_", "") for c in classes if c.startswith("modtype_")), None)
        title_span = act.find("span", class_="instancename")
        if title_span:
            a = title_span.find("a")
            title = a.get_text(strip=True) if a else title_span.get_text(strip=True)
            url = urljoin(BASE_URL, a["href"]) if a and a.get("href") else None
        else:
            title = act.get("data-title", "").strip()
            url = act.get("data-url")
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


def _safe(name):
    return re.sub(r"[^\w\-. ()\[\]+&]+", "_", str(name)).strip()[:120] or "file"


def crawl(username, password, course_ids, do_download):
    c = SHSIDCrawler()
    print("logging in...")
    c.login(username, password)
    print("logged in.")

    if course_ids:
        ids = [str(x) for x in course_ids]
    else:
        courses = c.get_all_courses()
        ids = list(courses.keys())
        print(f"found {len(ids)} course(s)")

    index = {"courses": []}
    for cid in ids:
        print(f"crawling course {cid} ...")
        data = c.get_course_contents(cid)
        n_files = 0
        if do_download:
            course_dir = OUT_DIR / _safe(data["course_title"])
            for sec in data["sections"]:
                for act in sec.get("activities", []):
                    urls = []
                    if act.get("modtype") == "folder" and act.get("url"):
                        try:
                            urls = c.scrape_folder(act["url"])
                        except Exception as exc:
                            print(f"  ! folder {act.get('title')}: {exc}")
                    elif act.get("url") and urlparse(act["url"]).path.lower().endswith(FILE_EXTS):
                        urls = [{"name": act.get("title") or "file", "url": act["url"]}]
                    for f in urls:
                        name = _safe(f["name"])
                        if not name.lower().endswith(FILE_EXTS):
                            name += ".bin"
                        dest = course_dir / _safe(sec["section_title"]) / name
                        try:
                            c.download(f["url"], dest)
                            act.setdefault("downloaded", []).append(str(dest.relative_to(ROOT)))
                            n_files += 1
                        except Exception as exc:
                            print(f"  ! download {name}: {exc}")
        print(f"  ok: {data['course_title']} ({len(data['sections'])} sections, {n_files} files)")
        index["courses"].append(data)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT_DIR / 'index.json'}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Crawl SHSID LinkedClassroom into raw/shsid/")
    ap.add_argument("--username", "-u", default=os.environ.get("SHSID_USER", ""))
    ap.add_argument("--password", "-p", default=os.environ.get("SHSID_PASS", ""))
    ap.add_argument("--course-ids", nargs="*", type=int, metavar="ID", default=None)
    ap.add_argument("--download", action="store_true", help="also download files (PDFs etc.)")
    args = ap.parse_args(argv)
    if not args.username or not args.password:
        ap.error("credentials required: --username/--password or SHSID_USER/SHSID_PASS")
    crawl(args.username, args.password, args.course_ids, args.download)
    return 0


if __name__ == "__main__":
    sys.exit(main())
