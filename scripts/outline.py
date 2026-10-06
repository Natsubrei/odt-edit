#!/usr/bin/env python3
"""打印 ODT 正文大纲：标题、列表嵌套、样式名。
用法: python3 outline.py 文件.odt
动手改字之前先跑，用来定位该改哪一块、列表现在是几级。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import add_pylib
add_pylib()

TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
A_STYLE = "{%s}style-name" % TEXT


def qn(el):
    tag = el.tag
    return tag.split("}")[-1] if "}" in tag else tag


def style_of(el):
    return el.get(A_STYLE) or ""


def first_text(el, n=60):
    t = "".join(el.itertext()).replace("\n", " ").strip()
    return t if len(t) <= n else t[: n - 1] + "…"


def dump_list(lst, indent, show_head=True):
    if show_head:
        print(f"{indent}list {style_of(lst) or '-'}")
    n = 0
    for item in lst:
        if qn(item) != "list-item":
            continue
        n += 1
        ps = [c for c in item if qn(c) == "p"]
        nested = [c for c in item if qn(c) == "list"]
        label = first_text(ps[0], 70) if ps else ""
        extra = f"  (+{len(ps)-1}p)" if len(ps) > 1 else ""
        print(f"{indent}  {n}. {label}{extra}")
        for sub in nested:
            dump_list(sub, indent + "    ", show_head=True)


def main():
    if len(sys.argv) < 2:
        print("用法: python3 outline.py 文件.odt", file=sys.stderr)
        sys.exit(2)
    from odfdo import Document

    doc = Document(sys.argv[1])
    root = doc.body._xml_element
    print(f"# {sys.argv[1]}")
    for i, el in enumerate(list(root)):
        tag = qn(el)
        st = style_of(el)
        if tag == "h":
            print(f"{i:4} h    {st:16} {first_text(el, 80)}")
        elif tag == "p":
            t = first_text(el, 80)
            if t:
                print(f"{i:4} p    {st:16} {t}")
        elif tag == "list":
            print(f"{i:4} list {st:16}")
            dump_list(el, "      ", show_head=False)
        elif tag in ("table", "table-of-content"):
            print(f"{i:4} {tag:5} {st:16} {first_text(el, 40)}")
        elif tag not in ("sequence-decls",):
            t = first_text(el, 40)
            if t:
                print(f"{i:4} {tag:5} {st:16} {t}")


if __name__ == "__main__":
    main()
