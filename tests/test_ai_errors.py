"""AI-service errors read out by Home Assistant become short friendly sentences."""
from unittest.mock import Mock, patch

import pytest

import ai_errors
import i18n
from satellite_protocol import VoiceSatelliteProtocol
from aioesphomeapi.model import VoiceAssistantEventType as Event

GEMINI_503 = ('Sorry, I had a problem getting a response from Google Generative AI.: {\n  "error": {\n'
              '    "code": 503,\n    "message": "This model is currently experiencing high demand.",\n'
              '    "status": "UNAVAILABLE"\n  }\n}')


@pytest.fixture(autouse=True)
def language(monkeypatch, tmp_path):
    import tempfile
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path))     # error speech files stay in the test dir
    yield
    i18n.set_language('en')


def test_the_real_gemini_503_is_explained_in_portuguese():
    i18n.set_language('pt_BR')
    assert ai_errors.friendly_error(GEMINI_503) == (
        'O serviço de IA (Google Generative AI) está sobrecarregado agora. Tente de novo em alguns segundos.')


def test_same_error_in_polish_and_english():
    i18n.set_language('pl')
    assert 'przeciążona' in ai_errors.friendly_error(GEMINI_503)
    i18n.set_language('en')
    assert ai_errors.friendly_error(GEMINI_503).startswith('The AI service (Google Generative AI) is overloaded')


@pytest.mark.parametrize('detail, expected', [
    ('"code": 429, "status": "RESOURCE_EXHAUSTED"', 'limite de uso'),
    ('"code": 403, "message": "API key not valid"', 'recusou a chave'),
    ('"code": 504, "status": "DEADLINE_EXCEEDED"', 'demorou demais'),
    ('"code": 500, "status": "INTERNAL"', 'erro interno'),
    ('something else entirely', 'Não consegui uma resposta'),
])
def test_other_kinds_of_error(detail, expected):
    i18n.set_language('pt_BR')
    text = f'Sorry, I had a problem getting a response from OpenAI.: {{{detail}}}'
    assert expected in ai_errors.friendly_error(text)


@pytest.mark.parametrize('text, provider, kind', [
    ('Sorry, I had a problem getting a response from Google Generative AI.', 'Google Generative AI', 'answer'),
    ('Sorry, I had a problem getting a response from Google Generative AI. Reason: SAFETY',
     'Google Generative AI', 'answer'),
    ('Sorry, I had a problem talking to the Ollama server: timed out', 'the Ollama server', 'too long'),
    ('Error talking to OpenAI', 'OpenAI', 'answer'),
    ('Anthropic API error: overloaded_error.', 'Anthropic', 'overloaded'),
    ('Authentication error with Anthropic API: invalid x-api-key. Reauthentication required.',
     'Anthropic', 'access key'),
    ('Error communicating with the OpenRouter API: 429 Too Many Requests', 'OpenRouter', 'usage limit'),
])
def test_error_answers_of_the_ha_integrations(text, provider, kind):
    friendly = ai_errors.friendly_error(text)
    assert f'({provider})' in friendly and kind in friendly


@pytest.mark.parametrize('text', [
    'Pronto.', 'A luz da sala está ligada.', 'It is 503 degrees', '', None,
    'There is an error from the dishwasher: E15 means a leak.',
    'The vacuum reported an unexpected error.',
    'Sorry, I had a problem turning on the kitchen light.',
    'The international station is unavailable.',
])
def test_normal_answers_are_left_alone(text):
    assert ai_errors.friendly_error(text) is None


def test_internal_needs_the_whole_word():
    text = 'Sorry, I had a problem getting a response from International AI: something else'
    assert 'internal error' not in ai_errors.friendly_error(text)


def test_synthesis_is_skipped_outside_windows(tmp_path):
    with patch('ai_errors.sys.platform', 'linux'):
        assert ai_errors.synthesize('oi', str(tmp_path / 'x.wav')) is False


# ---- satellite integration (3.9.0 playback: cancellable, on the loop, with fallback)
def make_protocol():
    protocol = VoiceSatelliteProtocol(device_name='t', mac_address='02:00:00:00:00:01',
                                      animation_server=Mock(), on_tts_url=Mock(), on_tts_finished=Mock())
    protocol.send_messages = Mock()
    return protocol


class InlineThread:
    """Runs the synthesis thread synchronously so the test sees its effect immediately."""
    def __init__(self, target, **kwargs):
        self.target = target

    def start(self):
        self.target()


def run_error_reply(protocol, synthesize, events_before_end=()):
    with patch('satellite_protocol.media_ducker'), patch('utils.processing_sound_loop'), \
         patch('satellite_protocol.ai_errors.synthesize', side_effect=synthesize) as synth, \
         patch('satellite_protocol.threading.Thread', InlineThread):
        protocol._handle_voice_event(Event.VOICE_ASSISTANT_RUN_START, {})
        protocol._handle_voice_event(Event.VOICE_ASSISTANT_TTS_START, {'text': GEMINI_503})
        for event, data in events_before_end:
            protocol._handle_voice_event(event, data)
        protocol._handle_voice_event(Event.VOICE_ASSISTANT_TTS_END, {'url': 'http://ha/api/tts_proxy/x.mp3'})
    return synth


