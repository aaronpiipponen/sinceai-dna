#!/usr/bin/env bash
# Stop the quick tunnel and the demo server it was started with. Idempotent.
#
# Only PIDs recorded by public_up.sh are signalled, and only after their
# command line matches: a pkill pattern could hit the calling shell.
set -uo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/public_common.sh
. "$HERE/public_common.sh"

stop_pidfile "$TUNNEL_PID" "cloudflared tunnel" "tunnel"
stop_pidfile "$SERVER_PID" "app/server.py" "demo server"
rm -f "$URL_FILE"
