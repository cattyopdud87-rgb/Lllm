#!/usr/bin/env bash
set -e
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== [1/5] Installing Termux / Arch Dependencies ==="
if command -v pkg >/dev/null 2>&1; then
  pkg install -y python-numpy python-onnxruntime pulseaudio ffmpeg curl cmake ninja clang git
elif command -v pacman >/dev/null 2>&1; then
  pacman -S --needed --noconfirm python-numpy python-onnxruntime pulseaudio ffmpeg curl cmake ninja clang git
fi

echo "=== [2/5] Ensuring ARMv8.2-A Binaries (bin/) ==="
if [ ! -x "$REPO_ROOT/bin/llama-server" ] || [ ! -x "$REPO_ROOT/bin/whisper-cli" ] || [ ! -x "$REPO_ROOT/bin/piper/piper" ]; then
  "$REPO_ROOT/scripts/build_bins.sh"
fi

echo "=== [3/5] Ensuring Pre-Quantized Models (models/) ==="
if [ ! -f "$REPO_ROOT/models/qwen2.5-1.5b-instruct-q4_k_m.gguf" ]; then
  "$REPO_ROOT/scripts/fetch_models.sh"
fi

echo "=== [4/5] Checking Audio Socket (/data/local/tmp/awl/pulse.sock) ==="
if [ -S /data/local/tmp/awl/pulse.sock ]; then
  PULSE_SERVER=unix:/data/local/tmp/awl/pulse.sock pactl list sinks short || true
  PULSE_SERVER=unix:/data/local/tmp/awl/pulse.sock pactl list sources short || true
else
  echo "Warning: /data/local/tmp/awl/pulse.sock not found. Ensure 99-audio-forensics.sh (UID 2000 PulseAudio) is active."
fi

echo "=== [5/5] Starting & Verifying Warm llama-server ==="
"$REPO_ROOT/src/llama-server.sh" start
"$REPO_ROOT/src/llama-server.sh" status
echo "Install complete! Run: $REPO_ROOT/src/vaani_stream.py"
