# Wake word wizard

The wizard trains a custom wake word **in your own language** without Colab, notebooks or TensorFlow.
Open it from **Settings → Wake Word → Create your own wake word**, or run:

```bash
python main.py --wake-word-wizard
```

It takes about 30–40 minutes, most of it waiting. At the end it asks whether you want to test the new
word live and whether to add it to your wake word list.

## Steps

| # | Step | What happens |
|---|------|--------------|
| 1 | **Language & word** | Pick the language and type the word (3–4 syllables work best; avoid common words). |
| 2 | **Training tools** | Creates a separate Python environment (CPU PyTorch, openWakeWord models, edge-tts). ~800 MB, once. |
| 3 | **Voices** | Generates thousands of synthetic clips with neural voices of the chosen language: your word at different speeds and pitches, plus words and phrases that must *not* trigger it. |
| 4 | **Your voice** | You record: the word (~2 min), normal speech (~2 min), the quiet room (30 s) and a separate *exam* set of the word (~75 s). |
| 5 | **Train** | Trains a small head on openWakeWord embeddings, exports `ONNX`, then checks it on the exam recordings and on held-out speech it has never seen, and tells you in plain words if the result is good, usable or not good enough. |
| 6 | **Test** | Live meter: say the word and watch the bar. Then *Add it to my wake word list* (copies the model to `models/` and updates `HA_WAKE_WORD_MODELS`) or *Use only this one*. |

## Why your own voice matters

Synthetic voices alone give a model that works on synthetic voices. Your recordings teach it your
microphone, room and accent, and the *exam* recordings (never used for training) are what makes the
reported numbers honest.

## Privacy

* Your recordings stay on your computer, in the `wakeword_workspace/` folder next to the settings file
  (git-ignored).
* The only data sent anywhere is the **text** of the training phrases, to the Microsoft Edge online
  voices (via the `edge-tts` package, no account or key) to generate synthetic speech.
* The microphone is used only in step 4 and in the live test.

## Supported languages

Each language is a JSON file in [`wakeword_trainer/corpora/`](../wakeword_trainer/corpora/): everyday words
and phrases (used to build the negatives), command templates, the Edge voice locales and the prefixes people say
before a wake word. English, Portuguese (Brazil) and Spanish are included.

To add a language, copy `en.json` to `<code>.json`, translate the lists and set `edge_locales`
(see the output of `edge-tts --list-voices`). It appears in the wizard automatically.

## Command line (optional)

The training steps can run without the UI, in the training environment:

```bash
python -m wakeword_trainer.cli init     --workspace DIR --word Bruninha --language pt
python -m wakeword_trainer.cli generate --workspace DIR
# record clips into DIR/data/real_pos, real_neg, test_pos (16 kHz mono wav) and optionally DIR/data/ambient.wav
python -m wakeword_trainer.cli train    --workspace DIR
python -m wakeword_trainer.cli evaluate --workspace DIR
```

Every command prints one JSON object per line (`progress`, `log`, `result`, `error`).

## Tips for a good model

* Record in the same place and with the same microphone you will use GLaSSIST with.
* Say the word with different energy and distance; let a video or music play during the "normal speech" recording.
* If the result is "usable" or "not good enough", record more speech and more clips and train again: more real
  speech is the quickest way to cut false triggers.
* Words that end like many common words (for example Portuguese `-inha`) need extra negatives; the wizard builds
  them automatically from the language corpus.
* Raise `HA_WAKE_WORD_THRESHOLD` in the settings if it triggers too easily.

## Limits

* The wizard needs Python 3.9–3.12 on the computer to build the training environment (the packaged
  installer cannot install packages by itself).
* Models are ONNX only, which is what GLaSSIST uses on Windows. For Linux `.tflite` or a Home Assistant
  openWakeWord server you would convert them separately.
* Languages other than the included corpora need a corpus file.
