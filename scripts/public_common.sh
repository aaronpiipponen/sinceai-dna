# shellcheck shell=bash
# Shared state and process helpers for the public quick-tunnel scripts.
# Sourced by public_up.sh / public_down.sh / public_status.sh; never run alone.

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
STATE=${DNA_PUBLIC_STATE:-/tmp/opencode/public}
PORT=${PORT:-8780}
HOST=127.0.0.1

SERVER_PID=$STATE/server.pid
TUNNEL_PID=$STATE/tunnel.pid
SERVER_LOG=$STATE/server.log
TUNNEL_LOG=$STATE/tunnel.log
URL_FILE=$STATE/url.txt

pid_alive() {
    local pid=${1:-}
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

pid_cmdline() {
    local pid=${1:-}
    [ -n "$pid" ] || return 1
    tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null
}

# pid_is PID PATTERN — the PID exists and its command line contains PATTERN.
# A pid file can be stale and its PID reused by an unrelated process; only
# ever signal a process we recognise.
pid_is() {
    local pid=$1 pattern=$2
    pid_alive "$pid" || return 1
    case "$(pid_cmdline "$pid")" in
        *"$pattern"*) return 0 ;;
    esac
    return 1
}

find_cloudflared() {
    if [ -n "${CLOUDFLARED:-}" ]; then
        printf '%s\n' "$CLOUDFLARED"
    elif command -v cloudflared >/dev/null 2>&1; then
        command -v cloudflared
    elif [ -x "$HOME/.local/bin/cloudflared" ]; then
        printf '%s\n' "$HOME/.local/bin/cloudflared"
    else
        return 1
    fi
}

check_port() {
    case "${PORT:-}" in
        ''|*[!0-9]*)
            echo "PORT must be a number, got '$PORT'" >&2
            return 1
            ;;
    esac
    if [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
        echo "PORT out of range: $PORT" >&2
        return 1
    fi
}

# stop_pidfile FILE PATTERN LABEL — TERM the PID in FILE when it is ours,
# KILL it after 5 s, then remove the file. Missing or stale files are fine.
stop_pidfile() {
    local file=$1 pattern=$2 label=$3 pid
    if [ ! -f "$file" ]; then
        echo "$label: not running"
        return 0
    fi
    pid=$(cat "$file" 2>/dev/null || true)
    if ! pid_is "$pid" "$pattern"; then
        rm -f "$file"
        echo "$label: not running (removed stale pid file)"
        return 0
    fi
    kill -TERM "$pid" 2>/dev/null || true
    for _ in $(seq 1 50); do
        pid_alive "$pid" || break
        sleep 0.1
    done
    if pid_alive "$pid"; then
        echo "$label: PID $pid ignored TERM, sending KILL" >&2
        kill -KILL "$pid" 2>/dev/null || true
    fi
    rm -f "$file"
    echo "$label: stopped (PID $pid)"
    return 0
}
