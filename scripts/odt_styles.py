#!/usr/bin/env python3
"""解析 ODT 样式的“有效属性”，并按属性分组统计。

解决的问题：文档里有十几种字体、行高、底色组合时，肉眼查不出来源。

用法:
  python3 odt_styles.py 文件.odt                  # 段落 + 文字样式，按属性分组
  python3 odt_styles.py 文件.odt --family paragraph
  python3 odt_styles.py 文件.odt --resolve TBMFile # 单个样式的继承链
  python3 odt_styles.py 文件.odt --warn-only      # 只报继承风险
  python3 odt_styles.py 文件.odt --unused         # 只列没被引用的样式
  python3 odt_styles.py 文件.odt --json

重要：LibreOffice 不把「自动样式」(content.xml 里的 office:automatic-styles)
当作可继承的 style:parent-style-name。继承会静默失败，字体/底色全丢，且不报错。
本脚本会解析两种结果并对比，把这种风险标出来。
"""
import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import require_deps  # noqa: E402

require_deps()

from lxml import etree          # noqa: E402
from odfdo import Document      # noqa: E402

TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
OFFICE = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
STYLE = "urn:oasis:names:tc:opendocument:xmlns:style:1.0"
FO = "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"

# 属性键的展示顺序与中文名
PARA_KEYS = [("font", "字体"), ("size", "字号"), ("line_height", "行高"),
             ("margin_top", "段前"), ("margin_bottom", "段后"),
             ("background", "底色"), ("color", "颜色"),
             ("weight", "粗"), ("style", "斜"), ("underline", "下划线"),
             ("align", "对齐"), ("indent", "左缩进"), ("font_asian", "中文字体")]
TEXT_KEYS = [("font", "字体"), ("size", "字号"), ("color", "颜色"),
             ("weight", "粗"), ("style", "斜"), ("underline", "下划线"),
             ("background", "底色")]
DISPLAY = dict(PARA_KEYS + TEXT_KEYS)


def q(ns, tag):
    return "{%s}%s" % (ns, tag)


def props_of(el):
    """读一个 style 元素自己声明的属性（不含继承）。"""
    out = {}
    pp = el.find(q(STYLE, "paragraph-properties"))
    tp = el.find(q(STYLE, "text-properties"))
    if pp is not None:
        for key, attr in (("line_height", q(FO, "line-height")),
                          ("margin_top", q(FO, "margin-top")),
                          ("margin_bottom", q(FO, "margin-bottom")),
                          ("background", q(FO, "background-color")),
                          ("align", q(FO, "text-align")),
                          ("indent", q(FO, "margin-left"))):
            v = pp.get(attr)
            if v is not None:
                out[key] = v
    if tp is not None:
        for key, attr in (("font", q(STYLE, "font-name")),
                          ("font_asian", q(STYLE, "font-name-asian")),
                          ("font_family", q(FO, "font-family")),
                          ("size", q(FO, "font-size")),
                          ("size_asian", q(STYLE, "font-size-asian")),
                          ("color", q(FO, "color")),
                          ("background", q(FO, "background-color")),
                          ("weight", q(FO, "font-weight")),
                          ("style", q(FO, "font-style")),
                          ("underline", q(STYLE, "text-underline-style"))):
            v = tp.get(attr)
            if v is not None:
                out[key] = v
    return out


def build(path):
    """返回 (content, styles, defs, auto_names, defaults)。"""
    doc = Document(path)
    content = etree.fromstring(doc.container.get_part("content.xml"))
    styles = etree.fromstring(doc.container.get_part("styles.xml"))
    defs, auto = {}, set()
    for e in content.iter(q(STYLE, "style")):
        nm = e.get(q(STYLE, "name"))
        if nm:
            defs[(e.get(q(STYLE, "family")), nm)] = e
            auto.add(nm)
    for e in styles.iter(q(STYLE, "style")):
        nm = e.get(q(STYLE, "name"))
        if nm:
            defs.setdefault((e.get(q(STYLE, "family")), nm), e)
    defaults = {}
    for e in styles.iter(q(STYLE, "default-style")):
        defaults[e.get(q(STYLE, "family"))] = e
    return content, styles, defs, auto, defaults


