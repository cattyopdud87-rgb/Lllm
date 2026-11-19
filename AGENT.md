# AGENT.md — Vaani Offline Speech AI & Xiaomi Redmi Note 10 Pro (`sweet`) Engineering Manual

## 1. Target Hardware & OS Profile
- **Device:** Xiaomi Redmi Note 10 Pro (`M2101K6P`, `sweet` / `sweetin`)
- **SoC:** Qualcomm Snapdragon 732G (`SM6150` / `SM7150-AC`):
  - `policy0` (Cores `0–5`): 6× Kryo 470 Silver (Cortex-A55, `300 MHz – 1.80 GHz`)
  - `policy6` (Cores `6–7`): 2× Kryo 470 Gold (Cortex-A76, `300 MHz – 2.30 GHz`, ARMv8.2-A `asimddp` + `fp16`)
  - **GPU:** Adreno 618 (**DO NOT** run LLM Vulkan/OpenCL compute on Adreno 618 — yields `0.49 t/s` and triggers KGSL timeouts/SystemUI ANRs).
- **RAM / Swap:** `5.4 GiB` usable LPDDR4X + `4.0 GiB` ZSTD ZRAM (`CONFIG_ZRAM_AUTO_RECOMP=y` every 15s).
- **Kernel:** Linux `4.14.357-reforge` (`CONFIG_PID_MAX_CLAMP_BIONIC=y`, `pid_max = 65535`, native `P_PIDFD`).

## 2. Models: Where to Download & Do We Need to Re-Quantize?
**NO re-quantization is required.** Download the official pre-quantized files directly via `./scripts/fetch_models.sh`:

| Component | Exact Model File | Size | Direct Download Source | Re-Quantize? & Device Benchmark Verdict |
| :--- | :--- | :--- | :--- | :--- |
| **LLM** | `qwen2.5-1.5b-instruct-q4_k_m.gguf` | `1.04 GiB` | `https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf` | **NO.** Official `Q4_K_M` uses ARMv8.2-A `asimddp` (`SDOT`) kernels directly (`9.31 t/s` gen vs `5.45 t/s` on `Q4_0`). **Do NOT use 3B models** (`3.08 t/s`, `2.2 GiB` RSS triggers Android `lmkd`). |
| **STT** | `ggml-tiny-q5_1.bin` | `32 MB` | `https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny-q5_1.bin` | **NO.** Official `Q5_1` gives 100% accuracy at `0.36 RTF` on Gold cores `6,7`. Optional higher accuracy: `ggml-base-q5_1.bin` (`59 MB`, `0.79 RTF`). |
| **VAD** | `silero_vad.onnx` | `1.8 MB` | `https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx` | **NO.** Runs in `1.06 ms` per 32ms audio chunk (`30.2x` real-time) on `onnxruntime`. |
| **TTS** | `en_US-amy-medium.onnx` (+ `.json`) | `63 MB` | `https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx` | **NO.** `0.24 RTF` (`4.25x` real-time) on Gold cores `6,7`. Hindi voices (`hi_IN-pratham-medium.onnx`, `hi_IN-priyamvada-medium.onnx`) come from the same `rhasspy/piper-voices` repo. |

## 3. Handling `bin/` (Why Binaries Are Excluded from Git & How to Rebuild / Port Them)
GitHub blocks large files (>100 MB) and precompiled ELF binaries bloat Git history, so `bin/` and `models/` are listed in `.gitignore`. On a fresh device or container, `./scripts/build_bins.sh` (invoked automatically by `./install.sh`) recreates `bin/` cleanly:
1. **`bin/llama-server` & `bin/whisper-cli` (Native Termux Bionic OR Arch glibc):**
   - Compile natively with `-DGGML_NATIVE=OFF -DGGML_VULKAN=OFF -DGGML_OPENCL=OFF -DGGML_CPU_ARM_ARCH="armv8.2-a+dotprod+fp16" -DBUILD_SHARED_LIBS=OFF`.
   - **Critical:** Always pass `-DGGML_NATIVE=OFF` with explicit `armv8.2-a+dotprod+fp16` because Android's `/proc/cpuinfo` on big.LITTLE Kryo 470 can misdetect flags when `-march=native` runs on a Silver core.
2. **`bin/piper/piper` (GNU/Linux glibc `aarch64` binary on Termux/Android):**
   - Official `piper_linux_aarch64.tar.gz` targets GNU/Linux `/lib/ld-linux-aarch64.so.1` (which exists natively inside the Arch Linux `mikasa` container, but NOT in Android/Termux Bionic).
   - **Inside Arch Linux Container (`mikasa`):** Runs natively out of the box (`./bin/piper/piper`).
   - **Inside Native Termux (Bionic):** Wrap `piper.bin` with the container's glibc dynamic loader:
     ```sh
     #!/system/bin/sh
     exec /data/local/Droidspaces/Containers/mikasa/rootfs/lib/ld-linux-aarch64.so.1 \
       --library-path /data/local/Droidspaces/Containers/mikasa/rootfs/usr/lib:/data/local/tmp/vaani-lab/piper \
       /path/to/piper.bin "$@"
     ```
   - *(Alternatively, to back up prebuilt binaries to GitHub without bloating Git commits, attach `tar -czf bin.tar.gz bin/` to a GitHub Release tag.)*

## 4. Critical Device-Specific Rules (Do Not Violate)
1. **CPU Core Pinning (`taskset -c 6,7 -t 2`):** Always pin `llama-server`, `whisper-cli`, and `piper` to Gold cores `6,7`.
2. **Android 15 `cpuset` Unlock (`0-7`):** Write `0-7` to `/dev/cpuset/foreground/cpus` so Gold Core 6 is never masked out.
3. **Split-Cluster Dynamic Boost:** Keep `policy0` and `policy6` on `schedutil` (`min=300000`) at idle; boost **only `policy6`** to `performance` (`2304000`) during compute and restore `schedutil` immediately afterward.
4. **Auto-Idle Memory Reclamation (`+1.02 GiB` DRAM):** `llama-server.sh` auto-unloads `llama-server` after 10 minutes idle so Android `lmkd` never kills foreground apps; `vaani_stream.py` auto-wakes it on demand.
5. **Audio Transport (UID `2000` OpenSL ES):** Host PulseAudio MUST run under UID `2000` (`com.android.shell`, `SYSTEM_FIXED` `RECORD_AUDIO`) on `/data/local/tmp/awl/pulse.sock` (`0777`) with `module-sles-sink` + `module-sles-source`.

## 5. From-Scratch Installation in a New Container / Termux Environment
1. `git clone <your-repo-url> llm && cd llm`
2. `./install.sh` (installs dependencies, compiles `llama-server`/`whisper-cli`, fetches `piper` and models, verifies `/data/local/tmp/awl/pulse.sock`, and starts `llama-server`).
3. Run `./src/vaani_stream.py` for live voice interaction, or `./src/vaani_stream.py --file <16k.wav>` to benchmark.
