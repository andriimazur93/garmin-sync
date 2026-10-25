#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ -z "${CIQ_SDK_HOME:-}" && -d "$project_root/.local/toolchains/sdk-9.3.0" ]]; then
    CIQ_SDK_HOME="$project_root/.local/toolchains/sdk-9.3.0"
fi
if ! command -v java >/dev/null && [[ -x "$project_root/.local/toolchains/java-17/bin/java" ]]; then
    export PATH="$project_root/.local/toolchains/java-17/bin:$PATH"
fi
: "${CIQ_SDK_HOME:?Set CIQ_SDK_HOME to the installed Connect IQ SDK directory}"
: "${GARMIN_SIGNING_KEY:?Set GARMIN_SIGNING_KEY to your external DER developer key}"
if ! command -v java >/dev/null; then
    echo 'Java is missing from PATH. Install Java 17 or add its bin directory to PATH.' >&2
    exit 1
fi
if [[ ! -f "$GARMIN_SIGNING_KEY" ]]; then
    echo 'GARMIN_SIGNING_KEY does not identify an existing file.' >&2
    exit 1
fi
test_flags=()
jungle=monkey.jungle
output="$project_root/dist/garmin-sync-fr955.prg"
if [[ "${1:-}" == --tests ]]; then
    test_flags=(-t)
    output="$project_root/dist/garmin-sync-fr955-tests.prg"
elif [[ "${1:-}" == --smoke ]]; then
    test_flags=(-t)
    jungle="$project_root/.local/watch-smoke/monkey.jungle"
    output="$project_root/dist/garmin-sync-fr955-smoke.prg"
    if [[ ! -f "$jungle" ]]; then
        echo 'Prepare private resources with scripts/prepare-smoke.py first.' >&2
        exit 1
    fi
elif [[ $# -ne 0 ]]; then
    echo 'Usage: build-watch.sh [--tests|--smoke]' >&2
    exit 2
fi
mkdir -p "$project_root/dist"
cd "$project_root/watch"
# SVG resource compilation does not require a running X server.
export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-} -Djava.awt.headless=true"
exec "$CIQ_SDK_HOME/bin/monkeyc" -f "$jungle" -d fr955 -y "$GARMIN_SIGNING_KEY" -o "$output" -w "${test_flags[@]}"
