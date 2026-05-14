"""Vision tools for Project Iceberg.

Uses vision-capable models served by Ollama (moondream2, llava, bakllava, etc.).
No cloud API needed — fully local and offline-capable.

Available tools:
    analyze_image(path, prompt)      — describe or answer questions about an image file
    capture_screen(prompt)           — screenshot the primary display and analyze it
    read_text_from_image(path)       — OCR: extract text from an image (receipt, doc, etc.)

Requirements:
    pip install pillow
    ollama pull moondream        # fast (~1.7 GB, great for captions + simple Q&A)
    ollama pull llava             # richer reasoning (~4 GB, better for complex questions)

The VISION_MODEL constant below selects which model is used. moondream is the
default because it's small, very fast on a 1080 Ti, and handles 95% of use cases.
Switch to "llava" in constants.py if you need stronger visual reasoning.
"""

from __future__ import annotations

import base64
import os

import requests

from agent_core.constants import OLLAMA_HOST_URL, OLLAMA_VISION_MODEL

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _image_to_base64(path: str) -> str:
    """Read an image file and return its base64 string."""
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def _ollama_vision(image_b64: str, prompt: str) -> str:
    """Call the Ollama /api/generate endpoint with a vision model + image."""
    url = f"{OLLAMA_HOST_URL}/api/generate"
    payload = {
        "model": OLLAMA_VISION_MODEL,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except requests.exceptions.ConnectionError:
        return (
            f"[vision error] Ollama is not reachable at {OLLAMA_HOST_URL}. "
            "Make sure Ollama is running: `ollama serve`"
        )
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return (
                f"[vision error] Model '{OLLAMA_VISION_MODEL}' not found. "
                f"Pull it with: ollama pull {OLLAMA_VISION_MODEL}"
            )
        return f"[vision error] HTTP {e.response.status_code}: {e}"
    except Exception as e:
        return f"[vision error] {e}"


# ---------------------------------------------------------------------------
# Public tools
# ---------------------------------------------------------------------------


def analyze_image(path: str, prompt: str = "Describe this image in detail.") -> str:
    """Analyze an image file and answer questions about it.

    Args:
        path:   Absolute or relative path to the image (JPEG, PNG, GIF, BMP, WEBP).
        prompt: What to ask about the image. Default: general description.

    Returns:
        The model's response as a string, or an error message.

    Examples:
        analyze_image("screenshot.png")
        analyze_image("photo.jpg", "What objects are in the foreground?")
        analyze_image("chart.png", "What trend does this graph show?")
    """
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return f"[vision error] File not found: {path}"

    try:
        image_b64 = _image_to_base64(path)
    except Exception as e:
        return f"[vision error] Could not read image: {e}"

    return _ollama_vision(image_b64, prompt)


def capture_screen(prompt: str = "Describe what is on the screen.") -> str:
    """Take a screenshot of the primary display and analyze it with a vision model.

    Args:
        prompt: What to ask about the screen contents. Default: general description.

    Returns:
        The model's response as a string, or an error message.

    Requires: pip install pillow
    """
    try:
        from PIL import ImageGrab  # type: ignore
    except ImportError:
        return "[vision error] Pillow is not installed. " "Install it with: pip install pillow"

    import io

    try:
        screenshot = ImageGrab.grab()
        buf = io.BytesIO()
        screenshot.save(buf, format="PNG")
        image_b64 = base64.standard_b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        return f"[vision error] Screenshot failed: {e}"

    return _ollama_vision(image_b64, prompt)


def read_text_from_image(path: str) -> str:
    """Extract text from an image using OCR via the vision model.

    Better than traditional Tesseract OCR for messy handwriting, stylised fonts,
    screenshots with mixed content, or images with text in unusual layouts.

    Args:
        path: Path to the image file.

    Returns:
        Extracted text content, preserving layout as best as possible.
    """
    ocr_prompt = (
        "Please extract and transcribe ALL text visible in this image exactly as it "
        "appears. Preserve line breaks and structure. Do not add commentary — output "
        "only the transcribed text."
    )
    return analyze_image(path, ocr_prompt)
