#!/data/data/com.termux/files/usr/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SERVER_BIN="${LLAMA_SERVER_BIN:-$REPO_ROOT/bin/llama-server}"
[ -x "$SERVER_BIN" ] || SERVER_BIN="/data/data/com.termux/files/home/development/build/llama.cpp/build-sdmmagpie/bin/llama-server"

MODEL="${LLM_MODEL:-$REPO_ROOT/models/qwen2.5-1.5b-instruct-q4_k_m.gguf}"
[ -f "$MODEL" ] || MODEL="/data/data/com.termux/files/home/development/model/qwen2.5-1.5b-instruct-q4_k_m.gguf"

LOG="/data/local/tmp/llama_server.log"
STAMP="/data/local/tmp/vaani_last_use"
IDLE_TIMEOUT_SEC="${IDLE_TIMEOUT_SEC:-600}"

touch_stamp() { date +%s > "$STAMP" 2>/dev/null || true; }

start_idle_reaper() {
  if pgrep -f "vaani_idle_reaper" >/dev/null 2>&1; then return 0; fi
  setsid bash -c "
    exec -a vaani_idle_reaper bash -c '
      while pgrep -f \"llama-server.*8080\" >/dev/null 2>&1; do
        sleep 60
        last=\$(cat \"$STAMP\" 2>/dev/null || echo 0)
        now=\$(date +%s)
        if [ \"\$last\" -gt 0 ] && [ \$((now - last)) -ge $IDLE_TIMEOUT_SEC ]; then
          pkill -f \"llama-server.*8080\" 2>/dev/null || true; su -c \"echo 60 > /proc/sys/vm/swappiness 2>/dev/null\" || true
          echo \"[\$(date)] Auto-unloaded idle llama-server after ${IDLE_TIMEOUT_SEC}s\" >> \"$LOG\"
          break
        fi
      done
    '
  " >/dev/null 2>&1 &
}

case "${1:-status}" in
  start)
    touch_stamp
    su -c 'echo 0-7 > /dev/cpuset/foreground/cpus 2>/dev/null; echo 100 > /proc/sys/vm/swappiness 2>/dev/null' || true
    if pgrep -f "llama-server.*8080" >/dev/null 2>&1; then
      start_idle_reaper
      echo "llama-server already running (PID $(pgrep -f 'llama-server.*8080'))."
      exit 0
    fi
    nohup taskset -c 6,7 "$SERVER_BIN" -m "$MODEL" -c 512 -t 2 -np 1 --poll 0 -lm mmap --host 127.0.0.1 --port 8080 > "$LOG" 2>&1 &
    for i in $(seq 1 30); do
      if curl -s http://127.0.0.1:8080/health | grep -q "ok"; then
        touch_stamp
        start_idle_reaper
        echo "llama-server started and healthy on 127.0.0.1:8080 (PID $(pgrep -f 'llama-server.*8080'))."
        exit 0
      fi
      sleep 1
    done
    echo "Warning: llama-server did not report healthy within 30s."
    exit 1
    ;;
  touch) touch_stamp ;;
  stop)
    pkill -f "vaani_idle_reaper" 2>/dev/null || true
    pkill -f "llama-server.*8080" 2>/dev/null && su -c "echo 60 > /proc/sys/vm/swappiness 2>/dev/null" && echo "llama-server stopped (swappiness=60)." || echo "llama-server was not running."
    ;;
  restart) "$0" stop; sleep 1; "$0" start ;;
  status)
    if pgrep -f "llama-server.*8080" >/dev/null 2>&1; then
      ps -eo pid,pcpu,pmem,rss,comm,args | grep -E "llama-server.*8080" | grep -v grep
      curl -s http://127.0.0.1:8080/health && echo ""
    else
      echo "llama-server is stopped (0 MB RAM used)."
    fi
    ;;
esac
