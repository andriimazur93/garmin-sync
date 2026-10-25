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
if [[ $# -lt 1 || $# -gt 2 || ( $# -eq 2 && "$2" != --tests ) ]]; then
    echo 'Usage: run-simulator.sh path/to/app.prg [--tests]' >&2
    exit 2
fi
if [[ ! -f "$1" ]]; then
    echo 'PRG file does not exist. Run scripts/build-watch.sh first.' >&2
    exit 1
fi
# Start connectiq (or a compatible simulator AppImage) separately before this command.
flags=()
if [[ "${2:-}" == --tests ]]; then
    # SDK 9.3.0's monkeydo returns 1 even for a clean PASSED test run.
    # Accept that code only alongside an explicit final passing summary.
    test_log=$(mktemp)
    trap 'rm -f -- "$test_log"' EXIT
    status=0
    "$CIQ_SDK_HOME/bin/monkeydo" "$1" fr955 -t > "$test_log" 2>&1 || status=$?
    cat "$test_log"
    if [[ "$status" -le 1 ]] && sed '/^[[:space:]]*$/d' "$test_log" | tail -n 1 | grep -Eq '^PASSED \(passed=[1-9][0-9]*, failed=0, errors=0\)$'; then
        exit 0
    fi
    if [[ "$status" -eq 0 ]]; then status=1; fi
    exit "$status"
fi
exec "$CIQ_SDK_HOME/bin/monkeydo" "$1" fr955 "${flags[@]}"
