#!/usr/bin/env bash
# Report whether the quick tunnel and the demo server are up, and the URL.
# Exit 0 when both are up, 1 otherwise.
set -uo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/public_common.sh
. "$HERE/public_common.sh"

tunnel_up=0
tpid=$(cat "$TUNNEL_PID" 2>/dev/null || true)
if pid_is "$tpid" "cloudflared tunnel"; then
    tunnel_up=1
    echo "tunnel: up (PID $tpid)"
else
    echo "tunnel: down"
fi

spid=$(cat "$SERVER_PID" 2>/dev/null || true)
if pid_is "$spid" "app/server.py"; then
    echo "server: up (PID $spid) on http://$HOST:$PORT/"
else
    echo "server: down"
fi

url=$(cat "$URL_FILE" 2>/dev/null || true)
if [ "$tunnel_up" -eq 0 ]; then
    echo "url: (none)"
elif [ -n "$url" ]; then
    echo "url: $url"
else
    echo "url: (tunnel is starting, no URL yet)"
fi

echo "logs: $STATE"
if [ "$tunnel_up" -eq 1 ] && pid_is "$spid" "app/server.py"; then
    exit 0
fi
exit 1
