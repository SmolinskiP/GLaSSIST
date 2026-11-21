"""Plain-language version of AI-service errors that Home Assistant reads out as raw text.

When a conversation agent fails (Google Gemini answers "503 Service Unavailable", a quota is
used up, a key is refused...), Home Assistant sends the technical error as the spoken answer, in
English, with the provider's JSON. This module recognises those answers and returns a short,
friendly sentence in the interface language (HA_LANGUAGE, see i18n.py), which GLaSSIST shows and,
on Windows, speaks with an installed voice of that language.
"""
import os
import re
import subprocess
import sys
from typing import Callable, Optional

import i18n
import utils

logger = utils.setup_logger()

_MARKERS = re.compile(r"problem getting a response|error talking to|unexpected error|error from", re.I)
_PROVIDER = re.compile(r"(?:getting a response from|talking to|error from)\s+([^.:\n]+?)\s*(?:[.:]|$)", re.I)
_CODE = re.compile(r'"code"\s*:\s*(\d{3})|\b(?:error|status)\D{0,12}(\d{3})\b|\b(\d{3})\s+[A-Z][a-z]+', re.I)

# (matching words or status codes, English template). {} is the provider name.
_KINDS = (
    ({"503", "unavailable", "high demand", "overloaded"},
     "The AI service ({}) is overloaded right now. Try again in a few seconds."),
    ({"429", "resource_exhausted", "quota", "rate limit"},
     "The usage limit of the AI service ({}) was reached for now. Try again later."),
    ({"401", "403", "api key", "permission_denied", "unauthenticated"},
     "The AI service ({}) refused the access key. Check the key in Home Assistant."),
    ({"504", "timeout", "timed out", "deadline"},
     "The AI service ({}) took too long to answer. Try again."),
    ({"500", "502", "internal"},
     "The AI service ({}) had an internal error. Try again in a moment."),
)
_GENERIC = "I could not get an answer from the AI service ({}) right now. Try again."

_CULTURES = {"en": "en-US", "pl": "pl-PL", "pt_BR": "pt-BR"}


def friendly_error(text: Optional[str]) -> Optional[str]:
    """The friendly sentence for an AI-service error answer, or None for a normal answer."""
    if not text or not _MARKERS.search(text):
        return None
    lowered = text.lower()
    codes = {c for groups in _CODE.findall(text) for c in groups if c}
    match = _PROVIDER.search(text)
    provider = match.group(1).strip() if match else "?"
    english = _GENERIC.format(provider)
    for words, template in _KINDS:
        if any((w in codes) if w.isdigit() else (w in lowered) for w in words):
            english = template.format(provider)
            break
    return i18n.t(english)


def speech_culture() -> str:
    return _CULTURES.get(i18n.get_language(), "en-US")


def speak(text: str, on_done: Callable[[], None], on_unavailable: Callable[[], None]) -> None:
    """Speak ``text`` with a Windows voice of the interface language, in a background thread.

    Calls ``on_done`` when finished. When no voice of that language is installed (or this is not
    Windows) calls ``on_unavailable`` instead, so the caller can fall back to Home Assistant's audio.
    """
    import threading

    def run() -> None:
        if sys.platform != "win32":
            on_unavailable()
            return
        script = ("Add-Type -AssemblyName System.Speech; "
                  "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                  "$v = $s.GetInstalledVoices() | Where-Object { $_.Enabled -and "
                  "$_.VoiceInfo.Culture.Name -eq $env:GLASSIST_SPEECH_CULTURE } | Select-Object -First 1; "
                  "if (-not $v) { exit 3 }; $s.SelectVoice($v.VoiceInfo.Name); $s.Speak($env:GLASSIST_SPEECH_TEXT)")
        env = dict(os.environ, GLASSIST_SPEECH_TEXT=text, GLASSIST_SPEECH_CULTURE=speech_culture())
        try:
            result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                                    env=env, timeout=40, creationflags=subprocess.CREATE_NO_WINDOW,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ok = result.returncode == 0
        except Exception:
            logger.debug("Local speech failed", exc_info=True)
            ok = False
        (on_done if ok else on_unavailable)()

    threading.Thread(target=run, name="ai-error-speech", daemon=True).start()
