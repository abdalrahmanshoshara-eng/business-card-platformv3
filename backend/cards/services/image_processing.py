from __future__ import annotations

import logging
import time
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

logger = logging.getLogger(__name__)

MAX_LONG_EDGE = 1600
JPEG_QUALITY = 85


def _pil_fallback(input_path: Path, output_path: Path) -> dict:
    img = Image.open(input_path)
    img = ImageOps.exif_transpose(img).convert('RGB')
    original_size = img.size
    longest = max(img.size)
    if longest > MAX_LONG_EDGE:
        scale = MAX_LONG_EDGE / longest
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)
    img = ImageOps.autocontrast(img, cutoff=1)
    img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=45, threshold=4))
    img.save(output_path, format='JPEG', quality=JPEG_QUALITY, optimize=True)
    return {
        'original_size': original_size,
        'final_size': img.size,
        'card_detected': False,
        'perspective_corrected': False,
        'dark_card': False,
        'output_bytes': output_path.stat().st_size,
    }


def _order_points(points):
    import numpy as np

    rect = np.zeros((4, 2), dtype='float32')
    s = points.sum(axis=1)
    rect[0] = points[np.argmin(s)]
    rect[2] = points[np.argmax(s)]
    diff = np.diff(points, axis=1)
    rect[1] = points[np.argmin(diff)]
    rect[3] = points[np.argmax(diff)]
    return rect


def _detect_card_quad(image):
    import cv2
    import numpy as np

    height, width = image.shape[:2]
    scale = min(1.0, 1200 / max(width, height))
    resized = cv2.resize(image, (int(width * scale), int(height * scale))) if scale < 1 else image.copy()
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 45, 140)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    min_area = resized.shape[0] * resized.shape[1] * 0.08
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:10]:
        area = cv2.contourArea(contour)
        if area < min_area:
            continue
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.025 * perimeter, True)
        if len(approx) == 4:
            points = approx.reshape(4, 2).astype('float32') / scale
            return _order_points(points), True

    candidates = [c for c in contours if cv2.contourArea(c) >= min_area]
    if not candidates:
        return None, False
    rect = cv2.minAreaRect(max(candidates, key=cv2.contourArea))
    points = cv2.boxPoints(rect).astype('float32') / scale
    return _order_points(points), False


def _warp_card(image, quad):
    import cv2
    import numpy as np

    rect = _order_points(quad)
    tl, tr, br, bl = rect
    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_width = max(int(width_a), int(width_b))
    max_height = max(int(height_a), int(height_b))
    if max_width < 250 or max_height < 150:
        return image
    destination = np.array(
        [[0, 0], [max_width - 1, 0], [max_width - 1, max_height - 1], [0, max_height - 1]],
        dtype='float32',
    )
    matrix = cv2.getPerspectiveTransform(rect, destination)
    return cv2.warpPerspective(image, matrix, (max_width, max_height))


def _enhance(image):
    import cv2

    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    lightness, a, b = cv2.split(lab)
    dark_card = lightness.mean() < 105
    if dark_card:
        clahe = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(8, 8))
        lightness = clahe.apply(lightness)
    else:
        lightness = cv2.normalize(lightness, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX)
    enhanced = cv2.merge((lightness, a, b))
    enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
    return enhanced, dark_card


def preprocess_image(input_path: str | Path) -> Path:
    input_path = Path(input_path)
    output_path = input_path.with_name(input_path.stem + '_processed.jpg')
    started = time.perf_counter()

    try:
        import cv2
        import numpy as np

        with Image.open(input_path) as pil_img:
            pil_img = ImageOps.exif_transpose(pil_img).convert('RGB')
            original_size = pil_img.size
            image = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        quad, strict_quad = _detect_card_quad(image)
        card_detected = quad is not None
        perspective_corrected = False
        if quad is not None:
            warped = _warp_card(image, quad)
            if warped.size:
                image = warped
                perspective_corrected = strict_quad

        image, dark_card = _enhance(image)
        height, width = image.shape[:2]
        longest = max(width, height)
        if longest > MAX_LONG_EDGE:
            scale = MAX_LONG_EDGE / longest
            image = cv2.resize(image, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)

        final_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(final_rgb)
        img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=35, threshold=5))
        img.save(output_path, format='JPEG', quality=JPEG_QUALITY, optimize=True)
        metadata = {
            'original_size': original_size,
            'final_size': img.size,
            'card_detected': card_detected,
            'perspective_corrected': perspective_corrected,
            'dark_card': dark_card,
            'output_bytes': output_path.stat().st_size,
        }
    except Exception:
        logger.exception('image_preprocessing_cv_failed path=%s', input_path)
        metadata = _pil_fallback(input_path, output_path)

    logger.info(
        'image_preprocessed path=%s output=%s elapsed_ms=%d original=%s final=%s bytes=%s card_detected=%s warped=%s dark=%s',
        input_path,
        output_path,
        int((time.perf_counter() - started) * 1000),
        metadata['original_size'],
        metadata['final_size'],
        metadata['output_bytes'],
        metadata['card_detected'],
        metadata['perspective_corrected'],
        metadata['dark_card'],
    )
    return output_path
