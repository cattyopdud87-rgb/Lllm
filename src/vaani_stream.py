#!/data/data/com.termux/files/usr/bin/python3
"""
Vaani Real-Time Streaming Offline Voice Engine (Master Brain Phase 10)
Architecture:
  Live Mic (parecord --raw 16kHz S16LE)
    -> Silero VAD v5 (32ms chunks, auto End-of-Speech)
    -> Whisper.cpp (Gold cores 6,7, RAM-only /dev/shm)
    -> Warm llama-server SSE stream (127.0.0.1:8080, cache_prompt=True)
    -> Clause-level flushing -> Persistent Piper (--output_raw) -> Persistent paplay (--raw)
Zero UFS flash writes per turn; automatic Split-Cluster Gold-Core Boost + schedutil restore.
"""
import argparse, json, os, re, subprocess, sys, time, urllib.request, wave
import numpy as np
import onnxruntime as ort

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(REPO_ROOT, "models") if os.path.isdir(os.path.join(REPO_ROOT, "models")) else "/data/data/com.termux/files/home/development/model"
WHISPER_CLI = os.path.join(REPO_ROOT, "bin", "whisper-cli") if os.path.exists(os.path.join(REPO_ROOT, "bin", "whisper-cli")) else "/data/data/com.termux/files/home/development/Lllm/artifacts/vaani-arm64-31424b7-727d3e7/bin/whisper-cli"
PIPER_BIN = os.path.join(REPO_ROOT, "bin", "piper", "piper") if os.path.exists(os.path.join(REPO_ROOT, "bin", "piper", "piper")) else "/data/local/tmp/vaani-lab/piper/piper"
STT_MODEL = os.environ.get("STT_MODEL", f"{MODEL_DIR}/ggml-tiny-q5_1.bin")
TTS_MODEL = os.environ.get("TTS_MODEL", f"{MODEL_DIR}/en_US-amy-medium.onnx")
VAD_MODEL = f"{MODEL_DIR}/silero_vad.onnx"
PULSE_SOCK = "unix:/data/local/tmp/awl/pulse.sock"
LLAMA_URL = "http://127.0.0.1:8080/v1/chat/completions"

CLAUSE_RE = re.compile(r'([.!?;:\n]+)(\s+|$)')


