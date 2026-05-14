"""Microphone listener using local Whisper for fully offline speech recognition.

Why Whisper over SpeechRecognition + Google:
  - Zero cloud dependency -- audio never leaves the machine
  - Works without an internet connection
  - Substantially better accuracy, especially for technical vocabulary
  - Runs on CPU or GPU (GTX 1080 Ti will use CUDA automatically if available)

Model size guide (all fit in 11 GB VRAM):
  tiny   -- ~39 MB, fastest, English-only variant available
  base   -- ~74 MB, good balance for short commands
  small  -- ~244 MB, noticeably better accuracy (default)
  medium -- ~769 MB, best for longer dictation
  large  -- ~1.5 GB, highest accuracy, slowest

The model is loaded once at import time and cached for the process lifetime.
GPU / CPU selection is automatic via torch.

Fallback: if openai-whisper or pyaudio is not installed, listen() logs a
clear message and returns None so the voice pipeline degrades gracefully.
"""

from __future__ import annotations

import os
import tempfile

from agent_core.constants import (VOICE_AMBIENT_NOISE_DURATION_SECONDS,
                                  VOICE_LISTEN_TIMEOUT_SECONDS,
                                  VOICE_PHRASE_TIME_LIMIT_SECONDS,
                                  WHISPER_MODEL_SIZE)

# ---------------------------------------------------------------------------
# Lazy imports -- both whisper and pyaudio are optional
# ---------------------------------------------------------------------------

_whisper = None
_sr = None


def _load_whisper():
    global _whisper
    if _whisper is not None:
        return _whisper
    try:
        import whisper

        _whisper = whisper
    except ImportError:
        print("[voice] openai-whisper not installed. " "Run: pip install openai-whisper")
    return _whisper


def _load_sr():
    global _sr
    if _sr is not None:
        return _sr
    try:
        import speech_recognition as sr

        _sr = sr
    except ImportError:
        print(
            "[voice] SpeechRecognition not installed (needed for mic capture). "
            "Run: pip install SpeechRecognition pyaudio"
        )
    return _sr


# ---------------------------------------------------------------------------
# Model cache
# ---------------------------------------------------------------------------

_model_cache = {}


def _get_model(size=None):
    whisper = _load_whisper()
    if whisper is None:
        return None
    size = size or WHISPER_MODEL_SIZE
    if size not in _model_cache:
        try:
            _model_cache[size] = whisper.load_model(size)
        except Exception as e:
            print(f"[voice] Failed to load Whisper model '{size}': {e}")
            return None
    return _model_cache[size]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def listen(
    timeout: float = VOICE_LISTEN_TIMEOUT_SECONDS,
    phrase_time_limit: float = VOICE_PHRASE_TIME_LIMIT_SECONDS,
    model_size: str = None,
):
    """Listen to the microphone and return transcribed text, or None on failure.

    Audio capture uses PyAudio via SpeechRecognition's Microphone class.
    Transcription runs locally via Whisper -- no internet required.
    """
    sr = _load_sr()
    model = _get_model(model_size)
    if sr is None or model is None:
        return None

    recognizer = sr.Recognizer()
    try:
        with sr.Microphone() as src:
            recognizer.adjust_for_ambient_noise(src, duration=VOICE_AMBIENT_NOISE_DURATION_SECONDS)
            audio = recognizer.listen(
                src,
                timeout=timeout,
                phrase_time_limit=phrase_time_limit,
            )
    except sr.WaitTimeoutError:
        return None
    except Exception as e:
        print(f"[voice capture error] {e}")
        return None

    wav_bytes = audio.get_wav_data()
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(wav_bytes)
            tmp_path = tmp.name
        result = model.transcribe(tmp_path, fp16=False, language="en")
        text = result.get("text", "").strip()
        return text if text else None
    except Exception as e:
        print(f"[voice transcription error] {e}")
        return None
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def preload_model(size: str = None) -> bool:
    """Eagerly load the Whisper model so the first listen() call has no delay.

    Call this at startup if voice mode is enabled. Returns True on success.
    """
    return _get_model(size) is not None
