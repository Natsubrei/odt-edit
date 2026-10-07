#!/usr/bin/env python3
"""两个 ODT 的差异报告：正文 diff +（可选）样式 diff。

用法:
  python3 diff_odt.py 旧.odt 新.odt 输出.diff              # 只比正文
  python3 diff_odt.py 旧.odt 新.odt 输出.diff --styles     # 正文 + 样式
  python3 diff_odt.py 旧.odt 新.odt 输出.diff --styles --no-blanks

为什么要 --styles：只改样式（字号、行高、底色、颜色、字体继承）的版本，
正文 diff 会是 0 hunk，看起来"没改动"。样式 diff 才看得出改了什么。

空行：默认保留空段落（输出空行），否则 diff 会显示"凭空少了几行"的假象。
"""
import argparse
import difflib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import add_pylib, work  # noqa: E402

add_pylib()

from odt_text import extract          # noqa: E402
import odt_styles                     # noqa: E402


def text_lines(odt, keep_blanks, tmp):
    path = os.path.join(tmp, "diff-%s.txt" % os.path.basename(odt))
    extract(odt, path, keep_blanks=keep_blanks)
    return open(path, encoding="utf-8").read().splitlines(keepends=True), path


def style_lines(odt):
    a = odt_styles.analyse(odt)
    out = []
    for fam, key, label in (("paragraph", "paragraphs", "段落"),
                            ("text", "texts", "文字")):
        miss = a["missing"][fam]
        if miss:
            out.append("!! 引用了但未定义的%s样式: %s\n" % (label, " ".join(miss)))
    for fam, key, label in (("paragraph", "paragraphs", "段落"),
                            ("text", "texts", "文字")):
        out.append("== %s样式（按实际生效的属性分组）==\n" % label)
        for line in odt_styles.group_rows(a[key], fam):
            out.append(line + "\n")
        out.append("\n")
    return out


def main():
    ap = argparse.ArgumentParser(description="ODT 差异报告")
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("out")
    ap.add_argument("--styles", action="store_true", help="附加样式级 diff")
    ap.add_argument("--no-blanks", action="store_true", help="丢空段落的正文提取")
    args = ap.parse_args()

    tmp = work()
    os.makedirs(tmp, exist_ok=True)
    keep = not args.no_blanks

    a, _ = text_lines(args.old, keep, tmp)
    b, _ = text_lines(args.new, keep, tmp)
    d = list(difflib.unified_diff(
        a, b,
        fromfile="%s (body)" % os.path.basename(args.old),
        tofile="%s (body)" % os.path.basename(args.new),
        n=2))
    hunk_text = "".join(d)

    hunk_style = ""
    if args.styles:
        sa, sb = style_lines(args.old), style_lines(args.new)
        hunk_style = "".join(difflib.unified_diff(
            sa, sb,
            fromfile="%s (styles)" % os.path.basename(args.old),
            tofile="%s (styles)" % os.path.basename(args.new),
            n=1))

    parent = os.path.dirname(args.out)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(hunk_text)
        if args.styles:
            if hunk_text:
                f.write("\n\n")
            if not hunk_style.strip():
                f.write("（样式无差异）\n")
            f.write(hunk_style)

    def stat(s):
        return (sum(1 for l in s.splitlines() if l.startswith("@@")),
                sum(1 for l in s.splitlines()
                    if l.startswith("+") and not l.startswith("+++")),
                sum(1 for l in s.splitlines()
                    if l.startswith("-") and not l.startswith("---")))

    h, p, m = stat(hunk_text)
    msg = "%s: 正文 %d hunks, +%d/-%d" % (args.out, h, p, m)
    if args.styles:
        sh, sp, sm = stat(hunk_style)
        msg += " | 样式 %d hunks, +%d/-%d" % (sh, sp, sm)
    print(msg)


if __name__ == "__main__":
    main()
