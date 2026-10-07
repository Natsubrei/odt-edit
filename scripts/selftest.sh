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

# --render 在没渲染时应当报错退出，而不是崩栈
if python3 "$HERE/check_odt.py" "$ROOT/examples/leaf.odt" --render >/dev/null 2>&1; then
  echo "expected --render to fail without a render" >&2
  exit 1
fi

# odt_probe 在没渲染时应当报错退出，而不是崩栈
if python3 "$HERE/odt_probe.py" "$ROOT/examples/leaf.odt" --pages 2>/dev/null; then
  echo "expected odt_probe --pages to fail without a render" >&2
  exit 1
fi
echo SELFTEST_OK
