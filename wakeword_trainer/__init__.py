"""Train a custom openWakeWord-compatible wake word for GLaSSIST in any supported language.

The pipeline (see docs/WAKE_WORD_WIZARD.md):
  1. generate  - synthetic positives/negatives with neural TTS voices of the chosen language
  2. record    - the user's own voice (positives, normal speech, room noise)
  3. train     - a tiny dense head on openWakeWord audio embeddings, exported to ONNX
  4. evaluate  - clip-level false activations on audio that was never used for training

Only the pure-Python modules (languages, workspace, confusables) are imported here so the
GLaSSIST UI can use them without NumPy/PyTorch; the heavy steps run in a separate environment.
"""
from . import confusables, languages, workspace  # noqa: F401

SAMPLE_RATE = 16000
FRAME = 1280           # 80 ms, the openWakeWord frame size
WINDOW = 16            # the model looks at 16 embeddings (~1.3 s)
EMBED_DIM = 96
