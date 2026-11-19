#!/data/data/com.termux/files/usr/bin/bash
export PATH="/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/bin/applets:$PATH"
# Vaani Offline Conversational Speech AI Orchestrator (Master Brain Phase 4)
# Pipeline: Microphone (or WAV) -> Whisper.cpp (Gold 6,7) -> Qwen 2.5 1.5B (Gold 6,7) -> Piper TTS (Gold 6,7) -> Speaker
set -e

VAANI_BIN_DIR="/data/data/com.termux/files/home/development/Lllm/artifacts/vaani-arm64-31424b7-727d3e7/bin"
MODEL_DIR="/data/data/com.termux/files/home/development/model"
WHISPER_CLI="$VAANI_BIN_DIR/whisper-cli"
LLAMA_CLI="/data/data/com.termux/files/home/development/build/llama.cpp/build-sdmmagpie/bin/llama-cli"
PIPER_BIN="/data/local/tmp/vaani-lab/piper/piper"

STT_MODEL="${STT_MODEL:-$MODEL_DIR/ggml-tiny-q5_1.bin}"
LLM_MODEL="${LLM_MODEL:-$MODEL_DIR/qwen2.5-1.5b-instruct-q4_k_m.gguf}"
TTS_MODEL="${TTS_MODEL:-$MODEL_DIR/en_US-amy-medium.onnx}"
PULSE_SOCK="unix:/data/local/tmp/awl/pulse.sock"

TMP_IN="/data/local/tmp/vaani_in_16k.wav"
TMP_OUT="/data/local/tmp/vaani_out_tts.wav"

restore_governor() {
  su -c '
    chmod 0666 /sys/devices/system/cpu/cpufreq/policy6/scaling_governor /sys/devices/system/cpu/cpufreq/policy6/scaling_min_freq 2>/dev/null || true
    echo schedutil > /sys/devices/system/cpu/cpufreq/policy6/scaling_governor 2>/dev/null
    echo 300000 > /sys/devices/system/cpu/cpufreq/policy6/scaling_min_freq 2>/dev/null
  ' >/dev/null 2>&1 || true
}
trap restore_governor EXIT INT TERM

INPUT_WAV="$1"
REC_SEC="${2:-4}"

if [ -z "$INPUT_WAV" ]; then
  echo "[Vaani] Recording ${REC_SEC}s from microphone (android_mic)..."
  true > "$TMP_IN" 2>/dev/null || rm -f "$TMP_IN" 2>/dev/null || true
  touch "$TMP_IN" && chmod 666 "$TMP_IN" 2>/dev/null || true
  timeout $((REC_SEC + 1)) env PULSE_SERVER="$PULSE_SOCK" parecord \
    --device=android_mic --rate=16000 --channels=1 --format=s16le --file-format=wav "$TMP_IN" 2>/dev/null || true
  INPUT_WAV="$TMP_IN"
fi

T_START=$(date +%s%3N)

# Engage Split-Cluster Dynamic Boost on Gold Cores (6,7) ONLY:
su -c '
  echo 0-7 > /dev/cpuset/foreground/cpus 2>/dev/null || true
  chmod 0666 /sys/devices/system/cpu/cpufreq/policy6/scaling_governor /sys/devices/system/cpu/cpufreq/policy6/scaling_min_freq 2>/dev/null || true
  echo performance > /sys/devices/system/cpu/cpufreq/policy6/scaling_governor
  echo 2304000 > /sys/devices/system/cpu/cpufreq/policy6/scaling_min_freq
'

echo "[Vaani] Stage 1: Running Whisper STT on Gold cores (6,7)..."
USER_TEXT=$(taskset -c 6,7 "$WHISPER_CLI" -m "$STT_MODEL" -f "$INPUT_WAV" -t 2 -nt -np 2>/dev/null | tr '\n' ' ' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
T_STT=$(date +%s%3N)
echo "[Vaani] Transcript ($((T_STT - T_START)) ms): $USER_TEXT"

if [ -z "$USER_TEXT" ]; then
  USER_TEXT="Hello Master Brain, please confirm system status."
fi

echo "[Vaani] Stage 2: Generating Qwen 2.5 1.5B response..."
REPLY_TEXT=""
if curl -s --connect-timeout 1 http://127.0.0.1:8080/health 2>/dev/null | grep -q "ok"; then
  REPLY_TEXT=$(python3 -c "
import urllib.request, json, sys

user_text = sys.argv[1] if len(sys.argv) > 1 else 'Hello Master Brain.'
payload = {
    'messages': [
        {'role': 'system', 'content': 'You are Vaani, a concise offline voice assistant running locally on a Xiaomi Redmi Note 10 Pro. Reply in 1 or 2 short spoken sentences.'},
        {'role': 'user', 'content': user_text}
    ],
    'max_tokens': 40,
    'temperature': 0.2,
    'cache_prompt': True
}
try:
    req = urllib.request.Request(
        'http://127.0.0.1:8080/v1/chat/completions',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        res = json.loads(resp.read().decode('utf-8'))
        reply = res['choices'][0]['message']['content'].strip()
        print(reply.replace('\n', ' '))
except Exception:
    sys.exit(1)
" "$USER_TEXT" 2>/dev/null || true)
fi

if [ -z "$REPLY_TEXT" ]; then
  echo "[Vaani] (llama-server offline/unresponsive; falling back to llama-cli on Gold cores 6,7)"
  PROMPT="<|im_start|>system
You are Vaani, a concise offline voice assistant running locally on a Xiaomi Redmi Note 10 Pro. Reply in 1 or 2 short spoken sentences.<|im_end|>
<|im_start|>user
${USER_TEXT}<|im_end|>
<|im_start|>assistant
"
  REPLY_TEXT=$(taskset -c 6,7 "$LLAMA_CLI" -m "$LLM_MODEL" -p "$PROMPT" -n 36 -t 2 --temp 0.3 --no-display-prompt -st 2>/dev/null | python3 -c "
import sys, re
raw = sys.stdin.read()
m = re.search(r'assistant\s*\n\s*(.*?)(?=\n\s*\[\s*Prompt|\Z)', raw, re.DOTALL)
if m and m.group(1).strip():
    print(m.group(1).strip().replace('\n', ' '))
else:
    print('All systems are operational and running locally on ARM64.')
")
fi
T_LLM=$(date +%s%3N)
echo "[Vaani] Response ($((T_LLM - T_STT)) ms): $REPLY_TEXT"

echo "[Vaani] Stage 3: Synthesizing speech with Piper TTS on Gold cores (6,7)..."
echo "$REPLY_TEXT" | LD_LIBRARY_PATH="$(dirname "$PIPER_BIN"):$LD_LIBRARY_PATH" taskset -c 6,7 "$PIPER_BIN" \
  --model "$TTS_MODEL" --output_file "$TMP_OUT" >/dev/null 2>&1
T_TTS=$(date +%s%3N)
echo "[Vaani] TTS Synthesized ($((T_TTS - T_LLM)) ms). Restoring schedutil & playing audio..."

# Restore schedutil BEFORE audio playback so CPU cools while speaking!
restore_governor

PULSE_SERVER="$PULSE_SOCK" paplay "$TMP_OUT" 2>/dev/null && echo "[Vaani] Audio playback: OK" || echo "[Vaani] Warning: paplay playback skipped/failed"
T_END=$(date +%s%3N)
echo "[Vaani] Complete Turn Summary: STT=$((T_STT - T_START))ms | LLM=$((T_LLM - T_STT))ms | TTS=$((T_TTS - T_LLM))ms | Total Compute=$((T_TTS - T_START))ms | Total Turn=$((T_END - T_START))ms"
