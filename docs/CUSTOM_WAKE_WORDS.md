# Custom wake-word models

GLaSSIST uses [openWakeWord](https://github.com/dscripka/openWakeWord) and supports custom wake-word
models in ONNX and TFLite formats. The easiest workflow is to train a model in Google Colab, convert
it when necessary, and add it to GLaSSIST's `models/` directory.

## 1. Train a model

Choose one of the openWakeWord notebooks:

- [Basic training](https://colab.research.google.com/drive/1q1oe2zOyZp7UsB3jJiQ1IFn8z5YfjwEb?usp=sharing) — recommended for your first model
- [Advanced training](https://colab.research.google.com/drive/1yyFH-fpguX2BTAW8wSQxTrJnJTM-0QAd?usp=sharing) — more control over training and model quality

Run every notebook step and download the generated `.tflite` model.

## 2. Convert the model for Windows

The Colab notebooks produce a TFLite model. Modern Windows installations of GLaSSIST use ONNX
Runtime, so the model must be converted to `.onnx` before it can be used on Windows. ONNX is also the
most portable choice if you want to use the same model on both Windows and Linux.

Install the conversion tools in a separate virtual environment:

```bash
python -m venv wake-word-converter
```

Activate it on Windows:

```powershell
wake-word-converter\Scripts\Activate.ps1
```

Or on Linux:

```bash
source wake-word-converter/bin/activate
```

Install TensorFlow and tf2onnx:

```bash
python -m pip install tensorflow tf2onnx
```

Convert the downloaded model:

```bash
python -m tf2onnx.convert --tflite your_model.tflite --output your_model.onnx
```

Replace `your_model` with the actual filename. Keep the filename simple: use letters, numbers, and
underscores, for example `hey_glassist.onnx`.

Linux can use `.tflite` directly when a compatible TFLite runtime is installed. Otherwise, use the
converted `.onnx` model.

## 3. Install the model

1. Open GLaSSIST Settings and go to **Wake Word**.
2. Use **Open Models Folder**, or open the repository's `models/` directory when running from source.
3. Copy the `.onnx` or supported `.tflite` file into that directory.
4. Refresh the model list.
5. Add the model using its filename without the extension. For `hey_glassist.onnx`, select or enter
   `hey_glassist`.
6. Save the settings and restart wake-word detection if it is already running.

## 4. Test and tune

Start with the default detection threshold of `0.5`. If GLaSSIST activates too easily, raise the
threshold. If it regularly misses the wake word, lower it in small steps. Test from different
distances, with normal room noise, and with voices other than the one used during training.

Custom models can behave beautifully in a quiet test and develop selective hearing the moment they
meet a real room. Test before relying on one for important automations.
