# Handoff — issue #48 "No context?" (conversation_id)

Written 2026-07-25 on the Linux box, to be implemented on the owner's Windows machine.
Analysis is done and verified against the code; nothing has been changed yet. This file
is the whole brief — you don't need the originating session.

Read `docs/AI-HANDOFF.md` first for who the owner is and how they like to work
(Polish, pragmatic, zero ceremony, commits straight to `main`).

## The bug

[#48](https://github.com/SmolinskiP/GLaSSIST/issues/48), reported by RheaAyase (Linux/Flatpak,
LLM conversation agent in HA). "Turn it off again" 30 seconds after "turn the light on" gets
answered with *"Could you please specify which area or device you'd like to control?"* — the
same follow-up works fine in HA's own text Assist.

Home Assistant keys conversation history by `conversation_id`. GLaSSIST never reads the real
one from HA and never sends one back, so every activation starts a fresh conversation with
zero history.

Not platform-specific — it is broken on Windows too. It only *shows* with an LLM agent;
with HA's default intent engine "turn it off again" fails for unrelated reasons, so nobody
filed it.

## Root cause

`client.py:227-234` (inside `start_assist_pipeline`) stuffs a synthetic string into the
`conversation_id` field of the outgoing `assist_pipeline/run`:

```python
if hasattr(self, '_conversation_context') and self._conversation_context:
    original_question = getattr(self, '_original_question', 'Unknown question')
    context_info = f"CONTEXT: {self._conversation_context} QUESTION: {original_question}"
    pipeline_params["conversation_id"] = context_info[:100]  # Limit length
```

HA treats `conversation_id` as an opaque key: an unrecognised value simply starts a *new*
conversation under that key. So this produces a different bogus conversation every turn —
and in the normal case (`_conversation_context` is `None`) no id is sent at all, and HA
generates a fresh one each run. Either way: no history.

**Critical de-risking fact — this hack is dead weight.** The interactive-prompt feature
(prompt_server → `conversation_manager.py`) does *not* consume it. Its context travels as
plain text in `client.py:369`:

```python
combined_text = f"{context_instructions} User was asked: '{original_question}' and responded: '{stt_text}'. Execute appropriate action and confirm what was done."
```

which goes straight into the `conversation.process` service call. Nothing anywhere reads
`conversation_id` back. Deleting the block above breaks no feature. Verify with
`grep -rn "conversation_id" *.py` before and after — the only hits should be the ones you add.

## What to build

Real `conversation_id` round-tripping with a sliding expiry measured from the last turn.

### 1. `client.py` — delete the hack

Remove `client.py:227-234` entirely (the `if hasattr(self, '_conversation_context')` block
and its `logger.info`). Leave `_conversation_context` itself alone — it still drives the
`conversation.process` path at `client.py:354`.

### 2. `client.py` — capture the real id

In `receive_response`, alongside the existing event handling (the loop around
`client.py:559-567`), extract `conversation_id` from **both** of these shapes:

- `event.data.conversation_id` — sent with `intent-start`
- `event.data.intent_output.conversation_id` — sent with `intent-end`

Read both rather than picking one. The payload shape differs between HA versions and this
was analysed without a live HA instance to confirm against — checking two places is cheap
insurance. First non-empty value wins; `intent-end` should overwrite `intent-start` if both
arrive.

Store on the client: `self._last_conversation_id` and `self._last_conversation_ts`
(`time.time()`). Initialise both to `None`/`0` in `__init__` next to `self.audio_url`
(`client.py:29`).

Log at INFO when an id is captured and when one is reused — the owner debugs these issues
from user-submitted logs, so make them greppable.

### 3. `client.py` — send it back

In `start_assist_pipeline`, where the removed block used to be:

```python
timeout = utils.get_env("HA_CONVERSATION_TIMEOUT", 300, int)
if (timeout > 0 and self._last_conversation_id
        and time.time() - self._last_conversation_ts < timeout):
    pipeline_params["conversation_id"] = self._last_conversation_id
else:
    self._last_conversation_id = None
```

