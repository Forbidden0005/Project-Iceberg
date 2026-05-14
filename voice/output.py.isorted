"""Text-to-speech output via pyttsx3."""

import pyttsx3

_engine = None


def _get_engine():
    # pyttsx3.init() is expensive and its engine object is safe to reuse,
    # so we cache one per process. The global is deliberate.
    global _engine  # noqa: PLW0603
    if _engine is None:
        _engine = pyttsx3.init()
    return _engine


def speak(text: str) -> None:
    if not text:
        return
    try:
        engine = _get_engine()
        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        print(f"[voice output error] {e}")
