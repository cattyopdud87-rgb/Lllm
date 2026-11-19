#!/bin/bash
set -e
export LD_LIBRARY_PATH=/opt/vaani/piper:$LD_LIBRARY_PATH

echo "=== 1. Testing Hindi TTS (pratham) ==="
T0=$(date +%s%N)
echo "नमस्ते, मैं वाणी हूँ। आज मैं आपकी क्या मदद कर सकती हूँ?" | \
  /opt/vaani/piper/piper --model /opt/vaani/models/hi_IN-pratham-medium.onnx \
  --output_file /tmp/tts-hi.wav
T1=$(date +%s%N)
HI_SYNTH_MS=$(( (T1 - T0) / 1000000 ))
echo "Hindi synthesis time: ${HI_SYNTH_MS} ms"

echo "=== 2. Testing English TTS (amy) ==="
T0=$(date +%s%N)
echo "Hello, I am Vaani. How can I help you today?" | \
  /opt/vaani/piper/piper --model /opt/vaani/models/en_US-amy-medium.onnx \
  --output_file /tmp/tts-en.wav
T1=$(date +%s%N)
EN_SYNTH_MS=$(( (T1 - T0) / 1000000 ))
echo "English synthesis time: ${EN_SYNTH_MS} ms"

ls -la /tmp/tts-hi.wav /tmp/tts-en.wav

python3 - << 'PYEOF'
import wave

for lang, path, synth_ms in [("hi", "/tmp/tts-hi.wav", 1), ("en", "/tmp/tts-en.wav", 1)]:
    try:
        w = wave.open(path)
        frames = w.getnframes()
        rate = w.getframerate()
        dur_s = frames / float(rate)
        print(f"[{lang}] frames: {frames}, rate: {rate}, duration: {dur_s:.2f}s")
    except Exception as e:
        print(f"[{lang}] error: {e}")
PYEOF
