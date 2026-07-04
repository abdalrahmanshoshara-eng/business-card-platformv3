from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageOps, ImageFilter


def preprocess_image(input_path: str | Path) -> Path:
    input_path = Path(input_path)
    output_path = input_path.with_name(input_path.stem + '_processed' + input_path.suffix)
    img = Image.open(input_path)
    img = ImageOps.exif_transpose(img).convert('RGB')
    w, h = img.size
    longest = max(w, h)
    if longest < 1600:
        scale = 1600 / longest
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    img = ImageOps.autocontrast(img)
    img = img.filter(ImageFilter.SHARPEN)
    img.save(output_path, quality=95)
    return output_path
