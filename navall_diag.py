"""navall_diag.py -- shows why NAVAll.txt parsing found no open-ended Direct-Growth schemes.
    python navall_diag.py [path-to-NAVAll.txt]      (default: data/NAVAll.txt, the copy live_check cached)
Prints the first lines, the lines the category-header pattern matches, and sample scheme names."""
import os, sys
import mf_holdings_screener as mfs
import config

path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(config.DATA_DIR, "NAVAll.txt")
text = open(path, encoding="utf-8", errors="replace").read()
lines = [l.strip() for l in text.splitlines() if l.strip()]
print(f"{len(lines)} non-empty lines. First 8:")
for l in lines[:8]:
    print("   ", repr(l[:140]))
heads = [l for l in lines if ";" not in l and mfs._HEAD_RE.match(l)]
print(f"\\nLines matching the category-header pattern: {len(heads)}")
for l in heads[:5]:
    print("   ", repr(l))
guess = [l for l in lines if ";" not in l and "(" in l and ")" in l]
print(f"\\nOther lines with brackets and no ';' (possible headers): {len(guess)}")
for l in guess[:8]:
    print("   ", repr(l))
recs = mfs.parse_navall(text)
print(f"\\nParsed {len(recs)} schemes; open-ended {sum(r['open_ended'] for r in recs)}; "
      f"Direct-Growth names {sum(mfs.is_direct_growth(r['name']) for r in recs)}")
print("Sample scheme rows:")
for r in recs[:5] + recs[len(recs)//2:len(recs)//2+3]:
    print("   ", r["code"], repr(r["name"][:80]), "|", repr(r["category"]), "| open_ended", r["open_ended"])
