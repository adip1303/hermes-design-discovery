"""WCAG 2.2 relative-luminance contrast calculations."""

from __future__ import annotations


def _linear(channel: int) -> float:
    value = channel / 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    value = hex_color.lstrip("#")
    red, green, blue = (int(value[index:index + 2], 16) for index in (0, 2, 4))
    return 0.2126 * _linear(red) + 0.7152 * _linear(green) + 0.0722 * _linear(blue)


def contrast_ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted((relative_luminance(foreground), relative_luminance(background)), reverse=True)
    return round((lighter + 0.05) / (darker + 0.05), 2)


PAIR_REQUIREMENTS = {
    "text_on_background": ("Text is hard to read on the background", 7),
    "text_on_surface": ("Text is hard to read on cards", 7),
    "muted_on_background": ("Muted text is hard to read on the background", 4.5),
    "muted_on_surface": ("Muted text is hard to read on cards", 4.5),
    "accent_text_on_accent": ("Button text is hard to read", 4.5),
    "border_strong_on_background": ("Strong borders are hard to see", 3),
    "success_on_background": ("Success text is hard to read on the background", 4.5),
    "success_on_surface": ("Success text is hard to read on cards", 4.5),
    "warning_on_background": ("Warning text is hard to read on the background", 4.5),
    "warning_on_surface": ("Warning text is hard to read on cards", 4.5),
    "danger_on_background": ("Danger text is hard to read on the background", 4.5),
    "danger_on_surface": ("Danger text is hard to read on cards", 4.5),
}


def report(tokens: dict) -> dict:
    color = tokens["color"]
    accent_usage = tokens.get("accent_usage", color.get("accent_usage", "text_and_fill"))
    pairs = {"text_on_background": (color["text"], color["background"]), "text_on_surface": (color["text"], color["surface"]), "muted_on_background": (color["muted"], color["background"]), "muted_on_surface": (color["muted"], color["surface"]), "accent_text_on_accent": (color["accent_text"], color["accent"]), "accent_on_background": (color["accent"], color["background"]), "border_strong_on_background": (color["border_strong"], color["background"]), **{f"{status}_on_{ground}": (color[status], color[ground]) for status in ("success", "warning", "danger") for ground in ("background", "surface")}}
    pairs.update({f"accent_text_on_alternate_{index}": (color["accent_text"], alternate) for index, alternate in enumerate(color["accent_alternates"], 1)})
    result = {}
    for name, colors in pairs.items():
        ratio = contrast_ratio(*colors)
        label, minimum = PAIR_REQUIREMENTS.get(name, ("Accent is hard to see on the background", 3 if accent_usage == "fill_only" else 4.5))
        result[name] = {"ratio": ratio, "aa_normal": ratio >= 4.5, "aaa_normal": ratio >= 7, "aa_large": ratio >= 3, "aaa_large": ratio >= 4.5, "minimum": minimum, "passes": ratio >= minimum, "label": label}
    return result
