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
from paths import require_deps, work  # noqa: E402

require_deps()

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


def style_counts(odt):
    """{(族, 属性单元格, 样式名, 单位): 计数}。属性变了名字或键就变。"""
    a = odt_styles.analyse(odt)
    out = {}
    for fam, key in (("paragraph", "paragraphs"), ("text", "texts")):
        keys = [k for k, _ in (odt_styles.PARA_KEYS if fam == "paragraph"
                               else odt_styles.TEXT_KEYS)]
        unit = "段" if fam == "paragraph" else "处"
        for r in a[key]:
            p = r["actual"]
            cells = " ".join("%s=%s" % (odt_styles.DISPLAY[k], p.get(k))
                             for k in keys if p.get(k) is not None)
            out[(fam, cells, str(r["name"]), unit)] = r["count"]
    return out


def change_kind(old, new):
    """把样式变化拆成“属性变了”与“只是数量变了”两类。

    为什么：往块里加删行时属性一个没改，只是计数变了（TBMFile 536→533 段），
    而分组行里带着计数，旧输出会报成样式 hunk +2/-2，看着像样式被改。
    """
    o, n = style_counts(old), style_counts(new)
    only = [k for k in o if k not in n] + [k for k in n if k not in o]
    cnt = [(k, o[k], n[k]) for k in o if k in n and o[k] != n[k]]
    parts = ["样式属性变化 %d 项" % len(only)]
    if only:
        parts.append("（%s）" % "；".join(k[2] for k in only[:6]))
    if cnt:
        d = "；".join("%s %s %d→%d" % (k[2], k[3], a, b) for k, a, b in cnt[:6])
        more = "；另有 %d 项" % (len(cnt) - 6) if len(cnt) > 6 else ""
        parts.append("仅计数变化 %d 项（%s%s）" % (len(cnt), d, more))
    else:
        parts.append("仅计数变化 0 项")
    return "；".join(parts), len(only), len(cnt)


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
    kind = ""
    kn = kc = 0
    if args.styles:
        sa, sb = style_lines(args.old), style_lines(args.new)
        hunk_style = "".join(difflib.unified_diff(
            sa, sb,
            fromfile="%s (styles)" % os.path.basename(args.old),
            tofile="%s (styles)" % os.path.basename(args.new),
            n=1))
        kind, kn, kc = change_kind(args.old, args.new)

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
            f.write("\n== 变更性质 ==\n%s\n" % kind)

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
        msg += " | 样式 %d hunks, +%d/-%d（属性变化 %d 项，仅计数 %d 项）" \
               % (sh, sp, sm, kn, kc)
    print(msg)


if __name__ == "__main__":
    main()
