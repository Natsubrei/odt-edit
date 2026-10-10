#!/usr/bin/env bash
# Python-only smoke test. Does not need Docker or LibreOffice.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
export ODT_EDIT_SKIP_DOCKER=1
bash "$HERE/setup_env.sh" --python-only
python3 "$HERE/make_examples.py"
python3 "$HERE/outline.py" "$ROOT/examples/nested-list.odt" | grep -q Nested
python3 "$HERE/check_odt.py" "$ROOT/examples/no-toc.odt"
if python3 "$HERE/check_odt.py" "$ROOT/examples/no-toc.odt" --require-toc; then
  echo "expected --require-toc to fail" >&2
  exit 1
fi
DIFF="$ROOT/examples/_selftest.diff"
python3 "$HERE/diff_odt.py" "$ROOT/examples/leaf.odt" "$ROOT/examples/nested-list.odt" "$DIFF"
test -s "$DIFF"
python3 "$HERE/diff_odt.py" "$ROOT/examples/leaf.odt" "$ROOT/examples/nested-list.odt" "$DIFF" --styles
test -s "$DIFF"
grep -q "样式" "$DIFF"
rm -f "$DIFF"

# 样式解析：正常文档不应报继承风险，也不应报未定义样式
python3 "$HERE/odt_styles.py" "$ROOT/examples/nested-list.odt" --warn-only
python3 "$HERE/odt_styles.py" "$ROOT/examples/nested-list.odt" --family paragraph >/dev/null
python3 "$HERE/odt_styles.py" "$ROOT/examples/nested-list.odt" --unused >/dev/null
python3 "$HERE/odt_styles.py" "$ROOT/examples/nested-list.odt" --json >/dev/null

# 空段落保留开关
TXT="$ROOT/examples/_selftest.txt"
python3 "$HERE/odt_text.py" "$ROOT/examples/leaf.odt" "$TXT" --keep-blanks
test -s "$TXT"
rm -f "$TXT"

# odthelper：助手可用，且 set_el_text 拒收 list-item
python3 - "$ROOT" <<'PY'
import sys
sys.path.insert(0, sys.argv[1] + "/scripts")
import odthelper as H
doc = H.load(sys.argv[1] + "/examples/nested-list.odt")

# 连续空格必须写成 text:s，否则被折叠
p = H.make_p("Standard", "a  b\tc")
x = p._xml_element
assert "{" + H.TEXT + "}s" in [e.tag for e in x.iter()], "连续空格没编码成 text:s"
assert "{" + H.TEXT + "}tab" in [e.tag for e in x.iter()], "tab 没编码"
assert "{" + H.TEXT + "}line-break" in [
    e.tag for e in H.make_p("Standard", "a\nb")._xml_element.iter()], "换行没编码"

# set_el_text 不能用于 list-item
item = next(e for e in doc.body.children if e.tag == "text:list"
            for e in e.children if e.tag == "text:list-item")
try:
    H.set_el_text(item, "x")
    raise SystemExit("set_el_text 本该拒绝 list-item")
except ValueError:
    pass

# set_item_label 保留下级 list
before = len(item._xml_element)
H.set_item_label(item, "重写标签")
assert len(item._xml_element) == before, "set_item_label 弄丢了子节点"

h = H.make_h(2, "标题", "Heading_20_2")
assert h._xml_element.get(H.A_STYLE) == "Heading_20_2", "make_h 丢了 style"
PY
echo "odthelper OK"

# check_odt --font-audit 必须能发现未定义样式
BAD="$ROOT/examples/_selftest_bad.odt"
python3 - "$ROOT" "$BAD" <<'PY'
import sys, zipfile
# 造一个引用了不存在样式的文档
src = sys.argv[1] + "/examples/leaf.odt"
parts = {}
z = zipfile.ZipFile(src)
for n in z.namelist():
    parts[n] = z.read(n)