def test_error_answer_is_shown_and_spoken_locally_instead_of_the_english_audio():
    i18n.set_language('pt_BR')
    protocol = make_protocol()
    synth = run_error_reply(protocol, lambda text, path: True)
    shown = protocol._animation_server.send_response_text.call_args.args[0]
    assert 'sobrecarregado' in shown and '503' not in shown
    spoken, path = synth.call_args.args
    assert 'sobrecarregado' in spoken
    played = protocol._on_tts_url.call_args
    assert played.args[0] == path and path.endswith('.wav')     # local speech, not HA's English audio
    assert played.kwargs['cancel_event'] is protocol._playback_cancel

    protocol._handle_voice_event(Event.VOICE_ASSISTANT_RUN_END, {})
    protocol._on_tts_finished.assert_not_called()               # still speaking
    played.kwargs['done_callback'](True)
    protocol._on_tts_finished.assert_called_once()


def test_without_a_voice_home_assistant_audio_is_played():
    protocol = make_protocol()
    run_error_reply(protocol, lambda text, path: False)
    played = protocol._on_tts_url.call_args
    assert played.args[0] == 'http://ha/api/tts_proxy/x.mp3'
    assert played.kwargs['cancel_event'] is protocol._playback_cancel


def test_hotkey_during_synthesis_plays_nothing():
    protocol = make_protocol()

    def synthesize(text, path):
        protocol.cancel_interaction()                          # pressed while the voice is generated
        return True

    run_error_reply(protocol, synthesize)
    protocol._on_tts_url.assert_not_called()
    assert protocol._tts_override is None


def test_streamed_reply_keeps_home_assistant_audio():
    protocol = make_protocol()
    with patch('satellite_protocol.media_ducker'), patch('utils.processing_sound_loop'), \
         patch('satellite_protocol.ai_errors.synthesize') as synth:
        protocol._handle_voice_event(Event.VOICE_ASSISTANT_RUN_START, {'url': 'http://ha/stream.mp3'})
        protocol._handle_voice_event(Event.VOICE_ASSISTANT_INTENT_PROGRESS, {'tts_start_streaming': '1'})
        protocol._handle_voice_event(Event.VOICE_ASSISTANT_TTS_START, {'text': GEMINI_503})
        protocol._handle_voice_event(Event.VOICE_ASSISTANT_TTS_END, {'url': 'http://ha/stream.mp3'})
    synth.assert_not_called()
    protocol._on_tts_url.assert_called_once()
    assert protocol._on_tts_url.call_args.kwargs['streaming'] is True


def test_normal_answer_still_plays_the_home_assistant_audio():
    protocol = make_protocol()
    with patch('satellite_protocol.media_ducker'), patch('utils.processing_sound_loop'), \
         patch('satellite_protocol.ai_errors.synthesize') as synth:
        protocol._handle_voice_event(Event.VOICE_ASSISTANT_RUN_START, {})
        protocol._handle_voice_event(Event.VOICE_ASSISTANT_TTS_START, {'text': 'Pronto.'})
        protocol._handle_voice_event(Event.VOICE_ASSISTANT_TTS_END, {'url': 'http://ha/x.mp3'})
    synth.assert_not_called()
    protocol._on_tts_url.assert_called_once()
    assert protocol._on_tts_url.call_args.args[0] == 'http://ha/x.mp3'


# ---- review follow-ups
@pytest.mark.parametrize('text, kind', [
    ('Error talking to OpenAI: Error code: 429 - Rate limit reached for gpt-4o. Limit 30000, Used 29873, '
     'Requested 503.', 'usage limit'),
    ('Sorry, I had a problem getting a response from Google Generative AI.: {"error": {"code": 403, '
     '"message": "Your quota project does not have access"}}', 'access key'),
    ('Anthropic API error: rate_limit_error.', 'usage limit'),
])
def test_the_reported_status_decides_the_kind(text, kind):
    assert kind in ai_errors.friendly_error(text)


@pytest.mark.parametrize('text', [
    'Sorry, I had a problem talking to the TV: it is off.',
    'Weather API error: the station is down',
])
def test_device_answers_with_error_wording_are_left_alone(text):
    assert ai_errors.friendly_error(text) is None


def test_hanging_voice_falls_back_to_home_assistant_audio():
    import asyncio
    import threading
    protocol = make_protocol()
    release = threading.Event()

    def synthesize(text, path):
        release.wait(5)
        return True

    async def run():
        protocol._loop = asyncio.get_running_loop()
        with patch('satellite_protocol.media_ducker'), patch('utils.processing_sound_loop'), \
             patch('satellite_protocol.ai_errors.synthesize', side_effect=synthesize), \
             patch('satellite_protocol.ERROR_SPEECH_TIMEOUT', 0.05):
            protocol._handle_voice_event(Event.VOICE_ASSISTANT_RUN_START, {})
            protocol._handle_voice_event(Event.VOICE_ASSISTANT_TTS_START, {'text': GEMINI_503})
            protocol._handle_voice_event(Event.VOICE_ASSISTANT_TTS_END, {'url': 'http://ha/x.mp3'})
            await asyncio.sleep(0.2)
            assert protocol._on_tts_url.call_args.args[0] == 'http://ha/x.mp3'
            release.set()
            await asyncio.sleep(0.2)
        assert protocol._on_tts_url.call_count == 1                # the late voice is not played too

    asyncio.run(run())


def test_each_error_reply_gets_its_own_file_and_the_old_one_is_removed():
    import os
    protocol = make_protocol()
    run_error_reply(protocol, lambda text, path: True)
    first = protocol._on_tts_url.call_args.args[0]
    protocol._on_tts_url.call_args.kwargs['done_callback'](True)
    protocol._handle_voice_event(Event.VOICE_ASSISTANT_RUN_END, {})
    run_error_reply(protocol, lambda text, path: True)
    second = protocol._on_tts_url.call_args.args[0]
    assert first != second and not os.path.exists(first) and os.path.exists(second)
    protocol._remove_error_speech()
