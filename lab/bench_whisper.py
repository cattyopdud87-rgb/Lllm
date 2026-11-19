import subprocess
import time
import json
import re

MODELS = ["tiny-q5_1", "base-q5_1"]
THREADS = [1, 2, 4]
AFFINITIES = [("gold", ["taskset", "-c", "6,7"]), ("unpinned", [])]
AUDIO_PATH = "/tmp/spch-en.wav"
AUDIO_DUR = 3.825

results = []

print(f"{'Model':<12} | {'Threads':<7} | {'Affinity':<8} | {'Encode (ms)':<11} | {'Total (ms)':<10} | {'RTF':<6} | {'Status'}")
print("-" * 75)

for model in MODELS:
    model_path = f"/opt/vaani/models/ggml-{model}.bin"
    for t in THREADS:
        for aff_label, aff_cmd in AFFINITIES:
            cmd = aff_cmd + [
                "/opt/vaani/bin/whisper-cli",
                "-m", model_path,
                "-t", str(t),
                "-l", "en",
                "-nt",
                AUDIO_PATH
            ]
            t0 = time.time()
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            elapsed = time.time() - t0

            # Extract timings
            total_ms = None
            encode_ms = None
            for line in res.stdout.splitlines():
                if "encode time =" in line:
                    m = re.search(r"=\s*([0-9.]+)\s*ms", line)
                    if m:
                        encode_ms = float(m.group(1))
                elif "total time =" in line:
                    m = re.search(r"=\s*([0-9.]+)\s*ms", line)
                    if m:
                        total_ms = float(m.group(1))

            if total_ms is None:
                total_ms = elapsed * 1000.0

            rtf = (total_ms / 1000.0) / AUDIO_DUR

            row = {
                "model": model,
                "threads": t,
                "affinity": aff_label,
                "encode_ms": encode_ms,
                "total_ms": total_ms,
                "rtf": round(rtf, 3),
                "wall_elapsed": round(elapsed, 3)
            }
            results.append(row)
            print(f"{model:<12} | {t:<7} | {aff_label:<8} | {str(encode_ms):<11} | {total_ms:<10.1f} | {rtf:<6.3f} | OK")

with open("/tmp/whisper_results.json", "w") as f:
    json.dump(results, f, indent=2)

# Find winner (lowest total_ms)
winner = min(results, key=lambda x: x["total_ms"])
print("\nWINNER:", winner)

# Hindi prompt test with winner
print("\n=== Testing Hindi with prompt नमस्ते ===")
h_cmd = (["taskset", "-c", "6,7"] if winner["affinity"] == "gold" else []) + [
    "/opt/vaani/bin/whisper-cli",
    "-m", f"/opt/vaani/models/ggml-{winner['model']}.bin",
    "-t", str(winner["threads"]),
    "-l", "hi",
    "--prompt", "नमस्ते",
    "-nt",
    "/tmp/spch-hi.wav"
]
h_res = subprocess.run(h_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
print("Hindi output:")
for line in h_res.stdout.splitlines():
    if line.strip() and not line.startswith("whisper_") and not line.startswith("system_") and not line.startswith("main:"):
        print(" ", line)
