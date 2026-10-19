"""AI-service errors read out by Home Assistant become short friendly sentences."""
import asyncio
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
def language():
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


@pytest.mark.parametrize('text', ['Pronto.', 'A luz da sala está ligada.', 'It is 503 degrees', '', None])
def test_normal_answers_are_left_alone(text):
    assert ai_errors.friendly_error(text) is None


def make_protocol():
    protocol = VoiceSatelliteProtocol(device_name='t', mac_address='02:00:00:00:00:01',
                                      animation_server=Mock(), on_tts_url=Mock(), on_tts_finished=Mock())
    protocol._loop = asyncio.new_event_loop()
    protocol._transport = Mock()
    protocol.send_messages = Mock()
    return protocol


def test_error_answer_is_shown_and_spoken_locally_instead_of_the_english_audio():
    i18n.set_language('pt_BR')
    protocol = make_protocol()
    with patch('satellite_protocol.ai_errors.speak') as speak:
        protocol._handle_voice_event(Event.VOICE_ASSISTANT_RUN_START, {})
        protocol._handle_voice_event(Event.VOICE_ASSISTANT_TTS_START, {'text': GEMINI_503})
        shown = protocol._animation_server.send_response_text.call_args.args[0]
        assert 'sobrecarregado' in shown and '503' not in shown
        protocol._handle_voice_event(Event.VOICE_ASSISTANT_TTS_END, {'url': 'http://ha/api/tts_proxy/x.mp3'})
    (spoken,), kwargs = speak.call_args
    assert 'sobrecarregado' in spoken
    protocol._on_tts_url.assert_not_called()                  # the English audio is not played
    kwargs['on_unavailable']()                                # no Portuguese voice: fall back to HA's audio
    protocol._on_tts_url.assert_called_once()
    assert protocol._on_tts_url.call_args.args[0] == 'http://ha/api/tts_proxy/x.mp3'


def test_normal_answer_still_plays_the_home_assistant_audio():
    protocol = make_protocol()
    with patch('satellite_protocol.ai_errors.speak') as speak:
        protocol._handle_voice_event(Event.VOICE_ASSISTANT_RUN_START, {})
        protocol._handle_voice_event(Event.VOICE_ASSISTANT_TTS_START, {'text': 'Pronto.'})
        protocol._handle_voice_event(Event.VOICE_ASSISTANT_TTS_END, {'url': 'http://ha/x.mp3'})
    speak.assert_not_called()
    protocol._on_tts_url.assert_called_once()


def test_speak_falls_back_when_not_windows_or_no_voice():
    done, unavailable = Mock(), Mock()
    with patch('ai_errors.sys.platform', 'linux'):
        t = ai_errors.speak('oi', done, unavailable)
    import time
    for _ in range(50):
        if unavailable.called:
            break
        time.sleep(0.02)
    unavailable.assert_called_once()
    done.assert_not_called()