c = parts["content.xml"].decode()
# 在正文末尾加一个引用不存在样式的段落
assert "</office:text>" in c
c = c.replace("</office:text>",
              '<text:p text:style-name="NoSuchStyle">x</text:p></office:text>', 1)
parts["content.xml"] = c.encode()
with zipfile.ZipFile(sys.argv[2], "w") as o:
    o.writestr("mimetype", parts["mimetype"], zipfile.ZIP_STORED)
    for n, b in parts.items():
        if n != "mimetype":
            o.writestr(n, b)
PY
if python3 "$HERE/check_odt.py" "$BAD" --font-audit >/dev/null 2>&1; then
  echo "expected --font-audit to fail on an undefined style" >&2
  exit 1
fi
rm -f "$BAD"

# --render / --toc-pages 在没渲染时应当报错退出，而不是崩栈
if python3 "$HERE/check_odt.py" "$ROOT/examples/leaf.odt" --render >/dev/null 2>&1; then
  echo "expected --render to fail without a render" >&2
  exit 1
fi
if python3 "$HERE/check_odt.py" "$ROOT/examples/leaf.odt" --toc-pages >/dev/null 2>&1; then
  echo "expected --toc-pages to fail without a render" >&2
  exit 1
fi

# props_of 必须能读到 text 样式声明的底色（以前只读段落属性，底色核对形同虚设）
python3 - "$ROOT" <<'PY'
import sys, zipfile
sys.path.insert(0, sys.argv[1] + "/scripts")
src = sys.argv[1] + "/examples/leaf.odt"
parts = {n: zipfile.ZipFile(src).read(n) for n in zipfile.ZipFile(src).namelist()}
c = parts["content.xml"].decode()
assert "<office:body>" in c and "</office:text>" in c
c = c.replace("<office:body>",
              '<office:automatic-styles '
              'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
              'xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0">'
              '<style:style style:name="TSelfTest" style:family="text">'
              '<style:text-properties fo:background-color="#cff8b6"/></style:style>'
              '</office:automatic-styles><office:body>', 1)
c = c.replace("</office:text>",
              '<text:p text:style-name="P1"><text:span text:style-name="TSelfTest">x</text:span>'
              "</text:p></office:text>", 1)
parts["content.xml"] = c.encode()
out = sys.argv[1] + "/examples/_selftest_bg.odt"
with zipfile.ZipFile(out, "w") as o:
    o.writestr("mimetype", parts["mimetype"], zipfile.ZIP_STORED)
    for n, b in parts.items():
        if n != "mimetype":
            o.writestr(n, b)

import odt_styles as S
_content, _styles, defs, _auto, _def = S.build(out)
el = defs[("text", "TSelfTest")]
got = S.props_of(el).get("background")
assert got == "#cff8b6", "text 样式的底色没被解析出来：%r" % got
print("props_of 底色 OK")
PY
rm -f "$ROOT/examples/_selftest_bg.odt"

# replace_text：命中数对得上，且只改文字槽、保留 span 结构
python3 - "$ROOT" <<'PY'
import sys
sys.path.insert(0, sys.argv[1] + "/scripts")
import odthelper as H
doc = H.load(sys.argv[1] + "/examples/nested-list.odt")
p = next(e for e in doc.body._xml_element.iter()
         if (e.tag.endswith("}p") or e.tag.endswith("}h"))
         and "Nested" in "".join(e.itertext()))
kids_before = len(p)
H.replace_text(p, "Nested", "埋点")
assert "埋点" in "".join(p.itertext()) and kids_before == len(p), "replace_text 动了结构"
try:
    H.replace_text(p, "根本不存在", "x")
    raise SystemExit("replace_text 本该在 0 命中时抛异常")
except ValueError:
    pass
print("replace_text OK")
PY

# odt_probe 在没渲染时应当报错退出，而不是崩栈
if python3 "$HERE/odt_probe.py" "$ROOT/examples/leaf.odt" --pages 2>/dev/null; then
  echo "expected odt_probe --pages to fail without a render" >&2
  exit 1
fi

