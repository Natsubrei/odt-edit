#!/usr/bin/env python3
"""ODT checks. Always: zip + mimetype.
Optional: --require-toc --require-chapter-seq --forbid-nbsp --forbidden a,b
          --font-audit              样式是否真正生效（只看 XML，不需要渲染）
          --render                  另外核对渲染产物（需先跑 render.sh）
Usage: python3 check_odt.py file.odt [flags]
Exit 0=pass 1=fail.

为什么需要 --font-audit：zip/TOC/章节号全过，样式仍可能整段失效。
LibreOffice 不把自动样式当父样式，不认识的样式名也不报错，两处都静默回落到默认样式。
"""
import sys, os, re, zipfile, argparse
from paths import require_deps, work
require_deps()


def _hex_rgb(v):
    v = (v or "").strip().lstrip("#")
    if len(v) == 6:
        try:
            return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return None
    return None


def audit_styles(path, problems):
    """样式是不是真的生效。只看 XML，不靠渲染，很快。"""
    import odt_styles as S

    a = S.analyse(path)
    n_bad = 0
    for fam, label in (("paragraph", "段落"), ("text", "文字")):
        for nm in a["missing"][fam]:
            problems.append(
                "%s样式 `%s` 未定义：正文引用了它，LibreOffice 静默回落默认样式" % (label, nm))
            n_bad += 1
        for r in a[fam + "s"]:
            if not r["broken_at"]:
                continue
            lost = [S.DISPLAY.get(k, k) for k in sorted(set(r["expected"]) | set(r["actual"]))
                    if r["expected"].get(k) != r["actual"].get(k)]
            problems.append(
                "%s样式 `%s`（%d 处）的继承在自动样式 `%s` 处中断，丢失属性：%s"
                % (label, r["name"], r["count"], r["broken_at"], " ".join(lost) or "—"))
            n_bad += 1
    print("font-audit: %s" % ("发现 %d 处样式失效" % n_bad if n_bad
                               else "样式均生效（无未定义样式、无继承断裂）"))


