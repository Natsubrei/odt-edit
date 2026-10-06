#!/usr/bin/env python3
"""Extract ODT body text (skip TOC; footnote-safe).
Usage: python3 odt_text.py in.odt out.txt
"""
import sys, os
from paths import add_pylib, work
add_pylib()


def extract(path, out):
    from odfdo import Document
    doc = Document(path)
    body = doc.body

    def safe(el):
        try:
            return el.text_recursive.strip()
        except Exception:
            return ""

    lines = []
    n_img = 0

    def dump_list(lst, depth):
        prefix = "  " * depth + "- "
        for item in lst.children:
            if item.tag != "text:list-item":
                continue
            for sub in item.children:
                if sub.tag in ("text:p", "text:h"):
                    t = safe(sub)
                    if t:
                        lines.append(prefix + t)
                elif sub.tag == "text:list":
                    dump_list(sub, depth + 1)

    for el in body.children:
        tag = el.tag
        if tag == "text:table-of-content":
            continue
        if tag == "text:h":
            lvl = el.get_attribute("text:outline-level") or 1
            t = safe(el)
            if t:
                lines.append("#" * int(lvl) + " " + t)
        elif tag == "text:p":
            t = safe(el)
            if t:
                lines.append(t)
        elif tag == "text:list":
            dump_list(el, 0)
        elif tag == "table:table":
            lines.append("[table]")
            for row in el.get_elements("table:table-row"):
                cells = [
                    c.text_recursive.strip().replace("\n", " ")
                    for c in row.get_elements("table:table-cell")
                ]
                lines.append(" | ".join(cells))
        try:
            n_img += len(el.xpath(".//draw:image"))
        except Exception:
            pass
    parent = os.path.dirname(out)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return lines, n_img


if __name__ == "__main__":
    extract(sys.argv[1], sys.argv[2])
    print(sys.argv[1], "->", sys.argv[2])
