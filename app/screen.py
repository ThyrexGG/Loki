"""On-demand screenshots for screen help (ADR-013).

- Captures ONE screenshot of the primary monitor, only when the user clicks "Look at my screen",
  after a short countdown so they can switch to the window they need help with.
- The image is downscaled (max 1280 px wide, JPEG) and returned to the browser in memory; it is sent
  only to the local Ollama vision model and is never written to disk by Loki.
"""

from __future__ import annotations

import asyncio
import base64
import io
from pathlib import Path

from PIL import Image, ImageGrab

VISION_MODEL = "qwen3-vl:8b"
MAX_WIDTH = 1280
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def _encode_pil_image(img: Image.Image) -> dict:
    orig_w, orig_h = img.size
    w, h = orig_w, orig_h
    if w > MAX_WIDTH or h > MAX_WIDTH:
        scale = min(MAX_WIDTH / max(w, 1), MAX_WIDTH / max(h, 1))
        img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))))
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[3])
        rgb = bg
    else:
        rgb = img.convert("RGB")
    buf = io.BytesIO()
    rgb.save(buf, format="JPEG", quality=85, optimize=True)
    data = buf.getvalue()
    return {
        "image_b64": base64.b64encode(data).decode("ascii"),
        "width": rgb.size[0],
        "height": rgb.size[1],
        "bytes": len(data),
        "screen_width": orig_w,
        "screen_height": orig_h,
    }


def _grab_jpeg_b64() -> dict:
    img = ImageGrab.grab(all_screens=False)  # primary monitor
    return _encode_pil_image(img)


def _grab_clipboard_b64() -> dict | None:
    clip = ImageGrab.grabclipboard()
    if isinstance(clip, Image.Image):
        return {**_encode_pil_image(clip), "label": "Image pasted from clipboard"}
    if isinstance(clip, list):
        for item in clip:
            p = Path(str(item))
            if p.is_file() and p.suffix.lower() in _IMAGE_EXTS:
                with Image.open(p) as im:
                    return {**_encode_pil_image(im), "label": f"Image pasted ({p.name})"}
    return None


async def capture(delay_seconds: float = 3.0) -> dict:
    delay = max(0.0, min(float(delay_seconds), 10.0))
    if delay:
        await asyncio.sleep(delay)
    return await asyncio.to_thread(_grab_jpeg_b64)


async def grab_clipboard() -> dict | None:
    return await asyncio.to_thread(_grab_clipboard_b64)