def ensure_llama_server_awake():
    subprocess.run([os.path.join(REPO_ROOT, "src", "llama-server.sh"), "start"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def set_gold_boost(enable: bool):
    if enable:
        cmd = (
            "echo 0-7 > /dev/cpuset/foreground/cpus 2>/dev/null; "
            "echo performance > /sys/devices/system/cpu/cpufreq/policy6/scaling_governor 2>/dev/null; "
            "echo 2304000 > /sys/devices/system/cpu/cpufreq/policy6/scaling_min_freq 2>/dev/null"
        )
    else:
        cmd = (
            "echo schedutil > /sys/devices/system/cpu/cpufreq/policy6/scaling_governor 2>/dev/null; "
            "echo 300000 > /sys/devices/system/cpu/cpufreq/policy6/scaling_min_freq 2>/dev/null"
        )
    subprocess.run(["su", "-c", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

class PersistentTTSSpeaker:
    """Keeps Piper ONNX model loaded in RAM and streams raw 22.05kHz S16LE PCM straight to paplay."""
    def __init__(self, model_path: str):
        self.model_path = model_path
        self._spawn()

    def _spawn(self):
        env = os.environ.copy()
        env["PULSE_SERVER"] = PULSE_SOCK
        env["LD_LIBRARY_PATH"] = f"{os.path.dirname(PIPER_BIN)}:{env.get('LD_LIBRARY_PATH', '')}"
        self.piper = subprocess.Popen(
            ["taskset", "-c", "6,7", PIPER_BIN, "--model", self.model_path, "--output_raw"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, bufsize=0
        )
        self.paplay = subprocess.Popen(
            ["paplay", "--raw", "--rate=22050", "--channels=1", "--format=s16le", "--latency-msec=40"],
            stdin=self.piper.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env
        )
        self.piper.stdout.close()

    def speak_clause(self, text: str):
        clean = text.strip().replace("\n", " ")
        if not clean:
            return
        if self.piper.poll() is not None or (self.paplay and self.paplay.poll() is not None):
            self.close()
            self._spawn()
        try:
            self.piper.stdin.write((clean + "\n").encode("utf-8"))
            self.piper.stdin.flush()
        except BrokenPipeError:
            self.close()
            self._spawn()
            self.piper.stdin.write((clean + "\n").encode("utf-8"))
            self.piper.stdin.flush()

    def close(self):
        try:
            if self.piper.stdin:
                self.piper.stdin.close()
        except Exception:
            pass
        for p in (self.piper, self.paplay):
            try:
                p.terminate()
                p.wait(timeout=2)
            except Exception:
                pass

def record_vad_utterance(vad_sess, threshold=0.5, silence_ms=480, max_sec=10.0) -> bytes:
    """Streams 16kHz mono PCM from android_mic through Silero VAD v5 and stops automatically on silence."""
    env = os.environ.copy()
    env["PULSE_SERVER"] = PULSE_SOCK
    rec = subprocess.Popen(
        ["parecord", "--raw", "--device=android_mic", "--rate=16000", "--channels=1", "--format=s16le"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env
    )
    state = np.zeros((2, 1, 128), dtype=np.float32)
    sr = np.array(16000, dtype=np.int64)
    chunk_bytes = 512 * 2  # 32ms @ 16kHz s16le
    pre_roll = []
    captured = []
    speaking = False
    silence_chunks = 0
    max_silence_chunks = max(1, int(silence_ms / 32))
    max_chunks = int((max_sec * 1000) / 32)
    print("[Vaani-VAD] Listening on android_mic (speak naturally)...", flush=True)
    try:
        for _ in range(max_chunks):
            raw = rec.stdout.read(chunk_bytes)
            if not raw or len(raw) < chunk_bytes:
                break
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            prob, state = vad_sess.run(None, {"input": samples[None, :], "state": state, "sr": sr})
            is_speech = float(prob[0][0]) >= threshold
            if not speaking:
                pre_roll.append(raw)
                if len(pre_roll) > 10:
                    pre_roll.pop(0)
                if is_speech:
                    speaking = True
                    captured.extend(pre_roll)
                    silence_chunks = 0
                    print("[Vaani-VAD] Speech detected...", flush=True)
            else:
                captured.append(raw)
                if is_speech:
                    silence_chunks = 0
                else:
                    silence_chunks += 1
                    if silence_chunks >= max_silence_chunks:
                        print("[Vaani-VAD] End-of-speech detected.", flush=True)
                        break
    finally:
        rec.terminate()
        rec.wait(timeout=2)
    return b"".join(captured)

def transcribe_pcm_in_ram(pcm_bytes: bytes = None, wav_path: str = None) -> str:
    tmp_ram = "/dev/shm/vaani_stream_in.wav" if os.path.isdir("/dev/shm") else "/data/local/tmp/vaani_stream_in.wav"
    if wav_path:
        target = wav_path
    else:
        with wave.open(tmp_ram, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(pcm_bytes)
        target = tmp_ram
    res = subprocess.run(
        ["taskset", "-c", "6,7", WHISPER_CLI, "-m", STT_MODEL, "-f", target, "-t", "2", "-nt", "-np"],
        capture_output=True, text=True
    )
    if not wav_path and os.path.exists(tmp_ram):
        os.remove(tmp_ram)
    return " ".join(res.stdout.strip().split())

def stream_llm_to_tts(user_text: str, tts: PersistentTTSSpeaker, t_start: float):
    payload = {
        "messages": [
            {"role": "system", "content": "You are Vaani, a concise offline voice assistant running locally on a Xiaomi Redmi Note 10 Pro. Reply in 1 or 2 crisp spoken sentences."},
            {"role": "user", "content": user_text}
        ],
        "max_tokens": 60,
        "temperature": 0.2,
        "cache_prompt": True,
        "stream": True
    }
    req = urllib.request.Request(
        LLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    buf = ""
    full_reply = []
    first_token_t = None
    first_clause_t = None

    with urllib.request.urlopen(req, timeout=30) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="ignore").strip()
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            chunk = json.loads(data_str)
            delta = chunk["choices"][0].get("delta", {}).get("content", "")
            if not delta:
                continue
            if first_token_t is None:
                first_token_t = time.perf_counter()
            buf += delta
            full_reply.append(delta)
            m = CLAUSE_RE.search(buf)
            if m and len(buf[:m.end()].strip()) >= 12:
                clause = buf[:m.end()].strip()
                buf = buf[m.end():]
                if first_clause_t is None:
                    first_clause_t = time.perf_counter()
                    print(f"[Vaani-Stream] TTFT={(first_token_t - t_start)*1000:.0f}ms | First-Clause-to-TTS={(first_clause_t - t_start)*1000:.0f}ms", flush=True)
                tts.speak_clause(clause)

    if buf.strip():
        if first_clause_t is None:
            first_clause_t = time.perf_counter()
            print(f"[Vaani-Stream] TTFT={(first_token_t - t_start)*1000:.0f}ms | First-Clause-to-TTS={(first_clause_t - t_start)*1000:.0f}ms", flush=True)
        tts.speak_clause(buf.strip())

    return "".join(full_reply).strip(), first_token_t, first_clause_t

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="Test with an existing 16kHz WAV file instead of live mic")
    parser.add_argument("--turns", type=int, default=1, help="Number of turns to run")
    args = parser.parse_args()

    print("[Vaani-Stream] Pre-warming persistent Piper TTS + OpenSL ES audio pipe...", flush=True)
    tts = PersistentTTSSpeaker(TTS_MODEL)
    vad_sess = None if args.file else ort.InferenceSession(VAD_MODEL, providers=["CPUExecutionProvider"])
    time.sleep(0.8)

    try:
        for turn in range(1, args.turns + 1):
            pcm = None
            if not args.file:
                pcm = record_vad_utterance(vad_sess)
                if not pcm:
                    print("[Vaani-Stream] No speech detected.")
                    continue
            t0 = time.perf_counter()
            ensure_llama_server_awake()
            set_gold_boost(True)
            try:
                text = transcribe_pcm_in_ram(pcm_bytes=pcm, wav_path=args.file)
                t_stt = time.perf_counter()
                if not text or "BLANK_AUDIO" in text:
                    text = "Hello, please confirm system status."
                print(f"[Turn {turn}] STT ({(t_stt - t0)*1000:.0f}ms): {text}", flush=True)
                reply, t_ft, t_fc = stream_llm_to_tts(text, tts, t_stt)
                t_done = time.perf_counter()
                print(f"[Turn {turn}] LLM Reply ({(t_done - t_stt)*1000:.0f}ms): {reply}", flush=True)
                if t_fc:
                    print(f"[Turn {turn}] >>> Streaming Time-to-First-Audio Dispatch: {(t_fc - t_stt)*1000:.0f}ms (post-STT) | Total Compute: {(t_done - t0)*1000:.0f}ms <<<", flush=True)
            finally:
                set_gold_boost(False)
            time.sleep(2.5)
    finally:
        set_gold_boost(False)
        tts.close()

if __name__ == "__main__":
    main()
