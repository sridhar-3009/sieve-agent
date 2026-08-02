"""The wake-word matcher is a pure function — so it gets deterministic evals.
Whisper mangles phrases in predictable ways; these cases pin the fuzziness."""

import pytest

from sieve_agent.gateway.voice import matches_wake

SHOULD_WAKE = [
    ("hey sieve", "hey sieve"),
    ("Hey, Sieve!", "hey sieve"),                # punctuation
    ("heysieve", "hey sieve"),                   # whisper drops the space
    ("so anyway hey sieve schedule it", "hey sieve"),  # embedded in speech
    ("hey siv", "hey sieve"),                    # one-word mangle → fuzzy match
    ("Hey Sieve", "hey sieve"),
    ("hey computer, what's up", "hey computer"),
    # regression from the first live session: whisper wrote the wake word in
    # kana — variants after a comma cover other scripts
    ("しーぶ", "hey sieve,しーぶ"),
    ("しーぶしーぶ", "hey sieve,しーぶ"),
    ("小助手你好", "hey sieve,小助手"),
]

SHOULD_NOT_WAKE = [
    ("what a nice day", "hey sieve"),
    ("wake up call at nine", "hey sieve"),
    ("", "hey sieve"),
    ("hey sieve", ""),                            # no wake word configured
    ("have you seen my keys", "hey sieve"),
]


@pytest.mark.parametrize("heard,wake", SHOULD_WAKE, ids=[h for h, _ in SHOULD_WAKE])
def test_wakes(heard, wake):
    assert matches_wake(heard, wake)


@pytest.mark.parametrize("heard,wake", SHOULD_NOT_WAKE, ids=[h or "empty" for h, _ in SHOULD_NOT_WAKE])
def test_stays_asleep(heard, wake):
    assert not matches_wake(heard, wake)
