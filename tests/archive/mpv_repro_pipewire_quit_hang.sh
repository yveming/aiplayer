#!/usr/bin/env bash
# Minimal reproduction: mpv hangs on quit after a second "loadfile replace".
#
# Observed with mpv v0.41.0 (Ubuntu) using the default PipeWire audio output.
# Signature of the bug:
#   * sending `loadfile A replace`, then `loadfile B replace`, then `quit`
#     leaves the mpv process alive (quit's reply is even sent, but the
#     process never exits);
#   * the only running (R) thread is `mpv/ao/pipewire`; the PipeWire library
#     threads (`pw-data-loop`, `module-rt`) are sleeping;
#   * invoking `stop` immediately before each loadfile avoids the hang;
#   * SIGTERM still terminates the process.
# It reproduces with `--no-config`, so user scripts/config are not involved.
#
# Usage:
#   ./mpv_repro_pipewire_quit_hang.sh <media1> <media2>
#
# Exit status: 0 = mpv exited normally, 1 = HANG REPRODUCED.
#
# Note: uses a private IPC socket for this run and does not touch other mpv
# instances.

set -u

MPV="${MPV:-mpv}"
SOCK="/tmp/mpv-repro-$$.sock"
LOG="/tmp/mpv-repro-$$.log"
M1="${1:?usage: $0 <media1> <media2>}"
M2="${2:?usage: $0 <media1> <media2>}"

for f in "$M1" "$M2"; do
    if [ ! -f "$f" ]; then
        echo "media file not found: $f" >&2
        exit 2
    fi
done

ipc() {
    python3 - "$SOCK" "$@" <<'PY'
import json, socket, sys
sock = sys.argv[1]
cmd = sys.argv[2:]
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(10)
s.connect(sock)
s.sendall((json.dumps({"command": cmd}) + "\n").encode())
buf = b""
while True:
    try:
        chunk = s.recv(4096)
    except socket.timeout:
        print("TIMEOUT")
        sys.exit(1)
    if not chunk:
        print("EOF")
        sys.exit(0)
    buf += chunk
    for line in buf.decode("utf-8", "replace").split("\n")[:-1]:
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and "event" not in obj and "error" in obj:
            print(obj.get("error"))
            sys.exit(0 if obj.get("error") == "success" else 1)
PY
}

alive() {
    st=$(grep -m1 '^State:' "/proc/$MPVPID/status" 2>/dev/null | awk '{print $2}')
    [ -n "$st" ] && [ "$st" != "Z" ]
}

cleanup() {
    kill -9 "$MPVPID" >/dev/null 2>&1
    rm -f "$SOCK"
}
trap cleanup EXIT

echo "mpv: $($MPV --version 2>/dev/null | head -1)"
rm -f "$SOCK"
$MPV --idle=yes --keep-open=yes --input-ipc-server="$SOCK" --no-terminal \
     --no-config --log-file="$LOG" >/dev/null 2>&1 &
MPVPID=$!
echo "spawned mpv pid=$MPVPID"

for _ in $(seq 1 50); do
    [ -S "$SOCK" ] && break
    sleep 0.1
done
sleep 0.3

echo "loadfile 1 -> $(ipc loadfile "$M1" replace)"
sleep 2
echo "loadfile 2 -> $(ipc loadfile "$M2" replace)"
sleep 2
echo "quit       -> $(ipc quit)"

for _ in $(seq 1 20); do
    if ! alive; then
        echo "RESULT: OK - mpv exited after quit"
        exit 0
    fi
    sleep 0.25
done

echo "RESULT: HANG REPRODUCED - mpv still alive 5s after quit"
echo "threads (name state):"
python3 - "$MPVPID" <<'PY'
import glob, sys
pid = sys.argv[1]
for tf in glob.glob("/proc/%s/task/*/stat" % pid):
    data = open(tf).read()
    comm = data.split("(", 1)[1].rsplit(")", 1)[0]
    state = data.rsplit(")", 1)[-1].split()[0]
    print("  %-24s %s" % (comm, state))
PY
echo "--- mpv log tail ---"
tail -n 15 "$LOG" 2>/dev/null
echo "SIGTERM..."
kill -TERM "$MPVPID" 2>/dev/null
sleep 1
if alive; then
    echo "still alive after SIGTERM"
else
    echo "SIGTERM terminated mpv (confirms it is stuck in userspace exit)"
fi
exit 1
