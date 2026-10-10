#!/usr/bin/env python3
"""可 import 的编辑助手。以前这些函数只存在于 references/gotchas.md 的代码块里，
每做一次任务就复制一份，副本会各自漂移。现在这里是唯一真源。

用法：

    import sys, os
    sys.path.insert(0, "<本技能目录>/scripts")
    import odthelper as H

    doc = H.load("文件.odt")
    el = doc.body.children[12]
    H.set_el_text(el, "新标题")
    H.insert_after(el, H.make_p("TBMCode", "soffice --headless"))
    doc.save("新文件.odt")

全部结构性操作都走 lxml 层（`el._xml_element`）。理由见 references/gotchas.md。
"""
import copy
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import require_deps  # noqa: E402

require_deps()

from lxml import etree  # noqa: E402
from odfdo import Header, Paragraph  # noqa: E402

TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
A_STYLE = "{%s}style-name" % TEXT


def load(path):
    """打开 ODT。返回 odfdo Document。"""
    from odfdo import Document
    return Document(path)


def safe_t(el):
    """读文本。text_recursive 对含脚注/目录的节点会抛异常，这里吞掉返回 ""。"""
    try:
        return el.text_recursive
    except Exception:
        return ""


def xml_of(el):
    """拿到底层 lxml 元素。odfdo 包装对象和 lxml 元素都能传。

    必须先试 `_xml_element`：odfdo 元素**也有** `.tag` 属性（返回标签名），
    按 `hasattr(el, "tag")` 判断会永远拿到包装对象，再调 `.find()` 就报 AttributeError。
    """
    x = getattr(el, "_xml_element", None)
    return x if x is not None else el


_xml = xml_of  # 旧名字，文档里用过


def set_el_text(el, s):
    """清空子元素后写纯文本（保留样式属性与 outline-level）。

    会丢失书签/span，也会删掉下级 list。只用于叶子 text:p / text:h，
    禁止传入 text:list-item —— 用 set_item_label。
    TOC 引用的书签由 LibreOffice 刷新目录时重建。
    """
    x = xml_of(el)
    if etree.QName(x).localname == "list-item":
        raise ValueError("set_el_text 不能用于 list-item，改用 set_item_label")
    for ch in list(x):
        x.remove(ch)
    x.text = s


def set_item_label(item, s):
    """只改 list-item 里第一个 text:p 的文字，保留其后的下级 list。"""
    x = xml_of(item)
    p = x.find("{%s}p" % TEXT)
    if p is None:
        raise ValueError("list-item 没有 text:p")
    set_el_text(p, s)


def _emit(host, s):
    """把 s 追加到 host 的文字流末尾（无子节点时写 .text，否则写末子节点的 .tail）。"""
    if len(host):
        host[-1].tail = (host[-1].tail or "") + s
    else:
        host.text = (host.text or "") + s


def _append(host, s):
    """追加文字。连续空格写成 " " + <text:s text:c="n-1"/>，
    否则 ODF 解析时会被折叠成一个空格。
    """
    for seg in re.split(r"( {2,})", s):
        if not seg:
            continue
        if set(seg) == {" "}:
            _emit(host, " ")
            sp = host.makeelement("{%s}s" % TEXT, {"{%s}c" % TEXT: str(len(seg) - 1)})
            host.append(sp)
        else:
            _emit(host, seg)


def leading_spaces(el):
    """段落的前导空格数，<text:s text:c="n"/> 按 n 个空格展开。

    不要用 text_recursive 或 "".join(el.itertext()) 量缩进：它们不展开 text:s，
    结果恒为 0。等宽行的对齐就是靠 text:s 实现的，缩进在纯文本层看不见。
    也别只数第一个 text:s —— 缺 text:c 属性时要按 1 个空格算。
    """
    x = xml_of(el)

    def feed(t):
        st = t.lstrip(" ")
        return len(t) - len(st), not st

    n = 0
    if x.text:
        k, still_blank = feed(x.text)
        n += k
        if not still_blank:
            return n
    for child in x:
        if not isinstance(child.tag, str):
            continue
        if etree.QName(child).localname != "s":
            return n
        c = child.get("{%s}c" % TEXT)
        n += int(c) if (c or "").isdigit() else 1
        if child.tail:
            k, still_blank = feed(child.tail)
            n += k
            if not still_blank:
                return n
    return n


