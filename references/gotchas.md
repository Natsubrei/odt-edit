# ODT 编辑陷阱清单（每一条都踩过实战坑）

## odfdo API 陷阱

1. **`Paragraph(text=...)` 是错的**。构造参数名是 `text_or_element`，传 `text=` 会落进 `**kwargs` 被静默忽略，得到**空段落**。用位置参数：`Paragraph("文本", style="P12")`。
2. **`Header(level, text, style)` 会丢弃 style**。创建后手动补：`h._xml_element.set("{text-ns}style-name", style)`（text-ns = `urn:oasis:names:tc:opendocument:xmlns:text:1.0`）。
3. **没有 `getparent()`**。用 `el.parent`；删除用 `el.delete()`（自动保留 tail）；插入用 `el.insert(new, xmlposition=NEXT_SIBLING/PREV_SIBLING)`——参照物是**调用者自身**，不是父节点。
4. **`list.index(odfdo元素)` 不可靠**（包装对象身份问题）。用 `el._xml_element.getparent().index(el._xml_element)`。
5. **`text_content` setter 是给单元格/文本框用的**。对 text:p/text:h 使用时它会把新文本包成内嵌 `<text:p>` 插进去而不删旧内容 → **文本翻倍**。改叶子段落用 `set_el_text`；改带下级 list 的条目用 `set_item_label`。
6. **`el.text_recursive` 可能抛异常**：对含脚注的列表、TOC 触发 odfdo 内部 KeyError('footnote')。所有遍历读取都要 try/except 包裹；能跳过 `text:list`、`text:table-of-content`、`table:table`、`text:note` 就跳过。
7. **保存前 LibreOffice 会重编号自动样式**（P12→P10 之类）。不要对保存后的文件硬编码样式名做二次处理；比对样式用 styles.xml 的**样式名集合**，不比个数以外的细节。
8. **现成 `Heading_20_2` 常把「5.」和后面的字拆在不同 span 里。** 改标题用 `set_el_text` 整段换成纯文本即可，不必保留那些 span。
9. **章节号是死文字。** `3.2 安装` 不会因插入新节自动变成 `3.3`。插入/删除带数字的小节后：改后续标题，并搜「见 3.2」「（见3.」这类交叉引用。

## 标准助手（import，不要复制）

以前这里是源码，要求复制进临时脚本。副本会各自漂移：同一轮任务里 `make_p` 改过 3 次，
3 个副本各带一半的修复。现在是 `scripts/odthelper.py`，唯一真源。

```python
import sys
sys.path.insert(0, "<本技能目录>/scripts")
import odthelper as H

doc = H.load("文件.odt")
el = doc.body.children[12]
H.set_el_text(el, "新标题")
H.insert_after(el, H.make_p("TBMCode", "soffice --headless --convert-to pdf"))
doc.save("新文件.odt")
```

| 助手 | 作用 | 限制 |
|---|---|---|
| `load(path)` | 打开 ODT | |
| `safe_t(el)` | 读文本，吞掉 `text_recursive` 的异常 | 含脚注/目录的节点返回 `""` |
| `set_el_text(el, s)` | 清空子元素后写纯文本 | 只用于叶子 `text:p`/`text:h`；**传 `text:list-item` 会抛 ValueError** |
| `set_item_label(item, s)` | 只改 list-item 的首个 p，保留下级 list | |
| `make_p(style, text, span=None)` | 造段落：`\n`→line-break，`\t`→tab，连续空格→`text:s` | 等宽行要传原文档的 span 样式名 |
| `make_h(level, text, style)` | 造标题并补回 style | odfdo 的 `Header` 会丢 style |
| `insert_after` / `insert_before(el, new)` | 按参照元素插入 | 参照物是 `el` 自身，不是父节点 |
| `set_style(el, style)` | 改段落/span 的样式名 | |

两条不看代码就不知道的语义：

- **`set_el_text` 会丢书签和 span。** TOC 引用的书签由 LibreOffice 刷新目录时重建，可以接受。
- **`make_p` 里连续空格必须写成 `" "` + `<text:s text:c="n-1"/>`**，否则解析时被折叠成一个空格。
  这一条旧版只写在注释里、代码没实现，等宽行里的对齐空格会静默塌掉。

## 列表

LibreOffice 用**嵌套深度**决定点的形状（例如 1 级实心圆、2 级空心圆、3 级方点），不是用 list 的 `text:style-name` 单独决定。同名 `L5` 套深一层，点就会变。

三种写法效果不同：

1. **编号 list 后面再跟一个兄弟 list**（旧文档常见）：LO 把后一个 list 当成前一个的续写，下级点往往是空心圆。
2. **编号 list-item 里面再嵌一个 list**（正确的 XML 嵌套）：下级点也是空心圆，但必须是「item 的 p + 同级的 list」，不要再套一层。
3. **多套一层 list**（搬节点时把整个旧下级 list 再包一层塞进 item）：点升一级，变成方点或实心圆。看起来像「列表高了一级」。

搬列表前先拆平多余内层：目标形态是

```
text:list                    <!-- 编号 -->
  text:list-item
    text:p                   注意事项：
    text:list                <!-- 下级圆点 -->
      text:list-item / text:p   一条说明
```

**不要**对带下级 list 的 `list-item` 做 `set_el_text`。只改它的第一个 `text:p`。

新的「标题句 + 下级条目」块：`copy.deepcopy` 文档里已有的同结构 list，改各条 `text:p`。不要从零拼 list-item。克隆必须在 LibreOffice 重存之前做——重存后自动样式名会变。

## 空格规则（排版对齐的生死线）

