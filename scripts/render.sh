#!/usr/bin/env bash
# 渲染 ODT：导出 PDF + 逐页 PNG，供 odt_probe.py 取证据。
#
# 默认**只读源文件，绝不回写**。要刷新目录（TOC）字段并回写，显式加 --refresh-toc。
# 回写会让 LibreOffice 重存文档并重命名全部自动样式（TBMCode -> P123 之类），
# 之后按样式名做的处理会全部失效，所以默认不开。
#
# 用法: render.sh 文件.odt [--refresh-toc] [--force] [页码...]
# 输出: $ODT_EDIT_WORK/<文件名去扩展>/render.pdf
#                                  /render.txt
#                                  /pages/p-NN.png
# Env: ODT_EDIT_IMAGE, ODT_EDIT_WORK, ODT_EDIT_SKIP_DOCKER=1
set -e

REFRESH=0
FORCE=0
ARGS=()
for a in "$@"; do
  case "$a" in
    --refresh-toc) REFRESH=1 ;;
    --force) FORCE=1 ;;
    *) ARGS+=("$a") ;;
  esac
done
set -- "${ARGS[@]+"${ARGS[@]}"}"

ODT="$1"; shift || true
PAGES="$*"
if [ -z "$ODT" ] || [ ! -f "$ODT" ]; then
  echo "usage: render.sh file.odt [--refresh-toc] [--force] [page...]" >&2
  exit 2
fi

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
UID_N="$(id -u)"
WORK_BASE="${ODT_EDIT_WORK:-${TMPDIR:-/tmp}/odt-edit-$UID_N/work}"
BASENAME="$(basename "$ODT")"
STEM="${BASENAME%.odt}"
WORK="$WORK_BASE/$STEM"
mkdir -p "$WORK/pages"
DIR="$(cd "$(dirname "$ODT")" && pwd)"

have_poppler() {
  command -v pdftotext >/dev/null 2>&1 && command -v pdftoppm >/dev/null 2>&1 \
    && command -v pdfinfo >/dev/null 2>&1
}

# 在 $WORK 下执行 poppler 命令；宿主没有就在容器里执行
run_poppler() {
  if have_poppler; then
    ( cd "$WORK" && eval "$1" )
  elif use_docker; then
    docker run --rm -v "$WORK":/work "${ODT_EDIT_IMAGE:-lo-headless}" \
      bash -c "cd /work && $1"
  else
    echo "没有 pdftotext/pdftoppm/pdfinfo，也没有 Docker 镜像。装 poppler-utils 或跑 setup_env.sh。" >&2
    return 1
  fi
}

render_from_pdf() {
  local pp
  if [ -n "$PAGES" ]; then
    pp="for p in $PAGES; do pdftoppm -png -r 110 -f \$p -l \$p render.pdf pages/p; done"
  else
    pp="pdftoppm -png -r 110 render.pdf pages/p"
  fi
  run_poppler "pdftotext render.pdf render.txt && rm -f pages/*.png && $pp && pdfinfo render.pdf | grep Pages"
  echo "PDF: $WORK/render.pdf"
  echo "PNG: $WORK/pages/"
  echo "TXT: $WORK/render.txt （按换页符 \\f 分页；连字符处会折行，不能当正文证据）"
}

find_soffice() { command -v soffice || command -v libreoffice || true; }

use_docker() {
  command -v docker >/dev/null 2>&1 || return 1
  [ "${ODT_EDIT_SKIP_DOCKER:-}" = "1" ] && return 1
  docker image inspect "${ODT_EDIT_IMAGE:-lo-headless}" >/dev/null 2>&1
}

convert_with_docker() {
  local img="${ODT_EDIT_IMAGE:-lo-headless}"
  docker run --rm \
    -v "$DIR":/data:ro \
    -v "$WORK":/work \
    "$img" bash -c '
set -e
export HOME=/tmp
cp "/data/'"$BASENAME"'" /tmp/doc.odt
soffice --headless --invisible --norestore --nologo \
  -env:UserInstallation=file:///tmp/loprof \
  --convert-to pdf --outdir /work /tmp/doc.odt >/dev/null
'
  # 容器内转换产物按 /tmp/doc.odt 命名为 doc.pdf
  mv -f "$WORK/doc.pdf" "$WORK/render.pdf"
}

refresh_toc_with_docker() {
  local img="${ODT_EDIT_IMAGE:-lo-headless}"
  docker run --rm \
    -v "$DIR":/data:rw \
    -v "$SKILL_DIR/scripts":/scripts:ro \
    -v "$WORK":/work \
    "$img" bash -c '
set -e
export HOME=/tmp
cp "/data/'"$BASENAME"'" /tmp/doc.odt
soffice --headless --invisible --norestore --nologo \
  -env:UserInstallation=file:///tmp/loprof \
  --accept="socket,host=127.0.0.1,port=2002;urp;" &
for i in $(seq 1 60); do
  sleep 0.5
  python3 -c "import socket;s=socket.socket();s.settimeout(1);s.connect((\"127.0.0.1\",2002))" 2>/dev/null && break
done
python3 /scripts/update_toc.py "file:///tmp/doc.odt" "file:///work/render.pdf"
cp /tmp/doc.odt "/data/'"$BASENAME"'"
'
}

if [ "$REFRESH" = "1" ]; then
  if use_docker; then
    refresh_toc_with_docker
    echo "TOC_REFRESHED 源文件已回写: $ODT"
  else
    echo "!! --refresh-toc 需要 Docker 镜像；本次只导出 PDF，不刷新目录" >&2
  fi
else
  echo "只读模式：源文件不会被修改（要刷新目录并回写，加 --refresh-toc）"
fi

if [ ! -f "$WORK/render.pdf" ]; then
  NEEDS=1
elif [ "$FORCE" = "1" ]; then
  NEEDS=1
  echo "PDF: --force，重新转换"
elif [ "$ODT" -nt "$WORK/render.pdf" ]; then
  NEEDS=1
else
  NEEDS=0
fi

if [ "$NEEDS" = "1" ]; then
  # 源文件比 PDF 新（或显式 --force）就必须重转。
  # 曾经这里只判断“PDF 是否存在”，改完文档再跑会静默复用旧 PDF，验证全部作废。
  echo "PDF: 重新转换"
  if use_docker; then
    convert_with_docker
  else
    SOFFICE="$(find_soffice)"
    if [ -z "$SOFFICE" ]; then
      echo "没有 Docker 镜像 '${ODT_EDIT_IMAGE:-lo-headless}'，也没有本机 soffice。跑 setup_env.sh 或装 LibreOffice。" >&2
      exit 1
    fi
    "$SOFFICE" --headless --norestore --convert-to pdf --outdir "$WORK" "$ODT" >/dev/null
    PDF_SRC="$WORK/${STEM}.pdf"
    [ "$PDF_SRC" != "$WORK/render.pdf" ] && mv -f "$PDF_SRC" "$WORK/render.pdf"
  fi
else
  echo "PDF: 复用 $WORK/render.pdf（源文件没有更新；要看新改动请加 --force）"
fi

render_from_pdf
echo RENDER_OK
