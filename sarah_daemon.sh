#!/bin/bash
# S.A.R.A.H. Background Daemon
# Runs the main agent loop in the background, at all times, tracked by PID
# so it can be reliably started/stopped/checked instead of relying on the
# caller to manage the process by hand.

PROJECT_ROOT="/home/xanmal/Documents/Projects/repositories/S.A.R.A.H"
export PYTHONPATH="$PROJECT_ROOT"

SARAH_HOME="$HOME/.sarah"
PID_FILE="$SARAH_HOME/daemon.pid"
LOG_FILE="$SARAH_HOME/daemon.log"
mkdir -p "$SARAH_HOME"

is_running() {
    [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

start() {
    if is_running; then
        echo "S.A.R.A.H. is already running (PID $(cat "$PID_FILE"))."
        exit 0
    fi
    nohup python3 "$PROJECT_ROOT/main.py" >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    disown
    echo "S.A.R.A.H. started (PID $(cat "$PID_FILE")). Logs: $LOG_FILE"
}

stop() {
    if ! is_running; then
        echo "S.A.R.A.H. is not running."
        rm -f "$PID_FILE"
        exit 0
    fi
    kill "$(cat "$PID_FILE")"
    rm -f "$PID_FILE"
    echo "S.A.R.A.H. stopped."
}

status() {
    if is_running; then
        echo "S.A.R.A.H. is running (PID $(cat "$PID_FILE"))."
    else
        echo "S.A.R.A.H. is not running."
    fi
}

case "$1" in
    start) start ;;
    stop) stop ;;
    restart) stop; start ;;
    status) status ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
