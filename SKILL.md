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

它打印正文子节点下标、标题、列表嵌套和样式名。改列表或插入小节前必须跑。修改用 odfdo 加载，**结构性操作全部走 lxml 层（取底层元素用 `H.xml_of(el)`）**——odfdo 包装 API 有多个坑，动手前必读 `references/gotchas.md`。

样式别靠肉眼判断，先解析：

```bash
python3 <本技能目录>/scripts/odt_styles.py 文件.odt
```

它把每个段落/文字样式**解析后**的属性（字体、字号、行高、段前段后、底色、颜色）按组打印，
并标出两类事故：

- **未定义样式**：正文引用了 styles 里没有的样式，LibreOffice 静默回落到默认样式。
- **继承断裂**：`style:parent-style-name` 指向**自动样式**。LibreOffice 不认这种继承，
  上游的字体、底色、行高会整个丢掉，而 XML 看起来完全正常。

`--resolve 样式名` 打印单个样式的继承链和"期望 vs 实际"；`--warn-only` 只报风险，可进 CI。

标准助手在模块里，`import` 用，不要从文档里复制——副本会各自漂移（同一轮任务里 `make_p` 改过 3 次，
3 个副本各带一半的修复）：

```python
import sys
sys.path.insert(0, "<本技能目录>/scripts")
import odthelper as H

doc = H.load("文件.odt")
el = doc.body.children[12]
H.replace_text(el, "旧措辞", "新措辞")
H.insert_after(el, H.make_p("TBMCode", "soffice --headless"))
doc.save("新文件.odt")
```

- `replace_text(el, old, new, expect=1)` — 改已有文字的首选：只动文字槽，span、书签、`text:soft-page-break` 全部保留，命中数不等于 `expect` 就抛异常。
- `set_el_text(el, s)` — 只用于**叶子**标题/段落（它会把段内结构抹平）。不要用 odfdo 的 `text_content` setter。禁止对 `text:list-item` 调用（会抛 `ValueError`）：它会删掉下级 list。改编号条目的说明文字用 `set_item_label`。
- `make_p(style, text, span=None)` — 造段落。`\n`→line-break、`\t`→tab、**连续空格必须编码为 " "+`<text:s text:c="n-1"/>`**（ODF 会折叠字面空格串）。原文若用 span 包等宽内容，把那个 span 的样式名传进去。
- `insert_after/insert_before(el, new)` — 基于 `xmlposition=NEXT_SIBLING/PREV_SIBLING`，参照物是调用者自身。
- `make_h(level, text, style)` — odfdo 的 `Header` 会丢 style，这个助手补回来。
- `clone_row(tpl, text, indent=None)` — 以已有段落为模板造一行，段落样式跟着模板。**往文件内容块或文本框里追行时用它**：模板末行常被拆成多个 span，只替换首个 span 的写法会残留旧文字（`… : true false`）。`indent=None` 沿用模板的前导缩进。
- `leading_spaces(el)` — 段落的前导空格数，`<text:s text:c="n"/>` 按 n 展开。**量缩进必须用它**：`itertext()` 与 `text_recursive` 都不展开 `text:s`，结果恒为 0。
- `clear_content(el)` — 清空内容（子节点 + `.text`），保留属性（样式名等）。

各函数的语义与限制见 `references/gotchas.md` 的对照表。
- 清批注：遍历 `//office:annotation` 与 `//office:annotation-end` 逐个 `el.delete()`；批注里的合理建议应落实为正文再删除。

规则：

- 每类修改加断言（命中数 == 预期值）；保存为**新版本文件**（vN+1），不覆盖原文件。
- 版本号常常不止写在文件名里，`meta.xml` 的 `dc:title` 里也有一份。出新版两处一起改：`doc.meta.set_title(...)`、`doc.meta.set_modification_date(...)`。
- 一轮改动做完再刷新目录。LibreOffice 重存会重命名自动样式，之后再按样式名打补丁就对不上了；宁可回到上一版把改动一次做完。
- 含脚注的段落不要动 `text:note` 子树，除非目标就是脚注本身。
- **新列表：deepcopy 文档里已有的同结构块**，改文字，不要从零拼 XML。点的形状由嵌套深度决定，见 gotchas「列表」。
- 标题里的 `3.2` 这类编号常常是**字面文本**，不是自动编号。插入或删除一节后，必须改后续标题，并全文搜「见 3.2」一类交叉引用。

## 2. 检查

```bash
python3 <本技能目录>/scripts/check_odt.py 新文件.odt [--forbidden 词1,词2,...]
```

必检：zip 完整性、mimetype 须为首位未压缩条目。可选：`--require-toc`、`--require-chapter-seq`、`--forbid-nbsp`。打印标题/表格/图片/批注计数，与修改前基线对照——图片数、表格数无故变化即是事故。相邻重复只提示、不因此失败。

样式诊断（动过样式就必跑，退出码非 0 表示有未定义样式或继承断裂）：

```bash
python3 <本技能目录>/scripts/odt_styles.py 新文件.odt --warn-only
python3 <本技能目录>/scripts/check_odt.py 新文件.odt --font-audit          # 只看 XML，很快
python3 <本技能目录>/scripts/check_odt.py 新文件.odt --font-audit --render # 还要核对渲染
python3 <本技能目录>/scripts/check_odt.py 新文件.odt --toc-pages           # 目录页码 vs 渲染分页
```

块结构与对齐（纯文本层看不见的那一类，动过代码块或等宽内容就必跑）：

