#!/usr/bin/env python3
"""ODT checks. Always: zip + mimetype.
Optional: --require-toc --require-chapter-seq --forbid-nbsp --forbidden a,b
Usage: python3 check_odt.py file.odt [flags]
Exit 0=pass 1=fail.
"""
import sys, os, re, zipfile, argparse
from paths import add_pylib, work
add_pylib()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--forbidden", default="", help="comma-separated substrings")
    ap.add_argument("--require-toc", action="store_true")
    ap.add_argument("--require-chapter-seq", action="store_true")
    ap.add_argument("--forbid-nbsp", action="store_true")
    args = ap.parse_args()
    path = args.path
    forbidden = [w for w in args.forbidden.split(",") if w]

    problems = []

    z = zipfile.ZipFile(path)
    if z.testzip() is not None:
        problems.append("zip CRC failed")
    names = z.namelist()
    if names[0] != "mimetype" or z.getinfo("mimetype").compress_type != 0:
        problems.append("mimetype is not the first uncompressed zip entry (ODF)")

    from odfdo import Document
    from odt_text import extract
    doc = Document(path)
    body = doc.body
    os.makedirs(work(), exist_ok=True)
    full_lines, _ = extract(path, os.path.join(work(), "_check_full.txt"))
    full = "\n".join(full_lines)

    def safe(e):
        try:
            return e.text_recursive.strip()
        except Exception:
            return ""

    hs = [e for e in body.children if e.tag == "text:h"]
    tops = [safe(e) for e in hs if e.get_attribute("text:outline-level") == "1"]
    nums = [t.split(".")[0] for t in tops if re.match(r"^\d+\.", t)]
    seq_ok = nums == [str(i) for i in range(1, len(nums) + 1)]
    n_tbl = len([e for e in body.children if e.tag == "table:table"])
    n_img = sum(len(e.xpath(".//draw:image")) for e in body.children)
    n_ann = len(body.xpath("//office:annotation"))
    print(
        f"structure: headings {len(hs)} | top {len(tops)} | tables {n_tbl} | images {n_img} | notes {n_ann}"
    )
    if not seq_ok:
        msg = f"chapter numbers not 1..n: {nums}"
        if args.require_chapter_seq:
            problems.append(msg)
        else:
            print("note:", msg)

    hits = [w for w in forbidden if w in full]
    if hits:
        problems.append(f"forbidden text: {hits}")

    n_nbsp = 0

    def walk(el):
        nonlocal n_nbsp
        if el.tag in ("text:table-of-content",):
            return
        try:
            n_nbsp += el.text_recursive.count("\u00a0")
        except Exception:
            pass
        for ch in list(getattr(el, "children", []) or []):
            walk(ch)

    for e in body.children:
        walk(e)
    if n_nbsp:
        msg = f"NBSP count {n_nbsp}"
        if args.forbid_nbsp:
            problems.append(msg)
        else:
            print("note:", msg)

    dups = []
    for line in full.split("\n"):
        collapsed = re.sub(r"[ \u00a0]+", " ", line)
        m = re.search(r"(.{6,}?)\1", collapsed)
        if m:
            dups.append(collapsed[:80])
    if dups:
        print(f"adjacent-repeat hints {len(dups)} (inspect; may be genuine):")
        for x in dups[:8]:
            print("  -", x)

    toc = next((e for e in body.children if e.tag == "text:table-of-content"), None)
    if toc is None:
        msg = "no TOC field"
        if args.require_toc:
            problems.append(msg)
        else:
            print("note:", msg)
    else:
        missing = []
        n_entries = 0
        for p in toc.get_elements("text:index-body/text:p"):
            t = safe(p)
            if not t:
                continue
            t0 = t.strip()
            m = re.match(r"^\[(.*)\]\([^)]*\)$", t0)
            inner = m.group(1) if m else t0
            title = re.split(r"\t", inner)[0].strip()
            title = re.sub(r"\s*\d+$", "", title).strip()
            if not title or title.startswith("目录") or title.lower().startswith("contents"):
                continue
            n_entries += 1
            core = re.sub(r"^\d+(\.\d+)*\.?\s*", "", title)
            if core and core not in full and title not in full:
                missing.append(title)
        print(f"TOC entries {n_entries}")
        if missing:
            msg = f"TOC titles not in body: {missing[:6]}"
            if args.require_toc:
                problems.append(msg)
            else:
                print("note:", msg)

    print("meta title:", doc.meta.get_title())
    if problems:
        print("\nFAIL")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
