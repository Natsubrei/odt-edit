---
name: odt-edit
description: Surgical edit, quality check, and version diff for .odt (OpenDocument Text) files. Use when the user wants to modify, inspect, or compare an ODT document, or to fix layout (alignment collapse, grey gaps, space folding, doubled text).
---

# Surgical ODT edit / check / diff

Four goals: correct content, no style damage, verifiable result, evidence of the diff. **Change content nodes only. Never rebuild the document. Do not touch the existing style sheet.**

## 0. Environment (idempotent, once per session)

```bash
bash <skill-dir>/scripts/setup_env.sh
```

Unpacks odfdo/lxml wheels into `$ODT_EDIT_PYLIB` (no pip). Optionally builds a LibreOffice image. `--python-only` skips Docker. See README for mirrors, architecture, and `ODT_EDIT_*` variables.

## 1. Edit

Inspect structure first:

```bash
python3 <skill-dir>/scripts/outline.py file.odt
```

It prints body-child indexes, headings, list nesting, and style names. Run it before changing lists or inserting a section. Load with odfdo; **do all structural work on the lxml layer (`H.xml_of(el)`)**. Read `references/gotchas.md` before coding.

Never judge styles by eye. Resolve them:

```bash
python3 <skill-dir>/scripts/odt_styles.py file.odt
```

It prints the **resolved** properties (font, size, line height, margins, background, colour)
grouped per style, and flags two failure classes:

- **Undefined style** — the body references a style that does not exist; LibreOffice falls back silently.
- **Broken inheritance** — `style:parent-style-name` points at an *automatic* style.
  LibreOffice ignores that link, so inherited font, background, and line height are dropped
  while the XML still looks correct.

`--resolve NAME` prints one style's chain plus expected-vs-actual. `--warn-only` reports risks only (CI-friendly).

Helpers are a module. Import them; do not copy them out of the docs:

```python
import sys
sys.path.insert(0, "<skill-dir>/scripts")
import odthelper as H

doc = H.load("file.odt")
el = doc.body.children[12]
H.replace_text(el, "old wording", "new wording")
H.insert_after(el, H.make_p("TBMCode", "soffice --headless"))
doc.save("new.odt")
```

