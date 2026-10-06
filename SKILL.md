---
name: odt-edit
description: 对 .odt（OpenDocument 文本）文件做外科手术式修改、质量检查和版本 diff。凡是要修改/编辑/更新 odt 文档、修复 odt 排版问题（对齐塌陷、灰色空白、空格折叠、文字翻倍）、对比两个 odt 的差异、检查 odt 内容或样式是否被改坏，都用这个技能——即使用户只说"改一下这个文档"、"这两个文档有什么区别"或"检查一下文档"。
---

# ODT 外科手术式编辑 / 检查 / Diff

目标四条：内容改对、样式零破坏、改完可验证、差异有据可查。核心原则：**只改内容节点，永不重新生成文档，不碰既有样式表。**

## 0. 环境准备（幂等，每个会话跑一次）

```bash
bash <本技能目录>/scripts/setup_env.sh
```

把 odfdo/lxml wheel 解包到 `$ODT_EDIT_PYLIB`（默认 `$TMPDIR/odt-edit-<uid>/pylibs`，无需 pip）。有 Docker 时再构建 LibreOffice 镜像。只要 Python 依赖时加 `--python-only`。镜像源、架构、工作目录见仓库 README 的 `ODT_EDIT_*`。

## 1. 修改

先看结构，再动手：

```bash
python3 <本技能目录>/scripts/outline.py 文件.odt
```

它打印正文子节点下标、标题、列表嵌套和样式名。改列表或插入小节前必须跑。修改用 odfdo 加载，**结构性操作全部走 lxml 层（`el._xml_element`）**——odfdo 包装 API 有多个坑，动手前必读 `references/gotchas.md`。

标准助手（gotchas 里有完整源码，复制即用）：

- `set_el_text(el, s)` — 只用于**叶子**标题/段落。不要用 odfdo 的 `text_content` setter。禁止对 `text:list-item` 调用：它会删掉下级 list。改编号条目的说明文字用 `set_item_label`。
- `make_p(style, text, span=None)` — 造段落。`\n`→line-break、`\t`→tab、**连续空格必须编码为 " "+`<text:s>`**（ODF 会折叠字面空格串）。原文若用 span 包等宽内容，把那个 span 的样式名传进去。
- `insert_after/insert_before(el, new)` — 基于 `xmlposition=NEXT_SIBLING/PREV_SIBLING`。
- 清批注：遍历 `//office:annotation` 与 `//office:annotation-end` 逐个 `el.delete()`；批注里的合理建议应落实为正文再删除。

规则：

- 每类修改加断言（命中数 == 预期值）；保存为**新版本文件**（vN+1），不覆盖原文件。
- 含脚注的段落不要动 `text:note` 子树，除非目标就是脚注本身。
- **新列表：deepcopy 文档里已有的同结构块**，改文字，不要从零拼 XML。点的形状由嵌套深度决定，见 gotchas「列表」。
- 标题里的 `3.2` 这类编号常常是**字面文本**，不是自动编号。插入或删除一节后，必须改后续标题，并全文搜「见 3.2」一类交叉引用。

## 2. 检查

```bash
python3 <本技能目录>/scripts/check_odt.py 新文件.odt [--forbidden 词1,词2,...]
```

必检：zip 完整性、mimetype 须为首位未压缩条目。可选：`--require-toc`、`--require-chapter-seq`、`--forbid-nbsp`。打印标题/表格/图片/批注计数，与修改前基线对照——图片数、表格数无故变化即是事故。相邻重复只提示、不因此失败。

## 3. 视觉验收 + 目录刷新

ODT 排版以 LibreOffice 渲染为准，且目录（TOC）是字段、必须由 LibreOffice 刷新：

```bash
bash <本技能目录>/scripts/render.sh 新文件.odt [页码...]   # 无页码=渲染全部
```

Docker + UNO 会刷新目录并回写 odt，再导出 PDF/PNG 到 `$ODT_EDIT_WORK`（默认 `$TMPDIR/odt-edit-<uid>/work`）。没有镜像时，若本机有 `soffice`，只导出 PDF，不刷新目录。逐页目检**被修改的页 + 抽查未修改的页**。同一 profile 的 soffice 不能并行（容器内已用独立 profile 规避）。

列表点的形状（空心圆 / 实心圆 / 方点）和缩进**只看 PNG**。`render.txt` 会在连字符处折行，`foo-bar-baz` 会变成 `foobarbaz`，不能当正文证据。`javaldx` 警告可忽略。

## 4. Diff

```bash
python3 <本技能目录>/scripts/diff_odt.py 旧文件.odt 新文件.odt 输出.diff
```

正文提取（跳过 TOC 字段、脚注安全）+ unified diff。答复用户时给摘录 + 完整 diff 文件路径。
