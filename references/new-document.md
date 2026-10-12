# 新写一份 ODT

用户要新文档、工作区没有可改的 `.odt` 时走这条。已有文件要改时不要用。

不要 `odfdo.Document('text')`。默认字体没有中文，样式表是空的。

1. 复制一份已经能在 LibreOffice 里正常显示中文的 ODT 当底稿。优先同课程、同仓库里最短的那份。底稿必须已有命名样式 `Title`、`Heading_20_1`、`Text_20_body`，并且中文字体已设（例如 Noto Serif SC / Noto Sans SC）。
2. 另存为新文件名，不要改底稿。
3. 清正文：保留 `text:sequence-decls`，删掉其余 body 子节点。
4. 改 `doc.meta.set_title(...)` 和 `doc.meta.set_modification_date(...)`。
5. 可以**新增**命名段落样式。`style:parent-style-name` 只能指向已有**命名**样式，不能指向自动样式。不要改现有样式表里的属性。
6. 表格、插图用自动样式，并且只被直接引用，不当别人的 parent。
7. 首行缩进写 `fo:text-indent="0.74cm"`（约两个汉字，12pt）。不要写 `em`：LibreOffice 经常不渲染。
8. 之后按 `SKILL.md` 第 1 节改内容：outline → 助手写正文 → check → diff。