def clear_content(el):
    """清空元素内容：删掉全部子节点并把 .text 置空，保留属性（样式名等）。"""
    x = xml_of(el)
    for ch in list(x):
        x.remove(ch)
    x.text = None
    return el


def clone_row(tpl, text, indent=None):
    """以 tpl 为模板造一行：段落样式跟着 tpl，正文换成 text。

    indent=None 沿用 tpl 的前导缩进；给数字则用该空格数（仍用 text:s 编码）。
    返回 lxml 元素，可直接交给 insert_after 或 append 到 text-box。

    为什么必须先清空再写：模板末行常被拆成多个 span（如 yml 的
    "xpack.security.enabled: false"），只替换首个 span 的写法会残留旧文字，
    渲染出 "bootstrap.memory_lock: true false"。
    """
    x = copy.deepcopy(xml_of(tpl))
    n = leading_spaces(x) if indent is None else indent
    clear_content(x)
    if n:
        sp = etree.SubElement(x, "{%s}s" % TEXT)
        sp.set("{%s}c" % TEXT, str(n))
    _append(x, text)
    return x


def make_p(style, text, span=None):
    """造段落：\\n→line-break，\\t→tab，连续空格→" "+text:s。

    span 给定时内容整体包进该 span（等宽行复制原文的 span 样式名）。
    """
    p = Paragraph(style=style)
    x = p._xml_element
    host = x
    if span:
        sp = x.makeelement("{%s}span" % TEXT, {A_STYLE: span})
        x.append(sp)
        host = sp

    for li, line in enumerate(text.split("\n")):
        if li:
            host.append(host.makeelement("{%s}line-break" % TEXT, {}))
        for pi, part in enumerate(line.split("\t")):
            if pi:
                host.append(host.makeelement("{%s}tab" % TEXT, {}))
            _append(host, part)
    return p


def make_h(level, text, style):
    """造标题。odfdo 的 Header 会丢 style，这里补回来。"""
    h = Header(level=level, text=text)
    h._xml_element.set(A_STYLE, style)
    return h


def insert_after(el, new):
    """按参照元素插入。el 与 new 都可以是 odfdo 包装对象或裸 lxml 元素
    （build 脚本里找出来的段落就是 lxml 元素，以前传进来会报没有 .insert）。
    """
    xml_of(el).addnext(getattr(new, "_xml_element", new))


def insert_before(el, new):
    xml_of(el).addprevious(getattr(new, "_xml_element", new))


def set_style(el, style):
    """改段落/span 的样式名。"""
    xml_of(el).set(A_STYLE, style)


def replace_text(el, old, new, expect=1):
    """在元素及其后代里做定点文字替换，命中数不符就抛 ValueError。

    比 set_el_text 安全：只改文字槽，span / 书签 / soft-page-break 等结构原样保留。
    改已有段落优先用它，不要整段重写。

    注意 lxml 的 iter() 会先给出元素自身，而自身的 .tail 属于父元素之后的文字，
    动它会改到兄弟节点外面去，所以根节点只取 .text。
    """
    x = xml_of(el)
    hits = 0
    first = True
    for n in x.iter():
        attrs = ("text",) if first else ("text", "tail")
        first = False
        for attr in attrs:
            v = getattr(n, attr)
            if v and old in v:
                hits += v.count(old)
                setattr(n, attr, v.replace(old, new))
    if hits != expect:
        raise ValueError("replace_text: %r 命中 %d 处，期望 %d 处"
                         % (old[:40], hits, expect))
    return hits
