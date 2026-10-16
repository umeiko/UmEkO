#!/bin/sh
# Linux server entrypoint. Configure drawio_path to THIS executable file.
set -eu

binary="${DRAWIO_BINARY:-/usr/bin/drawio}"
if [ ! -x "$binary" ]; then
    echo "draw.io executable is missing: $binary (set DRAWIO_BINARY to its absolute path)" >&2
    exit 1
fi
if ! command -v xvfb-run >/dev/null 2>&1; then
    echo "xvfb-run is missing; install xvfb and xauth" >&2
    exit 1
fi
if [ "${DRAWIO_NO_SANDBOX:-0}" = "1" ]; then
    # Electron in an isolated container may lack a usable Chromium sandbox.
    # Keep this flag after the input filename for draw.io CLI compatibility.
    set -- "$@" --no-sandbox
elif [ "$(id -u)" = "0" ]; then
    echo "Run draw.io as a normal user; isolated containers may set DRAWIO_NO_SANDBOX=1" >&2
    exit 1
fi
set -- "$@" --disable-acceleration
# A separate Electron profile avoids collisions between consecutive/concurrent exports.
profile=$(mktemp -d /tmp/umeko-drawio.XXXXXXXX)
trap 'rm -rf -- "$profile"' EXIT HUP INT TERM
XDG_CONFIG_HOME="$profile" xvfb-run -a -e /dev/stderr "$binary" "$@"
