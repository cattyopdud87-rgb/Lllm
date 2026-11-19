#!/usr/bin/env bash
set -e
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_TMP="$REPO_ROOT/.build_tmp"
mkdir -p "$REPO_ROOT/bin/piper" "$BUILD_TMP"

echo "=== [1/3] Building llama-server (ARMv8.2-A+dotprod+fp16, CPU-only, NO Vulkan/OpenCL) ==="
if [ ! -x "$REPO_ROOT/bin/llama-server" ]; then
  git clone --depth 1 https://github.com/ggml-org/llama.cpp.git "$BUILD_TMP/llama.cpp"
  cmake -S "$BUILD_TMP/llama.cpp" -B "$BUILD_TMP/llama.cpp/build" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=OFF -DGGML_VULKAN=OFF -DGGML_OPENCL=OFF \
    -DGGML_CPU_ARM_ARCH="armv8.2-a+dotprod+fp16" -DBUILD_SHARED_LIBS=OFF
  cmake --build "$BUILD_TMP/llama.cpp/build" -j4 --target llama-server
  cp -a "$BUILD_TMP/llama.cpp/build/bin/llama-server" "$REPO_ROOT/bin/llama-server"
fi

echo "=== [2/3] Building whisper-cli (ARMv8.2-A+dotprod+fp16) ==="
if [ ! -x "$REPO_ROOT/bin/whisper-cli" ]; then
  git clone --depth 1 https://github.com/ggml-org/whisper.cpp.git "$BUILD_TMP/whisper.cpp"
  cmake -S "$BUILD_TMP/whisper.cpp" -B "$BUILD_TMP/whisper.cpp/build" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=OFF -DGGML_VULKAN=OFF \
    -DGGML_CPU_ARM_ARCH="armv8.2-a+dotprod+fp16" -DBUILD_SHARED_LIBS=OFF
  cmake --build "$BUILD_TMP/whisper.cpp/build" -j4 --target whisper-cli
  cp -a "$BUILD_TMP/whisper.cpp/build/bin/whisper-cli" "$REPO_ROOT/bin/whisper-cli"
fi

echo "=== [3/3] Fetching Piper Linux aarch64 Release Tarball ==="
if [ ! -x "$REPO_ROOT/bin/piper/piper" ]; then
  curl -L -o "$BUILD_TMP/piper_linux_aarch64.tar.gz" \
    "https://github.com/rhasspy/piper/releases/latest/download/piper_linux_aarch64.tar.gz"
  tar -xzf "$BUILD_TMP/piper_linux_aarch64.tar.gz" -C "$REPO_ROOT/bin/"
fi

rm -rf "$BUILD_TMP"
echo "All ARMv8.2-A binaries ready in $REPO_ROOT/bin/"
