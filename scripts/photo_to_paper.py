"""Turn a photo (or scan) of a worksheet into a paper v1.1 JSON file.

    python scripts/photo_to_paper.py page.png --out out/paper.json --check
    python scripts/photo_to_paper.py page.png --no-llm --dump-blocks

Pipeline: OCR (remote Unlimited-OCR-2) -> blocks -> a small chat model structures the
blocks into questions -> figures are cropped out of the page -> paper v1.1 + PNG files.
Standard library only; PNG/JPEG input.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "scripts"))

import photo_import  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Photo -> paper v1.1 (OCR + LLM structuring)")
    ap.add_argument("image", help="page image (.png or .jpg)")
    ap.add_argument("--out", help="paper JSON path (default: <image>.paper.json)")
    ap.add_argument("--figures-dir", default="figures",
                    help="figure sub-directory stored in the JSON (default: figures)")
    ap.add_argument("--paper-id", default=None,
                    help="paper id (default: the output file stem)")
    ap.add_argument("--title", default=None, help="override the detected title")
    ap.add_argument("--base-url", default=None, help="OCR server base url")
    ap.add_argument("--model", default=None, help="OCR model id")
    ap.add_argument("--no-llm", action="store_true",
                    help="skip the chat model and use the regex structurer")
    ap.add_argument("--llm-base", default=None, help="chat model base url")
    ap.add_argument("--llm-key", default=None, help="chat model api key")
    ap.add_argument("--llm-model", default=None, help="chat model id")
    ap.add_argument("--no-figures", action="store_true", help="do not crop figures")
    ap.add_argument("--dump-blocks", action="store_true", help="print the OCR blocks")
    ap.add_argument("--dump-ocr", action="store_true", help="print the raw OCR text")
    ap.add_argument("--check", action="store_true", help="validate the result")
    args = ap.parse_args(argv)

    path = Path(args.image)
    if not path.is_file():
        print("no such file: %s" % path)
        return 2
    data = path.read_bytes()
    width, height = photo_import.image_size(data)
    print("page %s  %dx%d  %.1f KB" % (path.name, width, height, len(data) / 1024.0))

    raw = photo_import.ocr_image(data, base_url=args.base_url, model=args.model)
    if args.dump_ocr:
        print(raw)
    blocks = photo_import.parse_ocr_text(raw)
    print("blocks: %d (types: %s)" % (len(blocks), _type_summary(blocks)))
    if args.dump_blocks:
        for i, b in enumerate(blocks):
            print("  [%d] %s %s %s" % (i, b["kind"], b["bbox"], b["text"][:70]))

    title, questions, source = "", [], "regex"
    if not args.no_llm:
        try:
            title, questions = photo_import.structure_with_llm(
                blocks, base_url=args.llm_base, api_key=args.llm_key, model=args.llm_model)
            source = "llm:" + (args.llm_model or photo_import.STRUCT_MODEL)
        except ValueError as exc:
            print("  llm structuring failed (%s) - falling back to regex" % exc)
    if not questions:
        title, questions = photo_import.structure_blocks(blocks)
    filled = photo_import.apply_answer_key(blocks, questions)
    if filled:
        print("  answer key filled %d missing answer(s)" % filled)
    missing = [q["n"] for q in questions if not q.get("answer")]
    if missing:
        print("  warning: no answer for question(s) %s" % ", ".join(map(str, missing)))
    print("structurer: %s | questions: %d | title: %r" % (source, len(questions), title))
    if not questions:
        print("no questions detected - the page needs numbered items like '1.'")
        return 1

    files, figures = {}, {}
    if not args.no_figures:
        for q in questions:
            if not q["figures"]:
                continue
            box = photo_import.figure_box(q["figures"][0], width, height)
            if not box:
                continue
            name = "q%02d.png" % q["n"]
            try:
                files[name] = photo_import.crop_png(data, box)
            except ValueError as exc:
                print("  figure q%d skipped: %s" % (q["n"], exc))
                continue
            figures[q["n"]] = {
                "src": "%s/%s" % (args.figures_dir.rstrip("/"), name),
                "width": box[2] - box[0],
                "height": box[3] - box[1],
                "sha256": hashlib.sha256(files[name]).hexdigest(),
            }
            print("  figure q%d box=%s %dx%d" % (q["n"], box, box[2] - box[0], box[3] - box[1]))

    out = Path(args.out) if args.out else path.with_suffix(".paper.json")
    paper_id = args.paper_id or out.stem
    paper = photo_import.build_paper(
        args.title or title, questions, paper_id=paper_id,
        page_ref=path.name, figures=figures,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(paper, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote %s (%d questions, %d figures)" % (out, len(paper["questions"]), len(files)))

    if files:
        fig_dir = out.parent / args.figures_dir
        fig_dir.mkdir(parents=True, exist_ok=True)
        for name, blob in files.items():
            (fig_dir / name).write_bytes(blob)
        print("wrote %d figure(s) to %s" % (len(files), fig_dir))

    if args.check:
        import validate_paper
        problems = validate_paper.validate(paper, out)
        print("validate: %d error(s), %d warning(s)" % (problems.errors, problems.warnings))
        for lvl, code, msg in problems.items:
            print("  %s [%s] %s" % (lvl, code, msg))
        return 1 if problems.errors else 0
    return 0


def _type_summary(blocks):
    counts = {}
    for b in blocks:
        counts[b["kind"]] = counts.get(b["kind"], 0) + 1
    return ", ".join("%s=%d" % kv for kv in sorted(counts.items()))


if __name__ == "__main__":
    raise SystemExit(main())
