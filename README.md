# Vaani — Offline Conversational Speech AI Stack (Snapdragon 732G / ARMv8.2-A)

Real-time, zero-disk-I/O offline voice assistant running natively on Android 15 (Xiaomi Redmi Note 10 Pro, `sweet`) via Termux + OpenSL ES UID `2000` audio.

## Architecture
`Microphone (android_mic)` → `Silero VAD v5 (1.06 ms/chunk)` → `Whisper.cpp (Gold 6,7)` → `Warm llama-server SSE (Qwen 2.5 1.5B Q4_K_M, 182 ms TTFT)` → `Persistent Piper TTS (--output_raw)` → `Speaker (OpenSL ES)`

## Quick Start
```bash
# Start / check warm llama-server (auto-unloads after 10 min idle to free ~1 GiB DRAM)
./src/llama-server.sh start

# Run streaming voice assistant
./src/vaani_stream.py
```

## Directory Structure
- `src/`: Core streaming voice engine (`vaani_stream.py`), llama-server controller (`llama-server.sh`), and batch assistant (`vaani-assistant.sh`).
- `lab/`: Diagnostic and latency benchmark scripts for Silero VAD, Whisper STT, and Piper TTS.
- `docs/`: Real-world performance benchmarks and architecture reports.
- `MODELS.md`: Complete local model inventory and hardware acceleration parameters.
