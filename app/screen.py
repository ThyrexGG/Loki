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

from PIL import ImageGrab

VISION_MODEL = "qwen3-vl:8b"
MAX_WIDTH = 1280


def _grab_jpeg_b64() -> dict:
    img = ImageGrab.grab(all_screens=False)  # primary monitor
    w, h = img.size
    if w > MAX_WIDTH:
        img = img.resize((MAX_WIDTH, round(h * MAX_WIDTH / w)))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=82, optimize=True)
    data = buf.getvalue()
    return {"image_b64": base64.b64encode(data).decode("ascii"), "width": img.size[0], "height": img.size[1],
            "bytes": len(data), "screen_width": w, "screen_height": h}


async def capture(delay_seconds: float = 3.0) -> dict:
    delay = max(0.0, min(float(delay_seconds), 10.0))
    if delay:
        await asyncio.sleep(delay)
    return await asyncio.to_thread(_grab_jpeg_b64)