```bash
python3 <本技能目录>/scripts/check_odt.py 新文件.odt --blocks
python3 <本技能目录>/scripts/check_odt.py 新文件.odt --indent "<name>dfs.blocksize</name>"
```

- `--blocks`：把正文切成连续等宽块，列出「章节 / 行数 / 首行」，并报出**被非等宽行切开**的块。
  往已有的文件内容块后面追行时，中间插了一句引导语就会切成两段——XML 看着完全正常，
  渲染上是灰底断带。编号步骤句（`3. …`、`（3）…`）视为合法分隔，不报。
- `--indent`：打印匹配段落的前导空格数（展开 `text:s`）与样式名，可重复传多个。
  `diff_odt.py`、`odt_text.py`、`render.txt` 都不展开 `text:s`：等宽行的对齐在纯文本层完全看不见，
  改错了也看不出来。

**为什么必须有这一项**：zip、目录、章节号全过，样式仍可能整段失效。
`check_odt.py` 的其余检查全是结构性和文本性的，一条也发现不了"样式没生效"。
实际发生过：文档输出 PASS，而一行配置渲染成 12pt 衬线体、没有灰底。

`--font-audit` 查未定义样式和继承断裂（约 1 秒）。
`--render` 另外核对渲染产物：等宽字体种类数、等宽字体的近重复字号、近重复颜色、
以及「样式声明的底色在渲染里是否真的出现」（约 6 秒，需先跑 `render.sh`）。

## 3. 视觉验收 + 目录刷新

ODT 排版以 LibreOffice 渲染为准。默认**只读源文件，绝不回写**：

```bash
bash <本技能目录>/scripts/render.sh 新文件.odt [页码...]   # 无页码=渲染全部
bash <本技能目录>/scripts/render.sh 新文件.odt --refresh-toc  # 刷新目录字段并回写 odt
```

输出落在 `$ODT_EDIT_WORK/<文件名去扩展>/`（默认 `$TMPDIR/odt-edit-<uid>/work`）：
`render.pdf`、`render.txt`、`pages/p-NN.png`。按文件名分目录，多版本不会互相覆盖。

**为什么默认不回写**：回写会让 LibreOffice 重存文档并重命名全部自动样式
（`TBMCode` → `P123` 之类），之后按样式名做的任何处理都会失效。文档没有 TOC 字段时，
刷新是空操作，回写纯属风险。只有确实需要刷新目录字段时才加 `--refresh-toc`。

每次运行都会打印 `PDF: 重新转换` 或 `PDF: 复用…`：改完文档却看到「复用」，说明容器时钟有偏差，加 `--force`。刷新目录后 `check_odt.py --toc-pages` 仍报漂移时，按 gotchas「目录页码可能不收敛」回填数字。

逐页目检**被修改的页 + 抽查未修改的页**。同一 profile 的 soffice 不能并行（容器内已用独立 profile 规避）。逐页比对渲染图能一次点出所有实际变化页：

```bash
for f in $OLD/pages/*.png; do cmp -s "$f" "$NEW/pages/$(basename "$f")" || echo "DIFF $(basename "$f")"; done
```

光看 XML 判断不了渲染结果。字体被替换、底色少一行、同一行里混两种字体——查渲染产物：

```bash
python3 <本技能目录>/scripts/odt_probe.py 新文件.odt --fonts
python3 <本技能目录>/scripts/odt_probe.py 新文件.odt --page-of "某段文字"
python3 <本技能目录>/scripts/odt_probe.py 新文件.odt --bg 700 100 600 --page 11
python3 <本技能目录>/scripts/odt_probe.py 新文件.odt --crop 85 470 330 500 --scale 4 --page 11
```

- `--fonts`：PDF 里实际用到的 (字体, 字号, 颜色) 及字符数。**同一行内出现两个等宽字体编号 = 有片段掉回正文样式**。
- `--bg`：某列像素的背景色连续段。验证底色有没有盖满整块（"灰底少一行"就是这么查出来的）。
- `--crop`：裁剪放大成 PNG，看字形。判断"是不是两种字体"时放大 4 倍最直观。
- `--page-of`：文字在第几页，不靠文件名猜。加 `--quiet` 只输出页码（一行一个），便于管道解析。

列表点的形状（空心圆 / 实心圆 / 方点）和缩进**只看 PNG**。`render.txt` 的折行与去连字符陷阱见 `references/gotchas.md`「渲染产物」——它会吞掉行尾的 `-`，看起来像文档丢了字符。`render.layout.txt`（`pdftotext -layout`）保留折行，怀疑丢字时先看它，再查 XML。`javaldx` 警告可忽略。

## 4. Diff

```bash
python3 <本技能目录>/scripts/diff_odt.py 旧文件.odt 新文件.odt 输出.diff
python3 <本技能目录>/scripts/diff_odt.py 旧文件.odt 新文件.odt 输出.diff --styles
```

正文提取（跳过 TOC 字段、脚注安全）+ unified diff。答复用户时给摘录 + 完整 diff 文件路径。

**只改样式的版本一定加 `--styles`。** 字号、行高、底色、颜色、字体继承这类改动，
正文 diff 会是 `0 hunks`，看起来"没改动"。`--styles` 输出按属性分组的样式表差异，
还会把未定义样式和继承断裂列在最前面。

默认保留空段落（输出空行）。不保留的话，diff 会显示"凭空少了几行"——
文档里空段落一个没少，是提取时被丢掉了。要旧行为加 `--no-blanks`。