`timeout <= 0` disables the feature. Outside the window, clear the id and send nothing —
HA then mints a fresh one.

### 4. `HA_CONVERSATION_TIMEOUT` — the name already exists and is dead

`conversation_manager.py:20` reads it with a default of 15, assigns it to
`self.conversation_timeout`, and nothing ever reads that attribute. In the same file
`self.current_conversation` is only ever assigned `None`, so `get_conversation_info()` and
the `['timeout']` lookup at line 385 are unreachable. The var appears nowhere else in the
repo — not in `.env.example`, not in the settings UI. Nobody has it set, so the name is free
to take over.

Either delete the dead line 20 or leave it; don't try to share the value between the two.

**Default 300 seconds**, not 15. Two reasons: the reporter's own example is "30 seconds ago",
which 15 would miss; and HA's `default_agent` expires conversation history after 5 minutes
server-side, so a longer client-side window would just be a lie — we'd send an id the server
already dropped. `0` = off, for anyone who doesn't want the next command inheriting the
previous one's context.

### 5. Surface it — this is the whole point of not repeating history

- `.env.example`: add `HA_CONVERSATION_TIMEOUT=300` with a one-line comment.
- `flet_settings.py`, four places, follow `HA_SILENCE_THRESHOLD_SEC` as the template:
  - `:101` / `:124` — load into `current_settings`
  - `:516-522` — the slider + its "Current: …" label (put this one near
    `HA_CONTINUE_ON_QUESTION` at `:498`, it belongs with conversation behaviour)
  - `:1988` / `:2022` — collect the widget value on save
  - `:2080` / `:2097` — write the line into `.env`

  A slider is awkward for 0–600 with a meaningful `0`; a numeric text field with validation
  is probably the better fit. Owner's call if you want to ask.
- `CLAUDE.md` / README config table if either lists env vars.

## Acceptance criteria

1. "Turn on the desk light" → wait ~30 s → "turn it off again" works with an LLM agent,
   no clarification question.
2. Log shows the **same** `conversation_id` across both turns.
3. After `HA_CONVERSATION_TIMEOUT` elapses, the next command gets a **new** id and no
   inherited context.
4. `HA_CONVERSATION_TIMEOUT=0` → no `conversation_id` ever sent.
5. Interactive prompts (prompt_server) still work end to end — that's the one feature that
   touches this code path.
6. `grep -rn "CONTEXT: " *.py` returns nothing.

## Gotchas

- **`utils.get_env` reads the `.env` FILE first**, `os.environ` is only a fallback. Any test
  patching the environment must mock `utils._read_from_env_file` or the developer's real
  `.env` leaks into the test. See `TestSoundConfiguration` in `tests/test_utils.py` for the
  established pattern.
- **The test suite is stale** — roughly 107 of ~180 tests fail on `main` for unrelated
  reasons (pygame mocks left over from before the sounddevice migration, missing
  pytest-asyncio, animation_server API drift). Don't chase them. Run
  `python -m pytest tests/test_client.py tests/test_utils.py -v` and judge against the
  pre-existing failure set.
- `client.py:451-545` is a second, parallel pipeline path (`conversation.process` +
  TTS-only run, returning "fake results"). It builds its own `tts_pipeline` dict — it does
  **not** go through `start_assist_pipeline`, so your change doesn't reach it. Whether that
  path should also carry the conversation id is a separate question; leave it for now.
- Don't touch `receive_response`'s break condition while you're in there. It currently exits
  on `intent-end`, which is a real bug — but it's **issue #31**, not this one, and fixing it
  blind will confuse the two. Separate commit, separate issue.

## Not in scope

Issues #31 (premature TTS cutoff) and #49 (no words detected) were analysed in the same
session and are genuinely different bugs. #49 in particular is largely a Linux exposure
problem (no echo cancellation on PipeWire, so the activation beep loops back into the mic and
false-triggers the VAD, which then ends the turn on the following pause) — hard to reproduce
on Windows, don't attempt it from there.
