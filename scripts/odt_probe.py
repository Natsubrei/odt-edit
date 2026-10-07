#!/usr/bin/env python3
"""渲染探针：从 render.sh 产出的 PDF/PNG 里取证据。

解决的问题：光看 ODT 的 XML 判断不了“渲染出来到底是什么样”。
字体被替换、底色少一行、同一行里两种字体 —— 只有查渲染产物才知道。

依赖 render.sh 的输出目录（默认 $ODT_EDIT_WORK/<文件名去扩展>/）：
    render.pdf    render.txt    pages/p-NN.png

用法:
  python3 odt_probe.py 文件.odt --fonts                # PDF 里用到的 (字体, 字号, 颜色)
  python3 odt_probe.py 文件.odt --fonts --page 11
  python3 odt_probe.py 文件.odt --bg 700 100 600       # 第 N 页某列的背景色连续段
  python3 odt_probe.py 文件.odt --bg 700 100 600 --page 11
  python3 odt_probe.py 文件.odt --crop 85 470 330 500 --scale 4
  python3 odt_probe.py 文件.odt --page-of "a1.sources" # 某段文字在第几页
  python3 odt_probe.py 文件.odt --pages                # 已渲染哪些页

坐标单位是 PNG 像素。渲染分辨率是 110 DPI（与 render.sh 一致）。
"""
import argparse
import collections
import os
import re
import struct
import subprocess
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import add_pylib, work  # noqa: E402

add_pylib()


def out_dir(odt):
    stem = os.path.splitext(os.path.basename(odt))[0]
    return os.path.join(os.environ.get("ODT_EDIT_WORK", work()), stem)


