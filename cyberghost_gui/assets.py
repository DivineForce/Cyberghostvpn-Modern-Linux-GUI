from __future__ import annotations
from pathlib import Path
import shutil
from PIL import Image, ImageDraw
import urllib.request

def ensure_app_icon(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bundled_icon = Path(__file__).with_name("app_icon.png")
    if bundled_icon.exists():
        # Keep runtime icon in sync with the bundled asset so icon edits are visible on restart.
        shutil.copy2(bundled_icon, path)
        return
    if path.exists():
        return
    img = Image.new("RGBA", (256, 256), (11, 16, 32, 255))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((36, 36, 220, 220), radius=42, fill=(17, 24, 39, 255), outline=(37, 99, 235, 255), width=8)
    draw.ellipse((84, 88, 172, 176), fill=(229, 231, 235, 255))
    draw.ellipse((108, 116, 120, 128), fill=(11, 16, 32, 255))
    draw.ellipse((136, 116, 148, 128), fill=(11, 16, 32, 255))
    draw.arc((104, 126, 152, 154), start=10, end=170, fill=(11, 16, 32, 255), width=4)
    img.save(path)

def ensure_flag_png(flags_dir: Path, country_code: str) -> Path | None:
    code = (country_code or "").lower()
    if len(code) != 2 or not code.isalpha():
        return None
    flags_dir.mkdir(parents=True, exist_ok=True)
    target = flags_dir / f"{code}.png"
    if target.exists():
        return target
    url = f"https://flagcdn.com/w40/{code}.png"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CyberGhostModern/6.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            target.write_bytes(resp.read())
        return target
    except Exception:
        return None
