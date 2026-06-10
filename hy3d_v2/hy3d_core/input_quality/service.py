from __future__ import annotations

import importlib.util
from pathlib import Path
from statistics import mean


MIN_RECOMMENDED_SIZE = 256
NEAR_SQUARE_TOLERANCE = 0.12


def _empty_report(image_path: Path) -> dict:
    return {
        "image_path": str(image_path),
        "exists": image_path.exists(),
        "file_size": image_path.stat().st_size if image_path.exists() and image_path.is_file() else 0,
        "width": None,
        "height": None,
        "mode": None,
        "aspect_ratio": None,
        "has_alpha": False,
        "is_too_small": False,
        "is_square_or_near_square": False,
        "contrast_score": None,
        "estimated_background_complexity": None,
        "input_quality_status": "error",
        "warnings": [],
    }


def _contrast_score(gray_image) -> float:
    from PIL import ImageStat

    stat = ImageStat.Stat(gray_image)
    return round(float(stat.stddev[0]) / 255.0, 4)


def _estimated_background_complexity(gray_image) -> str:
    try:
        import numpy as np
    except Exception:
        return "unknown"

    arr = np.asarray(gray_image.resize((64, 64)))
    if arr.size == 0:
        return "unknown"
    top = arr[:8, :]
    bottom = arr[-8:, :]
    left = arr[:, :8]
    right = arr[:, -8:]
    border_std = mean(float(part.std()) for part in (top, bottom, left, right)) / 255.0
    if border_std >= 0.18:
        return "high"
    if border_std >= 0.08:
        return "medium"
    return "low"


def analyze_input_image(image_path: Path) -> dict:
    image_path = Path(image_path)
    report = _empty_report(image_path)
    if not image_path.exists() or not image_path.is_file():
        report["warnings"].append("input_image_missing")
        return report
    if importlib.util.find_spec("PIL") is None:
        report["warnings"].append("pillow_unavailable")
        report["input_quality_status"] = "warning"
        return report

    try:
        from PIL import Image

        with Image.open(image_path) as image:
            width, height = image.size
            mode = image.mode
            gray = image.convert("L")
            contrast = _contrast_score(gray)
            background_complexity = _estimated_background_complexity(gray)
    except Exception as exc:
        report["warnings"].append(f"input_image_invalid: {exc}")
        return report

    shortest_side = min(width, height)
    aspect_ratio = round(width / height, 4) if height else None
    near_square = aspect_ratio is not None and abs(aspect_ratio - 1.0) <= NEAR_SQUARE_TOLERANCE
    warnings: list[str] = []
    if shortest_side < MIN_RECOMMENDED_SIZE:
        warnings.append("image_too_small_for_best_quality")
    if not near_square:
        warnings.append("image_not_square_or_near_square")
    if contrast < 0.12:
        warnings.append("low_contrast")
    if background_complexity == "high":
        warnings.append("complex_background")

    status = "ok"
    if warnings:
        status = "warning"

    report.update(
        {
            "width": width,
            "height": height,
            "mode": mode,
            "aspect_ratio": aspect_ratio,
            "has_alpha": mode in {"LA", "RGBA"} or "transparency" in mode.lower(),
            "is_too_small": shortest_side < MIN_RECOMMENDED_SIZE,
            "is_square_or_near_square": near_square,
            "contrast_score": contrast,
            "estimated_background_complexity": background_complexity,
            "input_quality_status": status,
            "warnings": warnings,
        }
    )
    return report
