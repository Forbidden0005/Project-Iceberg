"""Microphone listener using SpeechRecognition + Google recognizer."""

import speech_recognition as sr

from agent_core.constants import (
    VOICE_AMBIENT_NOISE_DURATION_SECONDS,
    VOICE_LISTEN_TIMEOUT_SECONDS,
    VOICE_PHRASE_TIME_LIMIT_SECONDS,
)


def listen(
    timeout: float = VOICE_LISTEN_TIMEOUT_SECONDS,
    phrase_time_limit: float = VOICE_PHRASE_TIME_LIMIT_SECONDS,
):
    r = sr.Recognizer()

    try:
        with sr.Microphone() as src:
            r.adjust_for_ambient_noise(src, duration=VOICE_AMBIENT_NOISE_DURATION_SECONDS)
            audio = r.listen(src, timeout=timeout, phrase_time_limit=phrase_time_limit)
    except sr.WaitTimeoutError:
        return None
    except Exception as e:
        print(f"[voice input error] {e}")
        return None

    try:
        return r.recognize_google(audio)
    except sr.UnknownValueError:
        return None
    except sr.RequestError as e:
        print(f"[voice recognition error] {e}")
        return None