# --------------------------------------------------------------------------
# PDF：字体 / 分页
# --------------------------------------------------------------------------
def _docker_ok():
    if os.environ.get("ODT_EDIT_SKIP_DOCKER") == "1":
        return False
    if not shutil_which("docker"):
        return False
    img = os.environ.get("ODT_EDIT_IMAGE", "lo-headless")
    return subprocess.run(["docker", "image", "inspect", img],
                          stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0


def shutil_which(name):
    for p in os.environ.get("PATH", "").split(os.pathsep):
        f = os.path.join(p, name)
        if os.path.isfile(f) and os.access(f, os.X_OK):
            return f
    return None


def pdf_html(odt):
    """返回 pdftohtml -xml 的输出文本。"""
    d = out_dir(odt)
    pdf = os.path.join(d, "render.pdf")
    if not os.path.isfile(pdf):
        sys.exit("找不到 %s，先跑 render.sh" % pdf)
    if _docker_ok():
        img = os.environ.get("ODT_EDIT_IMAGE", "lo-headless")
        r = subprocess.run(["docker", "run", "--rm", "-v", d + ":/work", img, "bash", "-c",
                            "cd /work && pdftohtml -xml -i -stdout render.pdf 2>/dev/null"],
                           capture_output=True, text=True)
    else:
        if not shutil_which("pdftohtml"):
            sys.exit("没有 Docker 镜像，也没有 pdftohtml")
        r = subprocess.run(["pdftohtml", "-xml", "-i", "-stdout", pdf],
                           capture_output=True, text=True)
    if not r.stdout.strip():
        sys.exit("pdftohtml 无输出：%s" % (r.stderr or "")[:200])
    return r.stdout


def font_usage(odt, page=None):
    """返回 {页面号: Counter{(family, size, color): 字符数}}，以及全局合计。

    不解析 PDF，靠 pdftohtml -xml 给的 fontspec 编号统计。
    """
    xml = pdf_html(odt)
    pages = re.split(r"<page\b", xml)[1:]

    def specs_of(pg):
        out = {}
        for m in re.finditer(r"<fontspec\b([^>]*)>", pg):
            a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
            if a.get("id"):
                out[a["id"]] = (a.get("family", "?"), a.get("size", "?"),
                                a.get("color", "?"))
        return out

    # 有些页会引用别页声明的 font id，所以先建全局表兜底
    global_specs = {}
    for pg in pages:
        for k, v in specs_of(pg).items():
            global_specs.setdefault(k, v)

    total = collections.Counter()
    per_page = {}
    for idx, pg in enumerate(pages, 1):
        if page and idx != page:
            continue
        specs = dict(global_specs)
        specs.update(specs_of(pg))
        used = collections.Counter()
        for m in re.finditer(r'<text[^>]*font="(\d+)"[^>]*>(.*?)</text>', pg):
            used[m.group(1)] += len(re.sub(r"<[^>]+>", "", m.group(2)).strip())
        if used:
            per_page[idx] = collections.Counter()
            for fid, n in used.most_common():
                fam, size, col = specs.get(fid, ("?", "?", "?"))
                key = (fam.split("+")[-1], size, col)
                per_page[idx][key] += n
                total[key] += n
        if page:
            break
    return per_page, total


def cmd_fonts(odt, page=None):
    per_page, total = font_usage(odt, page)
    for idx in sorted(per_page):
        print("== 第 %d 页 ==" % idx)
        for (fam, size, col), n in per_page[idx].most_common():
            print("  %-24s size=%-4s color=%-9s %5d 字符" % (fam, size, col, n))
    print("\n== 汇总（字符数） ==")
    for (fam, size, col), n in total.most_common():
        print("  %-24s size=%-4s color=%-9s %6d" % (fam, size, col, n))
    fams = sorted({k[0] for k in total})
    mono = [f for f in fams if "Mono" in f or "Consol" in f or "Courier" in f]
    print("\n等宽字体: %s" % (", ".join(mono) if mono else "（无）"))
    print("颜色种类: %s" % ", ".join(sorted({k[2] for k in total})))


def cmd_page_of(odt, needle):
    d = out_dir(odt)
    txt = os.path.join(d, "render.txt")
    if not os.path.isfile(txt):
        sys.exit("找不到 %s，先跑 render.sh" % txt)
    raw = open(txt, encoding="utf-8").read()
    pages = raw.split("\x0c")
    norm = lambda t: re.sub(r"\s+", " ", t)          # pdftotext 的空格与原文不一致
    want = norm(needle).strip()
    hits = [i for i, p in enumerate(pages, 1) if want in norm(p)]
    if not hits:
        # 退化匹配：去掉全部空白
        tight = re.sub(r"\s+", "", needle)
        hits = [i for i, p in enumerate(pages, 1)
                if tight in re.sub(r"\s+", "", p)]
    if hits:
        print("出现页: %s" % ", ".join(map(str, hits)))
    else:
        print("未找到 %r。提示：pdftotext 会在连字符处折行，长串可能被拆开。" % needle)
    for i, p in enumerate(pages, 1):
        if want in norm(p):
            for line in p.splitlines():
                if norm(line).strip() and want[:12] in norm(line):
                    print("  第 %d 页: %s" % (i, line.strip()[:90]))
                    break


def cmd_pages(odt):
    d = out_dir(odt)
    pdir = os.path.join(d, "pages")
    if not os.path.isdir(pdir):
        sys.exit("找不到 %s，先跑 render.sh" % pdir)
    names = sorted(f for f in os.listdir(pdir) if f.endswith(".png"))
    print("%s (%d 张)" % (pdir, len(names)))
    for n in names:
        print("  " + n)


# --------------------------------------------------------------------------
# PNG：纯 Python 解码/编码（不依赖 PIL）
# --------------------------------------------------------------------------
def png_load(path):
    data = open(path, "rb").read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        sys.exit("%s 不是 PNG" % path)
    i, idat = 8, b""
    w = h = ct = None
    while i < len(data):
        ln = struct.unpack(">I", data[i:i + 4])[0]
        typ = data[i + 4:i + 8]
        chunk = data[i + 8:i + 8 + ln]
        if typ == b"IHDR":
            w, h, _bd, ct = struct.unpack(">IIBB", chunk[:10])
        elif typ == b"IDAT":
            idat += chunk
        i += 12 + ln
    raw = zlib.decompress(idat)
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ct]
    stride = w * ch
    out = bytearray()
    prev = bytearray(stride)
    p = 0
    for _ in range(h):
        f = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if f == 1:
            for x in range(ch, stride):
                line[x] = (line[x] + line[x - ch]) & 255
        elif f == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif f == 3:
            for x in range(stride):
                a = line[x - ch] if x >= ch else 0
                line[x] = (line[x] + ((a + prev[x]) >> 1)) & 255
        elif f == 4:
            for x in range(stride):
                a = line[x - ch] if x >= ch else 0
                b = prev[x]
                c = prev[x - ch] if x >= ch else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[x] = (line[x] + pr) & 255
        out += line
        prev = line
    return w, h, ch, bytes(out)