- **字面连续空格会被折叠成单个**（LibreOffice 导入即折叠）。要对齐必须编码为 `" " + <text:s text:c="N-1"/>`（N 是总宽度）。长文档里大量 `text:s` 是常态。
- **NBSP（U+00A0）不折叠**，所以老文档常用它做缩进对齐——但多数编辑器会把 NBSP 标成灰色底纹（用户看到的"灰色空白"就是它）。修复 = NBSP 串 → `" "+text:s`。
- **修空格的重建函数必须"进入即清源"**：先清掉原 text/tail 再重写，否则重写内容追加在原文之后 → **文本翻倍**（真实事故：树行内容全部双写）。重建后要单遍校验：折叠空白后正则扫 `(.{6,}?)\1`，命中为真重复。
- 等宽/对齐行的正确形态：原文用的那个段落样式 + 原文用的 span 样式包住全部内容 + `text:s` 空格。漏掉 span 会导致比例字体渲染、框线对不齐。以该文档已有的样式名为准。
- 修复空格的遍历只处理含 NBSP 的文本节点即可；**不要顺手把全文档的字面双空格也转成 text:s**——那会改变未审查区域的渲染行为。

## 检查规则

- 相邻重复文本扫描必须**先折叠空白**再正则，否则对齐空格串全命中（纯误报）。
- 残留词检查跳过 TOC 子树（TOC 是历史字段，刷新后自然更新）。
- 全文 NBSP 计数预期为 0（归一化完成后）；任何 >0 都是回归。

## 渲染 / LibreOffice

- **同 profile 的 soffice 不能并行**；容器里用 `-env:UserInstallation=file:///tmp/loprof` 隔离。
- 目录刷新走 UNO：loadComponentFromURL(Hidden) → `doc.refresh()` → `getTextFields().refresh()` → 逐个 `getDocumentIndexes().update()` → 再 `refresh()`+`update()` 一轮 → `store()`。只 update 不 refresh 页码不准。
- LibreOffice 重存后会**重命名全部自动样式**（P12→P10 级别），并在 styles.xml 里追加字体声明——这是正常现象，不是样式丢失；判定样式丢失要比对样式名集合差集。
- 中文渲染必须装 `fonts-noto-cjk`，否则全是豆腐块。
- 定位"某内容在第几页"：`pdftotext` 输出按 `\f` 分页后查找，不要按 PNG 文件名猜。
- **列表点的形状和缩进只看 PNG。** `pdftotext` 会在连字符处折行：`foo-bar-baz` 在 `render.txt` 里会变成 `foobarbaz`。不要根据 txt 判断正文被改坏。
- `javaldx` / java 警告可忽略。
- Docker 构建：默认走官方 Debian 源。换镜像源设 `ODT_EDIT_APT_MIRROR`。宿主代理是 `127.0.0.1` 时，容器 bridge 网络连不上，设 `ODT_EDIT_DOCKER_NETWORK=host`。

## 样式继承与渲染（最贵的两条）

**LibreOffice 不把「自动样式」当作可继承的 `style:parent-style-name`。**

`office:automatic-styles`（content.xml 里的自动样式）不能作为父样式被继承。
写了也不报错，继承静默失败，上游的文字属性、段落属性**整个丢掉**，
回落到文档默认样式（通常是 12pt 衬线体）。

事故形态（都真实发生过）：

- 段落样式 `A` 有字体，`B` 的父样式指向 `A`（自动样式），`B` 只声明了底色
  → `B` 里的文字是默认衬线体，但**底色正常**。看起来像"字体没统一"。
- `B` 的文字被 span 包住时，span 自带字体 → **同一行里两种字体**。
- `End` 变体（只加段后间距）的父样式指向主样式 → 底色丢一行，
  块末行露在白底外面。当时误判成"`fo:background-color` 不继承"，
  其实根因是这条继承整条都没生效。

**修法：每个样式写全自己的属性，不要靠继承。** 需要"主样式 + 变体"时，
变体也把字体、行高、底色全部重写一遍。

**`fo:font-family` 会盖过 `style:font-name`。** 只查 `style:font-name` 会漏判：
有的 span 写的是 `fo:font-family="'Noto Serif SC'"` + `fo:font-size="9pt"`，
字面上没有 `style:font-name`，按"等宽字体"筛选时会被跳过。
归一化时要把 `font-family*`、`font-pitch*` 删掉，再显式写 `style:font-name`。

**排查口诀**：渲染和 XML 不一致时，先怀疑自动样式继承，再对字体编号。

```bash
python3 scripts/odt_styles.py 文件.odt --warn-only     # 继承断裂 + 未定义样式
python3 scripts/odt_styles.py 文件.odt --resolve 样式名 # 期望 vs 实际
bash   scripts/render.sh 文件.odt
python3 scripts/odt_probe.py 文件.odt --fonts          # 同一行两个等宽字体编号 = 掉回默认
python3 scripts/odt_probe.py 文件.odt --crop X0 Y0 X1 Y1 --scale 4 --page N
```

**未定义样式也不会报错。** 正文引用 styles 里不存在的样式名（例如改名时漏改一处），
LibreOffice 静默回落到默认样式。`odt_styles.py --warn-only` 会列出来，退出码非 0。

## 渲染产物

- `render.sh` 默认**不回写源文件**。加 `--refresh-toc` 才回写。
  回写 = LibreOffice 重存 = 全部自动样式改名（`TBMCode` → `P123`），
  之后按样式名做的处理全部失效。
- 输出在 `$ODT_EDIT_WORK/<文件名去扩展>/`：`render.pdf`、`render.txt`、`pages/p-NN.png`。
- `render.sh` 的 poppler 步骤（pdftotext/pdftoppm/pdfinfo）在宿主缺失时会自动进容器；
  以前宿主没装 poppler 时这一步会静默失败。
- 背景色、字号、同一行是否混字体，只信 `odt_probe.py` 的结果，不要靠肉眼。
