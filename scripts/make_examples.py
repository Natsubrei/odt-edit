#!/usr/bin/env python3
"""Write three tiny fixture ODT files under examples/."""
import os, zipfile, io

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "examples")
FIXED_DATE = (2024, 1, 1, 0, 0, 0)

CONTENT = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
 xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
 office:version="1.3">
  <office:body><office:text>
{body}
  </office:text></office:body>
</office:document-content>
"""
STYLES = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" office:version="1.3">
  <office:styles/>
  <office:automatic-styles/>
  <office:master-styles/>
</office:document-styles>
"""
META = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:dc="http://purl.org/dc/elements/1.1/" office:version="1.3">
  <office:meta><dc:title>{title}</dc:title></office:meta>
</office:document-meta>
"""
MANIFEST = """<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.3">
  <manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/>
  <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
  <manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>
  <manifest:file-entry manifest:full-path="meta.xml" manifest:media-type="text/xml"/>
</manifest:manifest>
"""

BODIES = {
    "leaf.odt": (
        "leaf",
        """<text:h text:outline-level="1">Title</text:h>
<text:p>A leaf paragraph.</text:p>""",
    ),
    "nested-list.odt": (
        "nested-list",
        """<text:h text:outline-level="1">Notes</text:h>
<text:list>
  <text:list-item>
    <text:p>First</text:p>
    <text:list>
      <text:list-item><text:p>Nested item</text:p></text:list-item>
    </text:list>
  </text:list-item>
  <text:list-item>
    <text:p>Second</text:p>
  </text:list-item>
</text:list>""",
    ),
    "no-toc.odt": (
        "no-toc",
        """<text:h text:outline-level="1">Plain</text:h>
<text:p>This file has no table of contents.</text:p>""",
    ),
}


def write_odt(path, title, body):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        zi = zipfile.ZipInfo("mimetype")
        zi.compress_type = zipfile.ZIP_STORED
        zi.date_time = FIXED_DATE
        z.writestr(zi, "application/vnd.oasis.opendocument.text")
        for name, data in (("META-INF/manifest.xml", MANIFEST),
                           ("content.xml", CONTENT.format(body=body)),
                           ("styles.xml", STYLES),
                           ("meta.xml", META.format(title=title))):
            # 固定 date_time：否则每次跑 selftest 都用当前时间，examples/*.odt 平白变成“已修改”
            info = zipfile.ZipInfo(name)
            info.date_time = FIXED_DATE
            z.writestr(info, data)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, (title, body) in BODIES.items():
        p = os.path.join(OUT, name)
        write_odt(p, title, body)
        print("wrote", p)


if __name__ == "__main__":
    main()