def png_save(path, w, h, rows):
    def chunk(t, d):
        return (struct.pack(">I", len(d)) + t + d
                + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff))
    body = b"".join(b"\x00" + r for r in rows)
    blob = b"\x89PNG\r\n\x1a\n"
    blob += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    blob += chunk(b"IDAT", zlib.compress(body, 9))
    blob += chunk(b"IEND", b"")
    open(path, "wb").write(blob)


def page_png(odt, page):
    d = out_dir(odt)
    path = os.path.join(d, "pages", "p-%02d.png" % page)
    if not os.path.isfile(path):
        sys.exit("找不到 %s，先跑 render.sh（页码从 1 开始）" % path)
    return path


def classify(px, kind=None):
    r, g, b = px
    if kind == "bg-only":
        pass
    if r > 250 and g > 250 and b > 250:
        return "WHITE"
    if abs(r - g) < 8 and abs(g - b) < 8:
        if 225 <= r <= 250:
            return "GRAY"
        if r < 180:
            return "INK"
    return "COLOR"


def cmd_bg(odt, page, x, y0, y1):
    w, h, ch, px = png_load(page_png(odt, page))
    if not (0 <= x < w):
        sys.exit("x=%d 超出图片宽度 %d" % (x, w))
    y1 = min(y1, h)
    runs = []
    state = None
    for y in range(max(0, y0), y1):
        o = (y * w + x) * ch
        t = classify(px[o:o + 3])
        if state is None or state[0] != t:
            state = [t, y, y]
            runs.append(state)
        else:
            state[2] = y
    print("# %s  x=%d  y=%d..%d" % (page_png(odt, page), x, y0, y1))
    print("  色值: WHITE=白底  GRAY=浅灰底  INK=文字  COLOR=彩色")
    for t, a, b in runs:
        if b - a >= 2:
            print("  %-6s y=%4d-%4d  高 %d" % (t, a, b, b - a + 1))


def cmd_crop(odt, page, x0, y0, x1, y1, scale):
    w, h, ch, px = png_load(page_png(odt, page))
    x1 = min(x1, w)
    y1 = min(y1, h)
    rows = []
    for y in range(y0, y1):
        row = bytearray()
        for x in range(x0, x1):
            o = (y * w + x) * ch
            row += px[o:o + 3] * scale
        for _ in range(scale):
            rows.append(bytes(row))
    dst = os.path.join(out_dir(odt), "crop-p%d-%d_%d.png" % (page, x0, y0))
    png_save(dst, (x1 - x0) * scale, (y1 - y0) * scale, rows)
    print(dst)


def main():
    ap = argparse.ArgumentParser(description="ODT 渲染探针")
    ap.add_argument("odt")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--fonts", action="store_true", help="PDF 字体/字号/颜色")
    g.add_argument("--bg", nargs=3, metavar=("X", "Y0", "Y1"), help="某列的背景色连续段")
    g.add_argument("--crop", nargs=4, metavar=("X0", "Y0", "X1", "Y1"), help="裁剪放大")
    g.add_argument("--page-of", metavar="文本", help="文字在第几页")
    g.add_argument("--pages", action="store_true", help="已渲染的页")
    ap.add_argument("--page", type=int, default=1)
    ap.add_argument("--scale", type=int, default=3)
    args = ap.parse_args()

    if args.fonts:
        cmd_fonts(args.odt, args.page if args.page > 1 else None)
    elif args.bg:
        cmd_bg(args.odt, args.page, *(int(v) for v in args.bg))
    elif args.crop:
        cmd_crop(args.odt, args.page, *(int(v) for v in args.crop), args.scale)
    elif args.page_of:
        cmd_page_of(args.odt, args.page_of)
    else:
        cmd_pages(args.odt)


if __name__ == "__main__":
    main()
