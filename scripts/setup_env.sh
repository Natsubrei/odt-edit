#!/usr/bin/env bash
# Install Python wheels into $ODT_EDIT_PYLIB. Optionally build the LibreOffice image.
# Env:
#   ODT_EDIT_ROOT / ODT_EDIT_PYLIB / ODT_EDIT_WORK
#   ODT_EDIT_SKIP_DOCKER=1     skip image
#   ODT_EDIT_BUILD_IMAGE=1     build image if missing (default: build when docker exists)
#   ODT_EDIT_IMAGE             image name (default lo-headless)
#   ODT_EDIT_APT_MIRROR        e.g. mirrors.tuna.tsinghua.edu.cn
#   ODT_EDIT_DOCKER_NETWORK    e.g. host  (only if build cannot reach the network)
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
UID_N="$(id -u)"
ROOT="${ODT_EDIT_ROOT:-${TMPDIR:-/tmp}/odt-edit-$UID_N}"
LIB="${ODT_EDIT_PYLIB:-$ROOT/pylibs}"
IMAGE="${ODT_EDIT_IMAGE:-lo-headless}"
PYVER=$(python3 -c 'import sys; print(f"cp{sys.version_info.major}{sys.version_info.minor}")')
MACH=$(python3 -c 'import platform; print(platform.machine())')

if PYTHONPATH="$LIB" python3 -c "import odfdo, lxml" 2>/dev/null; then
  echo "python deps ready: $LIB"
else
  mkdir -p "$LIB" && cd "$LIB" && rm -f *.whl dl.whl
  while read -r u; do
    [ -n "$u" ] && curl -fsSL -o dl.whl "$u" && python3 -m zipfile -e dl.whl .
  done < <(python3 - "$PYVER" "$MACH" <<'EOF'
import json, sys, urllib.request
pyver, mach = sys.argv[1], sys.argv[2]
# PEP 600 arch tags: x86_64, aarch64. Apple Silicon reports arm64.
arch = {"arm64": "aarch64", "amd64": "x86_64"}.get(mach, mach)

def get(url):
    return json.load(urllib.request.urlopen(url, timeout=30))

def wheel(project, pred):
    d = get("https://pypi.org/pypi/%s/json" % project)
    urls = [u["url"] for u in d["urls"] if u["packagetype"] == "bdist_wheel" and pred(u["filename"])]
    if not urls:
        raise SystemExit("no wheel for %s py=%s arch=%s" % (project, pyver, arch))
    return urls[0]

print(wheel("odfdo", lambda n: n.endswith(".whl") and "py3" in n))
print(wheel("lxml", lambda n: pyver in n and arch in n and "manylinux" in n and "musllinux" not in n))
print(wheel("typing_extensions", lambda n: n.endswith(".whl") and "py3" in n))
EOF
)
  rm -f dl.whl
  PYTHONPATH="$LIB" python3 -c "import odfdo, lxml"
  echo "python deps installed: $LIB"
fi

if [ "${ODT_EDIT_SKIP_DOCKER:-}" = "1" ] || [ "$1" = "--python-only" ]; then
  echo "skip docker"
  exit 0
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found; Python-only mode. Host soffice can still export PDF."
  exit 0
fi
IMAGE_NAME="$IMAGE"
if docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
  echo "docker image ready: $IMAGE_NAME"
  exit 0
fi
if [ "${ODT_EDIT_BUILD_IMAGE:-1}" != "1" ]; then
  echo "docker image $IMAGE_NAME missing. Set ODT_EDIT_BUILD_IMAGE=1 to build."
  exit 0
fi

TMP=$(mktemp -d)
MIRROR="${ODT_EDIT_APT_MIRROR:-}"
cat > "$TMP/Dockerfile" <<EOF
FROM debian:bookworm-slim
ARG APT_MIRROR=
RUN if [ -n "\$APT_MIRROR" ]; then \\
      sed -i "s|deb.debian.org|\${APT_MIRROR}|g; s|security.debian.org|\${APT_MIRROR}/debian-security|g" /etc/apt/sources.list.d/debian.sources; \\
    fi \\
 && apt-get update -o Acquire::Retries=5 \\
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends -o Acquire::Retries=5 \\
    libreoffice-writer python3-uno fonts-noto-cjk poppler-utils ca-certificates \\
 && rm -rf /var/lib/apt/lists/*
EOF
NET=()
if [ -n "${ODT_EDIT_DOCKER_NETWORK:-}" ]; then
  NET=(--network "$ODT_EDIT_DOCKER_NETWORK")
fi
docker build "${NET[@]}" --build-arg APT_MIRROR="$MIRROR" -t "$IMAGE_NAME" "$TMP"
rm -rf "$TMP"
echo "docker image built: $IMAGE_NAME"
