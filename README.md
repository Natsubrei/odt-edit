# odt-edit

Surgical edits for OpenDocument Text (`.odt`) files, plus check / diff / render helpers for coding agents.

**Rule:** change content nodes only. Do not rebuild the document. Do not rewrite the style sheet.

- Agent instructions: [`SKILL.md`](SKILL.md) (Chinese), [`SKILL.en.md`](SKILL.en.md) (English)
- Pitfalls: [`references/gotchas.md`](references/gotchas.md)
- License: [MIT](LICENSE)

## Setup

```bash
bash scripts/setup_env.sh --python-only   # odfdo + lxml wheels
bash scripts/selftest.sh                  # no Docker
```

Optional LibreOffice image (TOC refresh + PNG):

```bash
# Debian packages from deb.debian.org by default
ODT_EDIT_BUILD_IMAGE=1 bash scripts/setup_env.sh

# Optional mirror / host network if the default build cannot reach the net:
# ODT_EDIT_APT_MIRROR=mirrors.tuna.tsinghua.edu.cn
# ODT_EDIT_DOCKER_NETWORK=host
```

## Scripts

| Script | Role |
|---|---|
| `scripts/outline.py` | Print headings and list nesting |
| `scripts/check_odt.py` | Zip/mimetype always; TOC/chapter/NBSP, style resolution, block structure, indent |
| `scripts/odthelper.py` | Importable edit helpers (`set_el_text`, `make_p`, `clone_row`, `leading_spaces`, …) |
| `scripts/odt_styles.py` | Resolve effective style properties; flag broken inheritance |
| `scripts/diff_odt.py` | Body diff; `--styles` adds a style-property diff, split into real property changes vs count-only changes |
| `scripts/odt_text.py` | Extract body text; `out` optional (stdout); `--keep-blanks` keeps empty paragraphs |
| `scripts/render.sh` | Read-only PDF + PNG + `render.txt`/`render.layout.txt`; `--refresh-toc` writes back |
| `scripts/odt_probe.py` | Inspect the render: fonts, `--find` (page + pixel coords), background runs, zoomed crops |
| `scripts/make_examples.py` | Write `examples/*.odt` fixtures |

`check_odt.py` flags: `--require-toc` `--require-chapter-seq` `--forbid-nbsp` `--forbidden a,b`
`--font-audit` (undefined styles / broken inheritance) `--blocks` (list blocks; splits are notes)
`--blocks-fail` (splits are errors) `--blocks-summary` (summary only, for loops/CI)
`--prose-space` (CJK stuck to Latin or `/` `$`)
`--indent TEXT` (leading spaces, `text:s` expanded) `--render` (also check the render output)
`--toc-pages` (TOC numbers vs render pagination).

`scripts/selftest.sh` runs in CI (`.github/workflows/selftest.yml`); it needs no Docker or LibreOffice.

`render.sh` never modifies the source unless you pass `--refresh-toc`. Output lands in
`$ODT_EDIT_WORK/<stem>/`: `render.pdf`, `render.txt`, `pages/p-NN.png`.
`odt_probe.py` reads that directory.

Temp dirs default to `$TMPDIR/odt-edit-<uid>/`. Override with `ODT_EDIT_ROOT`, `ODT_EDIT_PYLIB`, `ODT_EDIT_WORK`.

## Examples

```bash
python3 scripts/make_examples.py
python3 scripts/outline.py examples/nested-list.odt
python3 scripts/check_odt.py examples/no-toc.odt
python3 scripts/check_odt.py examples/no-toc.odt --require-toc   # expected fail
```