def chain_of(family, name, defs):
    chain, seen, cur = [], set(), name
    while cur and cur not in seen:
        seen.add(cur)
        e = defs.get((family, cur))
        if e is None:
            break
        chain.append((cur, e))
        cur = e.get(q(STYLE, "parent-style-name"))
    return chain


def resolve(family, name, defs, auto, defaults):
    """返回 (expected, actual, chain, broken_at)。

    expected = 按 ODF 规范沿父样式链合并的结果。
    actual   = LibreOffice 实际会用的结果：碰到「自动样式」祖先就中断继承。
    broken_at= 被中断的那个自动样式名；None 表示无风险。
    """
    chain = chain_of(family, name, defs)
    d = defaults.get(family)
    base = props_of(d) if d is not None else {}

    expected = dict(base)
    for _nm, e in reversed(chain):
        expected.update(props_of(e))

    actual = dict(base)
    broken_at = None
    for nm, e in reversed(chain):
        if nm != name and nm in auto:
            broken_at = nm
            break
        actual.update(props_of(e))
    return expected, actual, chain, broken_at


def analyse(path):
    """汇总文档里用到的样式与解析结果。"""
    content, styles, defs, auto, defaults = build(path)
    body = content.find(".//" + q(OFFICE, "text"))
    p_count, t_count = collections.Counter(), collections.Counter()
    if body is not None:
        for p in body.iter(q(TEXT, "p")):
            if p.get(q(TEXT, "style-name")):
                p_count[p.get(q(TEXT, "style-name"))] += 1
        for sp in body.iter(q(TEXT, "span")):
            if sp.get(q(TEXT, "style-name")):
                t_count[sp.get(q(TEXT, "style-name"))] += 1

    def rows(family, counter):
        out = []
        for name, n in counter.items():
            exp, act, chain, broken = resolve(family, name, defs, auto, defaults)
            out.append({"name": name, "count": n, "expected": exp,
                        "actual": act, "chain": [c[0] for c in chain],
                        "broken_at": broken})
        return out

    missing = {
        "paragraph": sorted(n for n in p_count if n and ("paragraph", n) not in defs),
        "text": sorted(n for n in t_count if n and ("text", n) not in defs),
    }
    return {"paragraphs": rows("paragraph", p_count),
            "texts": rows("text", t_count),
            "missing": missing,
            "defs": defs, "auto": auto, "defaults": defaults}


def group_rows(rows, family):
    """按“实际会生效”的属性分组，返回可直接打印/diff 的字符串行。"""
    keys = [k for k, _ in (PARA_KEYS if family == "paragraph" else TEXT_KEYS)]
    groups = collections.defaultdict(lambda: [0, []])
    for r in rows:
        p = r["actual"]
        key = tuple(p.get(k) for k in keys)
        groups[key][0] += r["count"]
        groups[key][1].append(str(r["name"]))
    out = []
    for key, (n, names) in sorted(groups.items(), key=lambda x: -x[1][0]):
        cells = ["%s=%s" % (DISPLAY[k], key[i] if key[i] is not None else "—")
                 for i, k in enumerate(keys) if key[i] is not None]
        unit = "段" if family == "paragraph" else "处"
        out.append("%5d %s | %-58s | %s" % (n, unit, " ".join(cells),
                                            " ".join(sorted(names))))
    return out


def cmd_table(path, family):
    a = analyse(path)
    both = [("paragraph", "paragraphs"), ("text", "texts")]
    if family == "paragraph":
        pairs = [("paragraph", "paragraphs")]
    elif family == "text":
        pairs = [("text", "texts")]
    else:
        pairs = both
    for fam, key in pairs:
        label = "段落样式" if fam == "paragraph" else "文字（span）样式"
        print("== %s（按“实际会生效”的属性分组） ==" % label)
        rows = group_rows(a[key], fam)
        print("\n".join(rows) if rows else "  （无）")
        print()