- `replace_text(el, old, new, expect=1)` — the default for editing existing text: it only touches text slots, so spans, bookmarks and `text:soft-page-break` survive. Raises when the hit count differs from `expect`.
- `set_el_text(el, s)` — leaf heading/paragraph only (it flattens the paragraph's structure). Do not use odfdo `text_content`. **Raises ValueError on `text:list-item`** (it deletes nested lists). Use `set_item_label` for a numbered item.
- `make_p(style, text, span=None)` — `\n`→line-break, `\t`→tab, consecutive spaces as `" "` + `<text:s text:c="n-1"/>`. If the original wraps monospaced text in a span, pass that span style name.
- `insert_after` / `insert_before` — `xml_of(el).addnext/addprevious`. `el` and `new` may be odfdo objects or raw lxml elements.
- `make_h(level, text, style)` — odfdo `Header` drops the style; this puts it back.
- `clone_row(tpl, text, indent=None)` — build a line from an existing paragraph as template (the paragraph style follows the template). **Use it when appending rows to a file-content block or text box**: the template's last line is often split across several spans, and helpers that replace only the first span leave the old text behind (`… : true false`). `indent=None` keeps the template's indent.
- `leading_spaces(el)` — leading spaces, `<text:s text:c="n"/>` expanded. **Always use it to measure indent**: neither `itertext()` nor `text_recursive` expands `text:s`, so they always read 0.
- `clear_content(el)` — drop children and `.text`, keep attributes (style name).
- `drop_row(el)` — delete one row paragraph. **If the removed row carries a `*End` paragraph style, the style moves to the new last row** (otherwise the block loses its closing edge).

Semantics and limits of each helper: see the table in `references/gotchas.md`.
- Remove comments: delete `//office:annotation` and `//office:annotation-end`. Apply useful comment text to the body first.

Rules:

- Assert hit counts per change class. Save as **vN+1**, do not overwrite the original.
- A version number often sits in two places: the file name and `dc:title` in `meta.xml`. Update both: `doc.meta.set_title(...)`, `doc.meta.set_modification_date(...)`.
- Finish every edit before refreshing the TOC. A LibreOffice re-save renames automatic styles, so patches keyed on style names stop matching afterwards.
- Do not touch a `text:note` subtree unless the footnote itself is the target.
- **New lists: deepcopy an existing same-shape block** and change the strings. Bullet glyphs follow nesting depth (see gotchas “Lists”).
- Numbers like `3.2` in headings are often **literal text**, not automatic numbering. After insert/delete, retitle later headings and search cross-references such as “see 3.2”.

## 2. Check

```bash
python3 <skill-dir>/scripts/check_odt.py new.odt [--forbidden w1,w2]
```

Always: zip integrity and mimetype (must be first, uncompressed). Optional: `--require-toc`, `--require-chapter-seq`, `--forbid-nbsp`. Compare table/image counts with the pre-edit baseline.

Advisory output (`note:`, `adjacent-repeat hints`) goes to stderr, so stdout stays greppable: summary lines, `  - ` failure details, `PASS`/`FAIL`.

Style diagnosis (mandatory once you touched styles; non-zero exit means undefined styles or broken inheritance):

```bash
python3 <skill-dir>/scripts/odt_styles.py new.odt --warn-only
python3 <skill-dir>/scripts/check_odt.py new.odt --font-audit           # XML only, fast
python3 <skill-dir>/scripts/check_odt.py new.odt --font-audit --render  # also check the render
python3 <skill-dir>/scripts/check_odt.py new.odt --toc-pages            # TOC numbers vs real pagination
```

Block structure and alignment (invisible to plain text extraction; run it after touching any code block):

```bash
python3 <skill-dir>/scripts/check_odt.py new.odt --blocks
python3 <skill-dir>/scripts/check_odt.py new.odt --blocks-fail
python3 <skill-dir>/scripts/check_odt.py new.odt --blocks-summary
python3 <skill-dir>/scripts/check_odt.py new.odt --prose-space
python3 <skill-dir>/scripts/check_odt.py new.odt --indent "<name>dfs.blocksize</name>"
```

- `--blocks`: lists contiguous monospaced blocks. Splits are **notes** (exit 0) by default — a lead-in
  sentence between two file snippets is often legitimate. Pass `--blocks-fail` to treat splits as errors.
  Numbered step lines (`3. …`, `（3）…`) count as legitimate separators and are not reported.
- `--blocks-summary`: same, but prints only the summary and the warnings (209 lines → ~10 on a big doc).
  Use this one in `round.sh` / CI.
- `--prose-space`: fail if body text (not monospaced blocks) has CJK stuck to Latin, or `/` `$` stuck to CJK.
- `--indent`: leading spaces (with `text:s` expanded) and style name per matching paragraph; repeatable.

After deleting config rows, assert the old text is gone with `--forbidden`:

```bash
python3 <skill-dir>/scripts/check_odt.py new.odt --forbidden "a1.sinks.k3.indexType,a1.sinks.k3.ttl"
```

**Why this matters:** zip, TOC, and chapter numbering can all pass while styles are entirely
ineffective. Every other `check_odt.py` check is structural or textual and cannot detect it.
This really happened: the document printed PASS while a config line rendered as 12pt serif
with no grey background.

`--font-audit` checks undefined styles and broken inheritance (~1s).
`--render` additionally checks the render: count of monospace families, near-duplicate sizes
within a monospace family, near-duplicate colours, and whether a declared background colour
actually appears in the render (~6s, needs a prior `render.sh`).

## 3. Visual QA + TOC refresh

LibreOffice is the layout source of truth. The render is **read-only by default**:

```bash
bash <skill-dir>/scripts/render.sh new.odt [pages...]
bash <skill-dir>/scripts/render.sh new.odt --refresh-toc   # refresh TOC fields and write back
```

Output goes to `$ODT_EDIT_WORK/<stem>/`: `render.pdf`, `render.txt`, `pages/p-NN.png`.
Per-document directories, so versions never clobber each other.

**Why no write-back by default:** writing back makes LibreOffice re-save the document and rename
every automatic style (`TBMCode` → `P123`). Any later work keyed on style names then breaks.

Each run prints either `PDF: 重新转换` (re-converted) or `PDF: 复用` (reused). If you edited the
document and see `复用`, the container clock is off: pass `--force`. When `--toc-pages` still
reports drift after a refresh, write the real page numbers into the TOC field (see gotchas
“目录页码可能不收敛”).
When the document has no TOC field the refresh is a no-op, so the write-back is pure risk.

Inspect **changed pages plus a sample of unchanged pages**.

XML alone cannot tell you what renders. Substituted fonts, a background one line short,
two fonts inside one line — check the render output:

```bash
python3 <skill-dir>/scripts/odt_probe.py new.odt --fonts
python3 <skill-dir>/scripts/odt_probe.py new.odt --find "some text"     # locate first
python3 <skill-dir>/scripts/odt_probe.py new.odt --page-of "some text"
python3 <skill-dir>/scripts/odt_probe.py new.odt --bg 700 100 600 --page 11
python3 <skill-dir>/scripts/odt_probe.py new.odt --crop 85 470 330 500 --scale 4 --page 11
```

- `--find`: the **page plus pixel coordinates** of a string — exactly what `--crop` / `--bg` need.
  Do not guess coordinates. `--quiet` prints `page x y height`, one per line.

- `--fonts`: (family, size, colour) actually used in the PDF, with character counts.
  **Two monospace font ids inside one line means a fragment fell back to body style.**
- `--bg`: background colour runs down one pixel column, to verify a background covers a whole block.
- `--crop`: zoomed PNG crop for glyph inspection. 4x makes "two fonts in one line" obvious.
- `--page-of`: which page holds a string. Add `--quiet` to print page numbers only, one per line.

Bullet shape and indent: **PNG only**. For the hyphen-wrap and de-hyphenation traps of `render.txt` (it swallows the trailing `-`, which looks like lost characters) see `references/gotchas.md`; `render.layout.txt` (`pdftotext -layout`) keeps the line breaks — check it first, then the XML. Ignore `javaldx` warnings.

## 4. Diff

```bash
python3 <skill-dir>/scripts/diff_odt.py old.odt new.odt out.diff
```

Body extract (skip TOC, footnote-safe) + unified diff. Quote a slice in the reply and give the full diff path.
