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
| `scripts/check_odt.py` | Zip/mimetype always; TOC/chapter/NBSP optional |
| `scripts/diff_odt.py` | Unified diff of extracted body text |
| `scripts/render.sh` | Docker+UNO TOC refresh, else host `soffice` PDF only |
| `scripts/make_examples.py` | Write `examples/*.odt` fixtures |

`check_odt.py` flags: `--require-toc` `--require-chapter-seq` `--forbid-nbsp` `--forbidden a,b`.

Temp dirs default to `$TMPDIR/odt-edit-<uid>/`. Override with `ODT_EDIT_ROOT`, `ODT_EDIT_PYLIB`, `ODT_EDIT_WORK`.

## Examples

```bash
python3 scripts/make_examples.py
python3 scripts/outline.py examples/nested-list.odt
python3 scripts/check_odt.py examples/no-toc.odt
python3 scripts/check_odt.py examples/no-toc.odt --require-toc   # expected fail
```
