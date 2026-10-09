#!/usr/bin/env python3
"""Extract ODT body text (skip TOC; footnote-safe).
Usage: python3 odt_text.py in.odt [out.txt] [--keep-blanks]

out.txt 省略时写 stdout（提示信息一律走 stderr，不污染管道）。

--keep-blanks: 空段落输出一个空行。默认会丢掉空段落，导致 diff 里
               出现"凭空少了几行"的假象（渲染出来其实没变）。
"""
import sys, os, argparse
from paths import add_pylib, work
add_pylib()


def extract(path, out, keep_blanks=False):
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
            elif keep_blanks and el.get_attribute("text:style-name"):
                lines.append("")
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
    if out:
        parent = os.path.dirname(out)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return lines, n_img


def main(argv=None):
    ap = argparse.ArgumentParser(description="提取 odt 正文为纯文本")
    ap.add_argument("odt")
    ap.add_argument("out", nargs="?", help="输出文件；省略则写 stdout")
    ap.add_argument("--keep-blanks", action="store_true", help="空段落输出空行")
    a = ap.parse_args(argv)
    lines, _n_img = extract(a.odt, a.out, keep_blanks=a.keep_blanks)
    if a.out:
        print("%s -> %s" % (a.odt, a.out), file=sys.stderr)
    else:
        sys.stdout.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
