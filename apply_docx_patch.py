#!/usr/bin/env python3
"""
apply_docx_patch.py  -  run once, in the folder that holds check_fund.py:

    python apply_docx_patch.py

Makes check_fund.py write a Word (.docx) report instead of Markdown (default),
keeps Markdown available with  --format md , and updates test_check_fund.py,
requirements.txt and README.md. Needs report_docx.py in the same folder.
Safe to re-run: files already patched are left alone. Originals are kept as *.bak.
"""
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

CHECK_FUND = [
    ("import report_md\n", "import report_docx\nimport report_md\n"),
    ('    ap.add_argument("--no-file", action="store_true", help="print the report only; write no file")\n',
     '    ap.add_argument("--no-file", action="store_true", help="print the report only; write no file")\n'
     '    ap.add_argument("--format", choices=["docx", "md"], default="docx",\n'
     '                    help="report file format (default: docx; md = Markdown text)")\n'),
    ('''    if not args.no_file:
        try:
            os.makedirs(args.output_dir, exist_ok=True)
            path = os.path.join(args.output_dir, f"fund_check_{rec['code']}.md")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(report)
            print(f"\\nReport written to {os.path.abspath(path)}", file=sys.stderr)
        except OSError as exc:
            print(f"WARNING: could not write the report file ({exc})", file=sys.stderr)
''',
     '''    if not args.no_file:
        path = os.path.join(args.output_dir, f"fund_check_{rec['code']}.{args.format}")
        try:
            os.makedirs(args.output_dir, exist_ok=True)
            if args.format == "docx":
                report_docx.markdown_to_docx(report, path, title=f"Fund check: {rec['name']}")
            else:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(report)
            print(f"\\nReport written to {os.path.abspath(path)}", file=sys.stderr)
        except report_docx.DocxUnavailable as exc:
            print(f"WARNING: no report file written. {exc}  (or use --format md)", file=sys.stderr)
        except OSError as exc:
            print(f"WARNING: could not write the report file ({exc})", file=sys.stderr)
'''),
]

TEST = [
    ('check("CLI: report file written", os.path.exists(os.path.join(d, "o", "fund_check_200.md")))\n',
     '''docx_path = os.path.join(d, "o", "fund_check_200.docx")
check("CLI: report file written (.docx by default)", os.path.exists(docx_path))
check("CLI: no .md file by default", not os.path.exists(os.path.join(d, "o", "fund_check_200.md")))
try:
    import docx as _docx
except ImportError:
    print("SKIP docx content checks (python-docx not installed)")
else:
    _doc = _docx.Document(docx_path)
    _text = "\\n".join(p.text for p in _doc.paragraphs)
    check("docx: title and screen result present", "Fund check: Zeta Small Cap" in _text and "Screen result" in _text)
    check("docx: metrics table present", len(_doc.tables) >= 1 and _doc.tables[0].cell(0, 0).text == "Metric")
    check("docx: no raw markdown markers", "**" not in _text)
rc, out, err, d = cli("Zeta Small Cap", "--format", "md")
check("CLI: --format md still writes Markdown", rc == 0 and os.path.exists(os.path.join(d, "o", "fund_check_200.md")))
'''),
]


def patch(name, pairs):
    path = os.path.join(HERE, name)
    if not os.path.exists(path):
        print(f"SKIP  {name}: not found")
        return True
    with open(path, encoding="utf-8", newline="") as fh:
        text = fh.read()
    crlf = "\r\n" in text
    work = text.replace("\r\n", "\n")
    changed = False
    for old, new in pairs:
        if new in work:
            continue
        if work.count(old) != 1:
            print(f"FAIL  {name}: expected text not found exactly once (file differs from the one patched):\n"
                  f"      {old.strip().splitlines()[0][:90]}")
            return False
        work = work.replace(old, new)
        changed = True
    if changed:
        shutil.copyfile(path, path + ".bak")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(work.replace("\n", "\r\n") if crlf else work)
        print(f"OK    {name} patched (backup: {name}.bak)")
    else:
        print(f"OK    {name} already patched")
    return True


def patch_requirements():
    path = os.path.join(HERE, "requirements.txt")
    if not os.path.exists(path):
        print("SKIP  requirements.txt: not found")
        return
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if re.search(r"^python-docx", text, re.M | re.I):
        print("OK    requirements.txt already lists python-docx")
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(("" if text.endswith("\n") or not text else "\n") + "python-docx\n")
    print("OK    requirements.txt: added python-docx")


def patch_readme():
    path = os.path.join(HERE, "README.md")
    if not os.path.exists(path):
        print("SKIP  README.md: not found")
        return
    with open(path, encoding="utf-8", newline="") as fh:
        text = fh.read()
    new = text.replace("fund_check_<code>.md", "fund_check_<code>.docx")
    if new != text:
        shutil.copyfile(path, path + ".bak")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(new)
        print("OK    README.md: report file name now .docx (also add a line: --format md writes Markdown instead)")
    else:
        print("OK    README.md: nothing to change")


def main():
    if not os.path.exists(os.path.join(HERE, "report_docx.py")):
        print("ERROR: put report_docx.py in this folder first")
        return 2
    ok = patch("check_fund.py", CHECK_FUND) and patch("test_check_fund.py", TEST)
    patch_requirements()
    patch_readme()
    if ok:
        print("\nNext:  pip install python-docx   then   python test_check_fund.py")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
