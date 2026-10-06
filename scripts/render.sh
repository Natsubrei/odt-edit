#!/usr/bin/env bash
# Refresh TOC (Docker+UNO), export PDF, render page PNGs.
# Usage: render.sh file.odt [page...]
# Env: ODT_EDIT_IMAGE, ODT_EDIT_WORK, ODT_EDIT_SKIP_DOCKER=1
set -e
ODT="$1"; shift || true
PAGES="$*"
if [ -z "$ODT" ] || [ ! -f "$ODT" ]; then
  echo "usage: render.sh file.odt [page...]" >&2
  exit 2
fi
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
UID_N="$(id -u)"
WORK="${ODT_EDIT_WORK:-${TMPDIR:-/tmp}/odt-edit-$UID_N/work}"
IMAGE="${ODT_EDIT_IMAGE:-lo-headless}"
mkdir -p "$WORK/pages"
BASENAME="$(basename "$ODT")"
DIR="$(cd "$(dirname "$ODT")" && pwd)"

render_from_pdf() {
  pdftotext "$WORK/render.pdf" "$WORK/render.txt"
  rm -f "$WORK/pages/"*.png
  if [ -n "$PAGES" ]; then
    for p in $PAGES; do pdftoppm -png -r 110 -f "$p" -l "$p" "$WORK/render.pdf" "$WORK/pages/p"; done
  else
    pdftoppm -png -r 110 "$WORK/render.pdf" "$WORK/pages/p"
  fi
  pdfinfo "$WORK/render.pdf" | grep Pages
  echo "PDF: $WORK/render.pdf | PNG: $WORK/pages/ | pages in $WORK/render.txt split by form feed"
}

use_docker() {
  command -v docker >/dev/null 2>&1 || return 1
  [ "${ODT_EDIT_SKIP_DOCKER:-}" = "1" ] && return 1
  docker image inspect "$IMAGE" >/dev/null 2>&1
}

if use_docker; then
  docker run --rm \
    -v "$DIR":/data:rw \
    -v "$SKILL_DIR/scripts":/scripts:ro \
    -v "$WORK":/work \
    "$IMAGE" bash -c '
set -e
export HOME=/tmp
cp "/data/'"$BASENAME"'" /tmp/doc.odt
soffice --headless --invisible --norestore --nologo -env:UserInstallation=file:///tmp/loprof --accept="socket,host=127.0.0.1,port=2002;urp;" &
for i in $(seq 1 40); do sleep 1; python3 -c "import socket;s=socket.socket();s.settimeout(1);s.connect((\"127.0.0.1\",2002))" 2>/dev/null && break; done
python3 /scripts/update_toc.py "file:///tmp/doc.odt" "file:///work/render.pdf"
cp /tmp/doc.odt "/data/'"$BASENAME"'"
'
  render_from_pdf
  echo RENDER_OK
  exit 0
fi

SOFFICE="$(command -v soffice || command -v libreoffice || true)"
if [ -z "$SOFFICE" ]; then
  echo "no Docker image '$IMAGE' and no host soffice. Run setup_env.sh or install LibreOffice." >&2
  exit 1
fi
echo "TOC_SKIPPED host soffice (no UNO refresh)"
"$SOFFICE" --headless --norestore --convert-to pdf --outdir "$WORK" "$ODT" >/dev/null
# soffice names the pdf after the source basename
PDF_SRC="$WORK/${BASENAME%.odt}.pdf"
if [ "$PDF_SRC" != "$WORK/render.pdf" ]; then
  mv -f "$PDF_SRC" "$WORK/render.pdf"
fi
render_from_pdf
echo RENDER_OK
