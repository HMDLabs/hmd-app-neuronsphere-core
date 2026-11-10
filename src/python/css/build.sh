#!/bin/sh
# Build deployments/static/deployments/css/app.css, the precompiled Tailwind v4 stylesheet.
#
# `hmd build` runs this before the python build. The Tailwind v4 standalone CLI
# comes from the hmd-config-tailwindcss-cli artifact that pre_build_artifacts
# unzips into css/bin/<platform>/tailwindcss, so the shared project builder image
# carries no Tailwind. The CLI is looked up in this order:
#
#   1. $TAILWINDCSS, a path to any Tailwind v4 CLI (local development)
#   2. css/bin/<platform>/tailwindcss, the artifact
#   3. `tailwindcss` on the PATH
#
# <platform> is linux-x64, linux-arm64 or macos-arm64, from `uname`;
# $TAILWINDCSS_PLATFORM overrides it. The generated file is not committed.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT_REL="../deployments/static/deployments/css/app.css"

platform() {
  if [ -n "${TAILWINDCSS_PLATFORM:-}" ]; then
    echo "$TAILWINDCSS_PLATFORM"
    return
  fi
  case "$(uname -s)-$(uname -m)" in
    Darwin-arm64) echo macos-arm64 ;;
    Linux-x86_64 | Linux-amd64) echo linux-x64 ;;
    Linux-aarch64 | Linux-arm64) echo linux-arm64 ;;
    *) echo "$(uname -s)-$(uname -m)" ;;
  esac
}

find_cli() {
  if [ -n "${TAILWINDCSS:-}" ]; then
    echo "$TAILWINDCSS"
    return
  fi
  candidate="$HERE/bin/$(platform)/tailwindcss"
  if [ -f "$candidate" ]; then
    # the artifact is unzipped without the executable bit
    chmod +x "$candidate"
    echo "$candidate"
    return
  fi
  if command -v tailwindcss >/dev/null 2>&1; then
    command -v tailwindcss
    return
  fi
  return 1
}

if ! CLI="$(find_cli)"; then
  echo "No Tailwind CLI for platform '$(platform)'." >&2
  echo "Expected css/bin/$(platform)/tailwindcss (the hmd-config-tailwindcss-cli artifact from" >&2
  echo "pre_build_artifacts), \$TAILWINDCSS, or tailwindcss on the PATH." >&2
  exit 1
fi

cd "$HERE"
# A stale stylesheet must never ship: remove it, and keep it removed on failure.
rm -f "$OUT_REL"
if ! "$CLI" --input app.src.css --output "$OUT_REL" --minify; then
  rm -f "$OUT_REL"
  echo "Tailwind build failed with $CLI" >&2
  exit 1
fi
echo "built $OUT_REL with $CLI"
