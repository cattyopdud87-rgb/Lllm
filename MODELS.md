# Local Offline Speech AI Model Inventory (Excluded from Git)

Large model weights are ignored by `.gitignore` and stored in `models/` (or downloaded via `./scripts/fetch_models.sh`):

| Role | Filename | Size | Target Hardware |
| :--- | :--- | :--- | :--- |
| **VAD** | `silero_vad.onnx` | 1.8 MB | CPU (`onnxruntime`, 1.06 ms / 32ms chunk) |
| **STT** | `ggml-tiny-q5_1.bin` | 32 MB | Kryo 470 Gold (`taskset -c 6,7 -t 2`) |
| **STT (High Acc)** | `ggml-base-q5_1.bin` | 59 MB | Kryo 470 Gold (`taskset -c 6,7 -t 2`) |
| **LLM** | `llm/qwen2.5-1.5b-instruct-q4_k_m.gguf` | 1.04 GiB | Kryo 470 Gold (`llama-server`, `9.31 t/s` peak) |
| **TTS (EN)** | `en_US-amy-medium.onnx` (+ `.json`) | 63 MB | Kryo 470 Gold (`piper --output_raw`, `0.24 RTF`) |
| **TTS (HI)** | `hi_IN-pratham-medium.onnx` / `hi_IN-priyamvada-medium.onnx` | 63 MB each | Kryo 470 Gold |
