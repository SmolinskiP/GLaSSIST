"""Plain-language version of AI-service errors that Home Assistant reads out as raw text.

When a conversation agent fails (Google Gemini answers "503 Service Unavailable", a quota is
used up, a key is refused...), Home Assistant sends the technical error as the spoken answer, in
English, with the provider's JSON. This module recognises those answers and returns a short,
friendly sentence in the interface language (HA_LANGUAGE, see i18n.py), which GLaSSIST shows and,
on Windows, speaks with an installed voice of that language.
"""
import re
import sys
from typing import Optional

import i18n
import utils

logger = utils.setup_logger()

# Only the exact way Home Assistant's AI integrations start an error answer, so a normal answer
# that merely mentions an error ("error from the dishwasher") is never replaced.
_ERROR_ANSWERS = (
    # Google Generative AI, Ollama and others
    re.compile(r"^Sorry, I had a problem (?:getting a response from|talking to)\s+"
               r"(?P<provider>[^:\n]+?)(?:\.?:|\.\s|\.?\s*$)", re.I),
    re.compile(r"^Error talking to\s+(?P<provider>[^:\n]+?)(?:\.?:|\.\s|\.?\s*$)", re.I),   # OpenAI
    re.compile(r"^Authentication error with\s+(?P<provider>.+?)\s+API\b", re.I),            # Anthropic
    re.compile(r"^(?P<provider>[\w .-]+?)\s+API error:", re.I),                             # Anthropic
    re.compile(r"^Error communicating with (?:the\s+)?(?P<provider>.+?)\s+API\b", re.I),    # OpenRouter
)
# The provider must look like an AI service, so "a problem talking to the TV" stays an answer.
_AI_PROVIDER = re.compile(r"(?<![a-z])(ai|gpt|gemini|google|ollama|openai|anthropic|claude|mistral|"
                          r"openrouter|llm|groq|deepseek|grok|xai|cohere|perplexity|azure|bedrock|"
                          r"llama|qwen|server)(?![a-z])", re.I)

# (status codes, words, English template). {} is the provider name.
_KINDS = (
    ({"503", "529"}, ("unavailable", "high demand", "overloaded"),
     "The AI service ({}) is overloaded right now. Try again in a few seconds."),
    ({"429"}, ("resource exhausted", "quota", "rate limit", "too many requests"),
     "The usage limit of the AI service ({}) was reached for now. Try again later."),
    ({"401", "403"}, ("api key", "permission denied", "unauthenticated", "authentication"),
     "The AI service ({}) refused the access key. Check the key in Home Assistant."),
    ({"504"}, ("timeout", "timed out", "deadline"),
     "The AI service ({}) took too long to answer. Try again."),
    ({"500", "502"}, ("internal",),
     "The AI service ({}) had an internal error. Try again in a moment."),
)
_GENERIC = "I could not get an answer from the AI service ({}) right now. Try again."
# Only numbers in a status position, not any number in the text ("Requested 503" tokens).
_STATUS_CODE = re.compile(r'"code"\s*:\s*(\d{3})\b|\b(?:error code|status code|status|code)\s*[:=]?\s*(\d{3})\b'
                          r'|\b(\d{3})\s+(?-i:[A-Z][a-z]+)', re.I)   # "429 Too Many Requests"

_CULTURES = {"en": "en-US", "pl": "pl-PL", "pt_BR": "pt-BR"}
_SPEECH_ASSEMBLY = "System.Speech, Version=3.0.0.0, Culture=neutral, PublicKeyToken=31bf3856ad364e35"


def _has_word(text: str, word: str) -> bool:
    # Letters only as boundaries: "overloaded_error" matches, "international" does not.
    return re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", text) is not None


def friendly_error(text: Optional[str]) -> Optional[str]:
    """The friendly sentence for an AI-service error answer, or None for a normal answer."""
    if not text:
        return None
    text = text.strip()
    match = next((m for m in (p.match(text) for p in _ERROR_ANSWERS) if m), None)
    if match is None or not _AI_PROVIDER.search(match.group("provider")):
        return None
    provider = match.group("provider").strip()
    words_text = re.sub(r"[_-]", " ", text.lower())
    codes = [code for groups in _STATUS_CODE.findall(text) for code in groups if code]
    # The reported status decides; words only when no known status code is given.
    template = next((t for code in codes for kind_codes, _, t in _KINDS if code in kind_codes), None)
    if template is None:
        template = next((t for _, words, t in _KINDS if any(_has_word(words_text, w) for w in words)),
                        _GENERIC)
    return i18n.t(template.format(provider))


def speech_culture() -> str:
    return _CULTURES.get(i18n.get_language(), "en-US")


def synthesize(text: str, path: str) -> bool:
    """Write ``text`` spoken by a Windows voice of the interface language to ``path`` (WAV).

    Uses System.Speech in-process through pythonnet (already loaded for the overlay window), so
    there is no extra process and the result plays like any other reply: on the selected output
    device, with the animation and cancellable by the hotkey or wake word. Returns False when that
    is not possible (not Windows, no voice of that language); the caller then plays Home
    Assistant's own audio.
    """
    if sys.platform != "win32":
        return False
    culture = speech_culture()
    try:
        import clr
        clr.AddReference(_SPEECH_ASSEMBLY)
        from System.Speech.Synthesis import SpeechSynthesizer

        synth = SpeechSynthesizer()
        try:
            voices = [v.VoiceInfo for v in synth.GetInstalledVoices() if v.Enabled]
            language = culture.split("-")[0]
            voice = (next((v for v in voices if v.Culture.Name == culture), None)
                     or next((v for v in voices if v.Culture.Name.split("-")[0] == language), None))
            if voice is None:
                logger.info(f"No Windows voice for {culture}; playing Home Assistant's audio instead")
                return False
            synth.SelectVoice(voice.Name)
            synth.SetOutputToWaveFile(path)
            synth.Speak(text)
            synth.SetOutputToNull()
            return True
        finally:
            synth.Dispose()
    except Exception:
        logger.warning("Local speech for the AI error failed; playing Home Assistant's audio", exc_info=True)
        return False
