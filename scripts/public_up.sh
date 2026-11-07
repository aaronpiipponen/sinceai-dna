#!/usr/bin/env bash
# Start the demo on 127.0.0.1 and publish it through a Cloudflare quick tunnel.
#
# Public hosting is the user's decision: this stays unstarted until they ask.
# Refuses to publish while /lab or /api/lab/* is reachable, because those
# expose ground truth and traces.
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/public_common.sh
. "$HERE/public_common.sh"

check_port
mkdir -p "$STATE"

CF=$(find_cloudflared) || {
    echo "public_up: cloudflared not found; install it in ~/.local/bin or set CLOUDFLARED" >&2
    exit 1
}
[ -x "$CF" ] || {
    echo "public_up: $CF is not executable" >&2
    exit 1
}
command -v python3 >/dev/null 2>&1 || {
    echo "public_up: python3 not found" >&2
    exit 1
}

# --- one tunnel at a time ---------------------------------------------------
if [ -f "$TUNNEL_PID" ]; then
    tpid=$(cat "$TUNNEL_PID" 2>/dev/null || true)
    if pid_is "$tpid" "cloudflared tunnel"; then
        url=$(cat "$URL_FILE" 2>/dev/null || true)
        echo "public_up: tunnel already running (PID $tpid)${url:+ at $url}" >&2
        echo "public_up: stop it with scripts/public_down.sh first" >&2
        exit 1
    fi
    rm -f "$TUNNEL_PID"
fi

# --- demo server: reuse ours, refuse someone else's -------------------------
server_pid=""
if [ -f "$SERVER_PID" ]; then
    pid=$(cat "$SERVER_PID" 2>/dev/null || true)
    if pid_is "$pid" "app/server.py"; then
        server_pid=$pid
        echo "public_up: reusing demo server (PID $server_pid) on port $PORT"
    else
        rm -f "$SERVER_PID"
    fi
fi

if [ -z "$server_pid" ]; then
    if curl -fsS --max-time 2 "http://$HOST:$PORT/api/health" >/dev/null 2>&1; then
        echo "public_up: something already serves http://$HOST:$PORT but public_up did not start it" >&2
        echo "public_up: stop it or choose another PORT" >&2
        exit 1
    fi
    (
        cd "$ROOT" || exit 1
        export DNA_PUBLIC=1
        export DNA_THINKING="${DNA_THINKING:-off}"  # live demo: no hidden reasoning, ~2.5 s turns
        nohup python3 app/server.py --host "$HOST" --port "$PORT" \
            >>"$SERVER_LOG" 2>&1 </dev/null &
        echo $! >"$SERVER_PID"
    ) || {
        echo "public_up: could not start the demo server" >&2
        exit 1
    }
    server_pid=$(cat "$SERVER_PID")
    echo "public_up: started demo server (PID $server_pid) on http://$HOST:$PORT/"
    for _ in $(seq 1 60); do
        curl -fsS --max-time 2 "http://$HOST:$PORT/api/health" >/dev/null 2>&1 && break
        pid_is "$server_pid" "app/server.py" || break
        sleep 0.25
    done
    if ! curl -fsS --max-time 2 "http://$HOST:$PORT/api/health" >/dev/null 2>&1; then
        echo "public_up: the demo server did not answer on port $PORT; see $SERVER_LOG" >&2
        tail -n 20 "$SERVER_LOG" >&2 || true
        stop_pidfile "$SERVER_PID" "app/server.py" "public_up: demo server"
        exit 1
    fi
fi

# --- gate: only the demo may be public --------------------------------------
lab_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://$HOST:$PORT/lab" || true)
api_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://$HOST:$PORT/api/lab/cases" || true)
if [ "$lab_code" != "404" ] || [ "$api_code" != "404" ]; then
    echo "public_up: refusing to publish: /lab answered $lab_code and /api/lab/cases answered $api_code" >&2
    echo "public_up: app/server.py must honour DNA_PUBLIC=1 and 404 /lab, /lab/* and /api/lab/*" >&2
    echo "public_up: the server is left running on 127.0.0.1:$PORT (not public); stop it with scripts/public_down.sh" >&2
    exit 1
fi

# --- tunnel -----------------------------------------------------------------
: >"$TUNNEL_LOG"
nohup "$CF" tunnel --url "http://$HOST:$PORT" --no-autoupdate >>"$TUNNEL_LOG" 2>&1 </dev/null &
echo $! >"$TUNNEL_PID"
tpid=$(cat "$TUNNEL_PID")
echo "public_up: starting cloudflared (PID $tpid); waiting for the tunnel URL"

url=""
for _ in $(seq 1 120); do
    url=$(grep -m1 -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" 2>/dev/null || true)
    [ -n "$url" ] && break
    pid_is "$tpid" "cloudflared tunnel" || break
    sleep 0.5
done

if [ -z "$url" ]; then
    echo "public_up: cloudflared did not print a trycloudflare URL; see $TUNNEL_LOG" >&2
    tail -n 20 "$TUNNEL_LOG" >&2 || true
    stop_pidfile "$TUNNEL_PID" "cloudflared tunnel" "public_up: tunnel"
    exit 1
fi

printf '%s\n' "$url" >"$URL_FILE"
echo "public_up: public URL: $url"
echo "public_up: stop with scripts/public_down.sh; check with scripts/public_status.sh"