def cmd_resolve(path, name):
    a = analyse(path)
    for family in ("paragraph", "text"):
        if (family, name) not in a["defs"]:
            continue
        exp, act, chain, broken = resolve(family, name, a["defs"], a["auto"], a["defaults"])
        print("样式 %s（family=%s）继承链：" % (name, family))
        for i, (nm, e) in enumerate(chain):
            tag = "自动样式" if nm in a["auto"] else "命名样式"
            own = props_of(e)
            print("  %s%s  [%s]  parent=%s" % ("  " * i, nm, tag,
                                               e.get(q(STYLE, "parent-style-name")) or "—"))
            if own:
                print("  %s     声明: %s" % ("  " * i,
                                              " ".join("%s=%s" % (DISPLAY.get(k, k), v)
                                                       for k, v in own.items())))
        print("\n  按规范解析: %s" % fmt(exp))
        print("  实际生效:   %s" % fmt(act))
        if broken:
            print("\n  !! 继承在自动样式 `%s` 处中断。" % broken)
            print("     LibreOffice 忽略指向自动样式的 style:parent-style-name，")
            print("     上游属性（字体、底色、行高…）会静默回落到默认样式。")
            print("     修法：把属性直接声明到该样式自己身上，不要靠继承。")
            diff = {k: (exp.get(k), act.get(k)) for k in set(exp) | set(act)
                    if exp.get(k) != act.get(k)}
            if diff:
                print("\n  丢失/被覆盖的属性：")
                for k, (e_, a_) in diff.items():
                    print("      %-10s 期望 %s -> 实际 %s"
                          % (DISPLAY.get(k, k), e_ if e_ is not None else "—",
                             a_ if a_ is not None else "—"))
        else:
            print("\n  继承链正常（无自动样式祖先）。")
        return
    print("找不到样式 %s" % name, file=sys.stderr)
    sys.exit(1)


def fmt(p):
    if not p:
        return "（无属性）"
    return " ".join("%s=%s" % (DISPLAY.get(k, k), v) for k, v in sorted(p.items()))


def cmd_warn(path):
    a = analyse(path)
    rc = 0
    for fam, key in (("段落", "paragraph"), ("文字", "text")):
        miss = a["missing"][key]
        if miss:
            rc = 1
            print("!! 引用了但未定义的%s样式（%d 个）—— LibreOffice 会回落到默认样式"
                  % (fam, len(miss)))
            for nm in miss:
                print("      %s" % nm)
    bad = [r for fam in ("paragraphs", "texts") for r in a[fam] if r["broken_at"]]
    if not bad:
        print("无继承风险：没有样式的父样式指向自动样式。")
        return rc
    print("!! 继承风险（%d 个样式）" % len(bad))
    for r in sorted(bad, key=lambda x: -x["count"]):
        lost = {k: (r["expected"].get(k), r["actual"].get(k))
                for k in set(r["expected"]) | set(r["actual"])
                if r["expected"].get(k) != r["actual"].get(k)}
        print("  %-20s x%-4d 中断于 %s" % (r["name"], r["count"], r["broken_at"]))
        for k, (e_, a_) in sorted(lost.items()):
            print("      %-10s 期望 %s -> 实际 %s"
                  % (DISPLAY.get(k, k), e_ if e_ is not None else "—",
                     a_ if a_ is not None else "—"))
    return 1


def cmd_unused(path):
    a = analyse(path)
    used_p = {r["name"] for r in a["paragraphs"]}
    used_t = {r["name"] for r in a["texts"]}
    for family, used in (("paragraph", used_p), ("text", used_t)):
        rows = []
        for (fam, nm) in a["defs"]:
            if fam == family and nm not in used:
                rows.append(nm)
        print("== 未被引用的%s样式：%d 个 ==" % ("段落" if family == "paragraph" else "文字",
                                              len(rows)))
        if rows:
            print("  " + " ".join(sorted(rows)))
        print()


def main():
    ap = argparse.ArgumentParser(description="解析 ODT 样式的有效属性")
    ap.add_argument("odt")
    ap.add_argument("--family", choices=("both", "paragraph", "text"), default="both")
    ap.add_argument("--resolve", metavar="样式名")
    ap.add_argument("--warn-only", action="store_true")
    ap.add_argument("--unused", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.json:
        a = analyse(args.odt)
        print(json.dumps({k: a[k] for k in ("paragraphs", "texts")},
                         ensure_ascii=False, indent=2))
        return
    if args.resolve:
        cmd_resolve(args.odt, args.resolve)
        return
    if args.warn_only:
        sys.exit(cmd_warn(args.odt))
    if args.unused:
        cmd_unused(args.odt)
        return
    n = cmd_warn(args.odt)
    print()
    cmd_table(args.odt, args.family)
    if n:
        sys.exit(1)


if __name__ == "__main__":
    main()
