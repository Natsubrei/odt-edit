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

It prints body-child indexes, headings, list nesting, and style names. Run it before changing lists or inserting a section. Load with odfdo; **do all structural work on `el._xml_element` (lxml)**. Read `references/gotchas.md` before coding.

Copy-paste helpers live in gotchas:

- `set_el_text(el, s)` — leaf heading/paragraph only. Do not use odfdo `text_content`. Do not call on `text:list-item` (it deletes nested lists). Use `set_item_label` for the label of a numbered item.
- `make_p(style, text, span=None)` — `\n`→line-break, `\t`→tab, consecutive spaces as `" "` + `<text:s>`. If the original wraps monospaced text in a span, pass that span style name.
- `insert_after` / `insert_before` — `xmlposition=NEXT_SIBLING/PREV_SIBLING`.
- Remove comments: delete `//office:annotation` and `//office:annotation-end`. Apply useful comment text to the body first.

Rules:

- Assert hit counts per change class. Save as **vN+1**, do not overwrite the original.
- Do not touch a `text:note` subtree unless the footnote itself is the target.
- **New lists: deepcopy an existing same-shape block** and change the strings. Bullet glyphs follow nesting depth (see gotchas “Lists”).
- Numbers like `3.2` in headings are often **literal text**, not automatic numbering. After insert/delete, retitle later headings and search cross-references such as “see 3.2”.

## 2. Check

```bash
python3 <skill-dir>/scripts/check_odt.py new.odt [--forbidden w1,w2]
```

Always: zip integrity and mimetype (must be first, uncompressed). Optional: `--require-toc`, `--require-chapter-seq`, `--forbid-nbsp`. Compare table/image counts with the pre-edit baseline.

## 3. Visual QA + TOC refresh

LibreOffice is the layout source of truth. TOC fields must be refreshed by LibreOffice:

```bash
bash <skill-dir>/scripts/render.sh new.odt [pages...]
```

Docker+UNO refreshes TOC and writes the ODT back, then exports PDF/PNG. Without Docker, host `soffice` exports PDF only (no TOC refresh). Inspect **changed pages plus a sample of unchanged pages**.

Bullet shape and indent: **PNG only**. `render.txt` wraps at hyphens (`foo-bar-baz` → `foobarbaz`). Ignore `javaldx` warnings.

## 4. Diff

```bash
python3 <skill-dir>/scripts/diff_odt.py old.odt new.odt out.diff
```

Body extract (skip TOC, footnote-safe) + unified diff. Quote a slice in the reply and give the full diff path.
