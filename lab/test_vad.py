import onnxruntime as ort
import numpy as np

model_path = "/opt/vaani/models/silero_vad.onnx"
s = ort.InferenceSession(model_path)

inputs = [(i.name, i.shape, i.type) for i in s.get_inputs()]
outputs = [(o.name, o.shape, o.type) for o in s.get_outputs()]
print("VAD Inputs:", inputs)
print("VAD Outputs:", outputs)

# Silero VAD v5 accepts 512 samples per chunk at 16kHz
sr = 16000
chunk_size = 512
x = np.zeros((1, chunk_size), dtype=np.float32)

feed = {
    "input": x,
    "state": np.zeros((2, 1, 128), dtype=np.float32),
    "sr": np.array(sr, dtype=np.int64)
}

out = s.run(None, feed)
prob = float(np.squeeze(out[0]))
print(f"VAD_OK speech_prob= {prob:.6f}")