def _bg_colours_seen(odt, wanted):
    """在渲染页里找声明过的底色。按列扫，只认长度 >= 6 像素的同色段。"""
    import collections
    import odt_probe as P

    pdir = os.path.join(P.out_dir(odt), "pages")
    if not os.path.isdir(pdir):
        return None, "找不到 %s，先跑 render.sh" % pdir
    counts = collections.Counter()
    names = sorted(f for f in os.listdir(pdir) if f.endswith(".png"))
    for i, n in enumerate(names, 1):
        w, h, ch, px = P.png_load(os.path.join(pdir, n))
        for x in range(w // 8, w, max(1, w // 6)):
            prev, run = None, 0
            for y in range(h):
                o = (y * w + x) * ch
                c = tuple(px[o:o + 3])
                if c == prev:
                    run += 1
                    continue
                if prev and run >= 6 and prev != (255, 255, 255):
                    counts[prev] += run
                prev, run = c, 1
            if prev and run >= 6 and prev != (255, 255, 255):
                counts[prev] += run
        if i % 10 == 0:
            print("  ...已扫 %d/%d 页" % (i, len(names)), file=sys.stderr)
    # 抗锯齿会造出大量杂色，只留有足够面积的
    return {c for c, n in counts.items() if n >= 30}, None


def audit_render(path, problems):
    """核对渲染产物。需要先跑 render.sh。"""
    import odt_probe as P
    import odt_styles as S

    d = P.out_dir(path)
    if not os.path.isfile(os.path.join(d, "render.pdf")):
        problems.append("--render 需要先跑 render.sh（找不到 %s/render.pdf）" % d)
        return

    _, total = P.font_usage(path)
    if not total:
        problems.append("--render 没能从 PDF 里读到字体，渲染产物可能不完整")
        return

    print("render: 用到 %d 种 (字体, 字号, 颜色) 组合" % len(total))
    for (fam, size, col), n in total.most_common(12):
        print("  %-24s size=%-4s color=%-9s %6d 字符" % (fam, size, col, n))

    def bits(v):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None

    # 1. 等宽字体只应有一种。两种 = 有片段掉回了别的字体
    monos = sorted({fam for fam in {k[0] for k in total}
                    if re.search(r"Mono|Consol|Courier", fam, re.I)})
    if len(monos) > 1:
        problems.append("渲染里有 %d 种等宽字体（%s）：有片段掉回了别的字体"
                        % (len(monos), ", ".join(monos)))

    # 2. 同一等宽字体出现两个“几乎一样”的字号 = 有片段静默换了字号。
    #    只查等宽：正文 12pt 与表格 10.5pt 这种差异是故意的，不是错误。
    by_fam = {}
    for fam, size, col in total:
        by_fam.setdefault(fam, set()).add(size)
    for fam in monos:
        vals = sorted(b for b in (bits(s) for s in by_fam.get(fam, ())) if b is not None)
        for a_, b_ in zip(vals, vals[1:]):
            if b_ - a_ <= 2:
                problems.append("等宽字体 %s 出现近乎重复的字号 %d 与 %d：有片段静默改了字号"
                                % (fam, a_, b_))

    # 3. 近色：视觉上一样、编码不同。同理
    cols = sorted({k[2] for k in total if k[2] != "?"})
    rgbs = [(c, _hex_rgb(c)) for c in cols]
    for i in range(len(rgbs)):
        for j in range(i + 1, len(rgbs)):
            c1, r1 = rgbs[i]
            c2, r2 = rgbs[j]
            if r1 and r2 and max(abs(x - y) for x, y in zip(r1, r2)) <= 24:
                problems.append("颜色 %s 与 %s 近乎相同：同一意图用了两个色值" % (c1, c2))

    # 4. 声明了底色，渲染里就该找得到
    declared = {}
    for (fam, nm), el in S.analyse(path)["defs"].items():
        v = S.props_of(el).get("background")
        if v:
            rgb = _hex_rgb(v)
            if rgb and rgb != (255, 255, 255):
                declared.setdefault(rgb, v)
    if not declared:
        print("render: 没有声明底色，跳过底色核对")
        return
    seen, err = _bg_colours_seen(path, declared)
    if err:
        problems.append(err)
        return
    for rgb, hexv in sorted(declared.items()):
        if rgb in seen:
            print("render: 底色 %s 在渲染中已出现" % hexv)
        else:
            problems.append("样式声明了底色 %s，但渲染页里找不到：底色没生效" % hexv)


def audit_toc_pages(path, problems):
    """核对目录字段里缓存的页码与渲染分页是否一致。需要先跑 render.sh。

    目录是字段，页码是上次刷新时写死的文本；正文加几行就会让后面章节整体挪一页，
    而目录数字不变。`--refresh-toc` 也不一定收敛：LibreOffice 会话内算的版式
    可能与冷加载差一页，所以这里以渲染产物为准。
    """
    import odt_probe as P

    txt = os.path.join(P.out_dir(path), "render.txt")
    if not os.path.isfile(txt):
        problems.append("--toc-pages 需要先跑 render.sh（找不到 %s）" % txt)
        return
    pages = open(txt, encoding="utf-8", errors="replace").read().split("\f")
    entry_re = re.compile(r"^(.+?)\.{6,}(\d+)\s*$")
    norm = lambda s: re.sub(r"\s+", "", s)

    toc_idx = [i for i, p in enumerate(pages)
               if sum(1 for l in p.splitlines() if entry_re.match(l.strip())) >= 3]
    if not toc_idx:
        print("toc-pages: 渲染里没找到目录页，跳过")
        return
    entries = []
    for i in toc_idx:
        for line in pages[i].splitlines():
            m = entry_re.match(line.strip())
            if m:
                entries.append((m.group(1).strip(), int(m.group(2))))

    cursor = max(toc_idx) + 1
    bad = []
    for name, num in entries:
        key = norm(name)
        found = None
        for i in range(cursor, len(pages)):
            if any(norm(l) == key for l in pages[i].splitlines() if l.strip()):
                found = i
                break
        if found is None or found + 1 != num:
            bad.append((name, num, found + 1 if found is not None else None))
        else:
            cursor = found   # 目录顺序即正文顺序，单向扫描可避开重名的列表项
    print("toc-pages: 目录 %d 条（占第 1-%d 页），与渲染分页不符 %d 条"
          % (len(entries), max(toc_idx) + 1, len(bad)))
    if bad:
        detail = "; ".join("「%s」标 %s 实 %s" % (n, a, b) for n, a, b in bad[:8])
        more = "；另有 %d 条" % (len(bad) - 8) if len(bad) > 8 else ""
        problems.append("目录页码漂移 %d/%d 条：%s%s。跑 render.sh --refresh-toc，"
                        "不收敛时按渲染分页回填目录字段里的数字" % (len(bad), len(entries), detail, more))


def audit_blocks(path, problems, fail=False):
    """把正文切成“连续等宽段落块”，报告块被切碎的地方。

    等宽行就是命令/文件内容块。块被一个普通段落从中间切开时，渲染上会出现
    灰色空白（底色断成两段），XML 本身看不出任何异常。
    典型事故：往已有文件内容块后面追行时，中间插了一句引导语。
    """
    from lxml import etree
    import odt_styles as S

    info = S.analyse(path)
    mono = {}
    for row in info["paragraphs"]:
        props = row["actual"]
        font = " ".join(str(props.get(k) or "")
                         for k in ("font", "font_family", "font_asian"))
        mono[row["name"]] = bool(re.search(r"Mono|Consol|Courier", font, re.I)) or \
            bool(re.search(r"Code|File|Mono|Pre", row["name"] or ""))

    content = S.build(path)[0]
    body = content.find(".//" + S.q(S.OFFICE, "text"))
    if body is None:
        problems.append("--blocks 找不到正文节点")
        return

    chapter, rows = "", []
    for e in body:
        if not isinstance(e.tag, str):
            continue
        local = etree.QName(e).localname
        if local == "h":
            chapter = "".join(e.itertext()).strip()
        elif local == "p":
            style = e.get(S.q(S.TEXT, "style-name"))
            text = "".join(e.itertext()).strip()
            if mono.get(style):
                rows.append((chapter, "code", text, style))
            elif text:
                rows.append((chapter, "prose", text, style))
            else:
                rows.append((chapter, "blank", "", style))

    # 连续 code 行 = 一个块
    blocks, i = [], 0
    while i < len(rows):
        if rows[i][1] != "code":
            i += 1
            continue
        j = i
        while j < len(rows) and rows[j][1] == "code":
            j += 1
        blocks.append((rows[i][0], j - i, rows[i][2], i))
        i = j

    print("blocks: %d 个块，%d 行等宽内容" % (len(blocks), sum(b[1] for b in blocks)))
    last_ch = None
    for ch, n, first, _idx in blocks:
        if ch != last_ch:
            print("  %s" % (ch or "(无章节)"))
            last_ch = ch
        print("    %3d 行  %s" % (n, first[:64]))

    # 块被单个非等宽行从中间切开。
    # 判据收窄到“两侧块都 >=2 行”：本文档的正常写法是「说明句 + 单条命令」交替，
    # 两侧都是单行块时中间夹一句说明是结构，不是事故。
    split_at = []
    for a, b in zip(blocks, blocks[1:]):
        if a[0] != b[0]:
            continue
        gap = rows[a[3] + a[1]:b[3]]
        step_re = re.compile(r"^\s*(\d+[.、)]|（\d+）|\(\d+\))")
        if len(gap) == 1 and gap[0][1] in ("prose", "blank") and a[1] >= 2 and b[1] >= 2 \
                and not step_re.match(gap[0][2]):
            split_at.append((a[0], gap[0][1], gap[0][2], a[1], b[1]))
    if split_at:
        detail = "; ".join("%s「%s」(%d 行块后接 %d 行块)"
                           % (ch, (t or "(空行)")[:28], n1, n2) for ch, _k, t, n1, n2 in split_at[:6])
        more = "；另有 %d 处" % (len(split_at) - 6) if len(split_at) > 6 else ""
        msg = ("等宽块被非等宽行切开 %d 处（渲染会出现底色断带、"
               "该行字体也不一致）：%s%s" % (len(split_at), detail, more))
        # 默认可选警告：说明句夹在两个文件块之间（zoo.cfg / logback）是合法结构。
        # 要当错误退出加 --blocks-fail。
        if fail:
            problems.append(msg)
        else:
            print("note:", msg)
    ones = [b for b in blocks if b[1] == 1]
    if ones:
        print("  提示：单行块 %d 个（合法但常是被切断的块），例：%s"
              % (len(ones), "; ".join(b[2][:36] for b in ones[:4])))


def audit_indent(path, needle):
    """打印含 needle 的段落：样式名 + 前导空格数（展开 text:s 后）。

    为什么需要：diff_odt.py / odt_text.py / render.txt 都不展开 text:s，
    等宽行的对齐在纯文本层完全看不见，改错了也看不出来。
    """
    import odthelper as H
    import odt_styles as S

    content = S.build(path)[0]
    body = content.find(".//" + S.q(S.OFFICE, "text"))
    hits = 0
    for p in body.iter(S.q(S.TEXT, "p")):
        text = "".join(p.itertext())
        if needle in text:
            hits += 1
            print("  indent=%d  %-16s %s"
                  % (H.leading_spaces(p),
                     p.get(S.q(S.TEXT, "style-name")) or "-",
                     text.strip()[:72]))
    if not hits:
        print("  indent: 未找到 %r" % needle)
    return hits


_PROSE_STUCK = (
    re.compile(r"[\u4e00-\u9fff][A-Za-z/$]"),
    re.compile(r"[A-Za-z/$][\u4e00-\u9fff]"),
)


def audit_prose_space(path, problems):
    """正文（非等宽块）里中文贴着英文，或 / $ 贴着中文。配置块不查。"""
    from lxml import etree
    import odt_styles as S

    info = S.analyse(path)
    skip = {}
    for row in info["paragraphs"]:
        props = row["actual"]
        font = " ".join(str(props.get(k) or "")
                         for k in ("font", "font_family", "font_asian"))
        skip[row["name"]] = bool(re.search(r"Mono|Consol|Courier", font, re.I)) or \
            bool(re.search(r"Code|File|Mono|Pre", row["name"] or ""))

    content = S.build(path)[0]
    body = content.find(".//" + S.q(S.OFFICE, "text"))
    if body is None:
        problems.append("--prose-space 找不到正文节点")
        return
    hits = []
    chapter = ""
    for e in body.iter():
        if not isinstance(e.tag, str):
            continue
        local = etree.QName(e).localname
        if local == "h":
            chapter = "".join(e.itertext()).strip()
        if local not in ("p", "h"):
            continue
        style = e.get(S.q(S.TEXT, "style-name"))
        if skip.get(style):
            continue
        text = "".join(e.itertext())
        if any(rx.search(text) for rx in _PROSE_STUCK):
            hits.append((chapter, text.strip()[:48]))
    if hits:
        detail = "; ".join("%s「%s」" % (ch or "(无章节)", t) for ch, t in hits[:8])
        more = "；另有 %d 处" % (len(hits) - 8) if len(hits) > 8 else ""
        problems.append("正文中英文或路径未空开 %d 处：%s%s" % (len(hits), detail, more))
    else:
        print("prose-space: 正文中英文已空开")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--forbidden", default="", help="comma-separated substrings")
    ap.add_argument("--require-toc", action="store_true")
    ap.add_argument("--require-chapter-seq", action="store_true")
    ap.add_argument("--forbid-nbsp", action="store_true")
    ap.add_argument("--font-audit", action="store_true",
                    help="检查样式是否真正生效（未定义样式 / 继承断裂）")
    ap.add_argument("--blocks", action="store_true",
                    help="列出连续等宽段落块；被切开的块默认只警告（说明句夹两块常是合法结构）")
    ap.add_argument("--blocks-fail", action="store_true",
                    help="与 --blocks 相同，但切开当作错误（退出码 1）")
    ap.add_argument("--prose-space", action="store_true",
                    help="正文（非等宽块）中文贴着英文、或 / $ 贴着中文则失败")
    ap.add_argument("--indent", metavar="文本", action="append",
                    help="打印匹配段落的前导空格数（展开 text:s）与样式名；可重复")
    ap.add_argument("--render", action="store_true",
                    help="另外核对渲染产物：等宽字体数、同族字号、近色、声明的底色")
    ap.add_argument("--toc-pages", action="store_true",
                    help="核对目录里缓存的页码与渲染分页是否一致（需先跑 render.sh）")
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
    if args.blocks or args.blocks_fail:
        audit_blocks(path, problems, fail=args.blocks_fail)
    if args.prose_space:
        audit_prose_space(path, problems)
    for needle in args.indent or []:
        audit_indent(path, needle)
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

    if args.font_audit or args.render:
        audit_styles(path, problems)
    if args.render:
        audit_render(path, problems)
    if args.toc_pages:
        audit_toc_pages(path, problems)

    print("meta title:", doc.meta.get_title())
    if problems:
        print("\nFAIL")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
