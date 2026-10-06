#!/usr/bin/env python3
"""UNO 脚本：加载 ODT（隐藏）、刷新布局与字段、更新全部目录索引、原地保存、导出 PDF。
在容器内运行，通过 socket 连接 soffice 监听器。
用法: python3 update_toc.py file:///tmp/doc.odt file:///work/out.pdf
"""
import sys, time, uno
from com.sun.star.beans import PropertyValue

def prop(n, v):
    p = PropertyValue(); p.Name = n; p.Value = v; return p

src, pdf = sys.argv[1], sys.argv[2]
local = uno.getComponentContext()
resolver = local.ServiceManager.createInstanceWithContext(
    "com.sun.star.bridge.UnoUrlResolver", local)
ctx = None
for _ in range(30):
    try:
        ctx = resolver.resolve(
            "uno:socket,host=127.0.0.1,port=2002;urp;StarOffice.ComponentContext")
        break
    except Exception:
        time.sleep(1)
if ctx is None:
    print("NO_CONNECT"); sys.exit(1)
desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
doc = desktop.loadComponentFromURL(src, "_blank", 0, (prop("Hidden", True),))
try:
    doc.refresh()
    try:
        doc.getTextFields().refresh()
    except Exception:
        pass
    idxs = doc.getDocumentIndexes()
    for i in range(idxs.getCount()):
        idxs.getByIndex(i).update()
    doc.refresh()
    for i in range(idxs.getCount()):
        idxs.getByIndex(i).update()
    doc.refresh()
    doc.store()
    doc.storeToURL(pdf, (prop("FilterName", "writer_pdf_Export"),))
    print("TOC_UPDATED indexes=", idxs.getCount())
finally:
    doc.close(False)