# --blocks：切开默认只警告（退出 0）；--blocks-fail 才当错误
BLK="$ROOT/examples/split-block.odt"
python3 "$HERE/check_odt.py" "$BLK" --blocks >/tmp/_blk.txt 2>&1 || {
  echo "--blocks 默认不应失败" >&2; cat /tmp/_blk.txt >&2; exit 1
}
grep -q "切开" /tmp/_blk.txt
if python3 "$HERE/check_odt.py" "$BLK" --blocks-fail >/tmp/_blkf.txt 2>&1; then
  echo "expected --blocks-fail to fail on a split block" >&2
  cat /tmp/_blkf.txt >&2
  exit 1
fi
grep -q "切开" /tmp/_blkf.txt
# 没被切开的文档不应报切开
if python3 "$HERE/check_odt.py" "$ROOT/examples/leaf.odt" --blocks 2>/dev/null | grep -q "切开"; then
  echo "--blocks 误报：leaf.odt 没有等宽块" >&2
  exit 1
fi

# --prose-space：正文 /opt/目录 必须报；leaf 没有中文贴英文，应通过
if python3 "$HERE/check_odt.py" "$BLK" --prose-space >/tmp/_psp.txt 2>&1; then
  echo "expected --prose-space to fail on /opt/目录" >&2
  cat /tmp/_psp.txt >&2
  exit 1
fi
grep -q "未空开" /tmp/_psp.txt
python3 "$HERE/check_odt.py" "$ROOT/examples/leaf.odt" --prose-space >/dev/null

# --indent：text:s 必须展开（" " + text:s c=3 → 4），不能用 itertext 量成 0
python3 "$HERE/check_odt.py" "$BLK" --indent "indented line" | grep -q "indent=4" \
  || { echo "--indent 没有展开 text:s" >&2; exit 1; }

# odt_text：省略 out 时写 stdout，且提示不污染管道
python3 "$HERE/odt_text.py" "$ROOT/examples/leaf.odt" | grep -q "A leaf paragraph." \
  || { echo "odt_text stdout 模式失效" >&2; exit 1; }
if python3 "$HERE/odt_text.py" "$ROOT/examples/leaf.odt" | grep -q " -> "; then
  echo "odt_text 的提示信息漏到了 stdout" >&2
  exit 1
fi

# clone_row / leading_spaces：多 span 模板不得残留旧文字
python3 - "$ROOT" <<'PY'
import sys
sys.path.insert(0, sys.argv[1] + "/scripts")
import odthelper as H          # 先 import 它：内部调 add_pylib()，lxml 才在 sys.path 上
from lxml import etree

TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
q = lambda t: "{%s}%s" % (TEXT, t)

# 末行被拆成两个 span 的模板（真实事故形状）
tpl = etree.Element(q("p"))
a = etree.SubElement(tpl, q("span")); a.text = "xpack.security.enabled: "
b = etree.SubElement(tpl, q("span")); b.text = "false"
row = H.clone_row(tpl, "bootstrap.memory_lock: true")
assert "".join(row.itertext()) == "bootstrap.memory_lock: true", \
    "clone_row 残留了模板 span：%r" % "".join(row.itertext())

# 缩进：" " + text:s c=4 → 5；缺 text:c 时按 1 算；无缩进为 0
p = etree.Element(q("p")); p.text = " "
s = etree.SubElement(p, q("s")); s.set(q("c"), "4"); s.tail = "x"
assert H.leading_spaces(p) == 5, H.leading_spaces(p)
p2 = etree.Element(q("p")); p2.text = " "
s2 = etree.SubElement(p2, q("s")); s2.tail = "x"
assert H.leading_spaces(p2) == 2, H.leading_spaces(p2)
assert H.leading_spaces(etree.Element(q("p"))) == 0
# 继承模板缩进
row2 = H.clone_row(p, "y")
assert H.leading_spaces(row2) == 5, H.leading_spaces(row2)
assert "".join(row2.itertext()) == "y"
print("clone_row / leading_spaces OK")
PY

echo SELFTEST_OK
