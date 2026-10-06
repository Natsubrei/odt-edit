#!/usr/bin/env bash
# Python-only smoke test. Does not need Docker or LibreOffice.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
export ODT_EDIT_SKIP_DOCKER=1
bash "$HERE/setup_env.sh" --python-only
python3 "$HERE/make_examples.py"
python3 "$HERE/outline.py" "$ROOT/examples/nested-list.odt" | grep -q Nested
python3 "$HERE/check_odt.py" "$ROOT/examples/no-toc.odt"
if python3 "$HERE/check_odt.py" "$ROOT/examples/no-toc.odt" --require-toc; then
  echo "expected --require-toc to fail" >&2
  exit 1
fi
DIFF="$ROOT/examples/_selftest.diff"
python3 "$HERE/diff_odt.py" "$ROOT/examples/leaf.odt" "$ROOT/examples/nested-list.odt" "$DIFF"
test -s "$DIFF"
rm -f "$DIFF"
echo SELFTEST_OK
