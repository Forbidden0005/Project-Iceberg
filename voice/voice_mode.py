"""Voice mode loop. Imports audio libs lazily so CLI mode works without them."""


def run_voice_mode(agent):
    try:
        # Lazy import: voice deps are optional and may not be installed.
        from voice.input import listen  # noqa: PLC0415
        from voice.output import speak  # noqa: PLC0415
    except ImportError as e:
        print(f"[voice] audio libraries missing: {e}")
        print("[voice] install with: pip install SpeechRecognition pyttsx3 pyaudio")
        return

    print("Voice mode active. Say 'exit' to quit.")
    while True:
        text = listen()
        if not text:
            continue

        print(f"> {text}")
        if "exit" in text.lower() or "quit" in text.lower():
            speak("Goodbye.")
            break

        results = agent.run(text)
        for r in results:
            print(r)
            speak(str(r))
