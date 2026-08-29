"""Dependency-free SVG shield generation compatible with Abacus options."""

import math
import re
import unicodedata
from dataclasses import dataclass
from xml.sax.saxutils import escape


DEFAULT_BACKGROUND = "007ec6"
DEFAULT_TEXT_COLOR = "fff"
DEFAULT_FONT_SIZE = 11.0

_COLOR_PATTERN = re.compile(r"^(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")
_REGULAR_STYLES = {"flat", "flat-square", "plastic"}
_SIMPLE_STYLES = {"flat-simple", "flat-square-simple", "plastic-simple"}
_FONT_FAMILIES = {
    "verdana": "Verdana,DejaVu Sans,sans-serif",
    "verdana-bold": "Verdana Bold,DejaVu Sans,sans-serif",
    "verdana-bold-italic": "Verdana Bold Italic,DejaVu Sans,sans-serif",
    "arial": "Arial,Helvetica,sans-serif",
    "arial-bold": "Arial Bold,Helvetica,sans-serif",
    "arial-italic": "Arial Italic,Helvetica,sans-serif",
    "arial-bold-italic": "Arial Bold Italic,Helvetica,sans-serif",
    "courier-new": "Courier New,Courier,monospace",
    "jetbrains-mono": "JetBrains Mono,Courier New,monospace",
}


@dataclass(frozen=True)
class BadgeOptions:
    bgcolor: str = DEFAULT_BACKGROUND
    textcolor: str = DEFAULT_TEXT_COLOR
    text: str = "counter"
    style: str = "flat"
    fontsize: str = "11"
    font: str = "verdana"


def _validate_color(value: str) -> str:
    color = value.strip().removeprefix("#")
    if not _COLOR_PATTERN.fullmatch(color):
        raise ValueError(
            f"'{color}' is not a valid hex color (should be like 'fff' or 'ff5500')"
        )
    return f"#{color}"


def _parse_font_size(value: str) -> float:
    try:
        size = float(value)
    except ValueError:
        return DEFAULT_FONT_SIZE
    if not math.isfinite(size) or size <= 3:
        return DEFAULT_FONT_SIZE
    return size


def _normalize_style(value: str) -> str:
    style = value.lower()
    if style in _REGULAR_STYLES or style in _SIMPLE_STYLES:
        return style
    return "flat-simple" if style.endswith("-simple") else "flat"


def _text_width(value: str, font_size: float) -> float:
    """Estimate text width without requiring server-side font files."""
    units = sum(
        2 if unicodedata.east_asian_width(character) in {"W", "F"} else 1
        for character in value
    )
    return units * font_size * 0.62


def _fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def generate_badge(value: int, options: BadgeOptions = BadgeOptions()) -> str:
    """Return an SVG badge using the same public options and styles as Abacus."""
    background = _validate_color(options.bgcolor)
    text_color = _validate_color(options.textcolor)
    font_size = _parse_font_size(options.fontsize)
    style = _normalize_style(options.style)
    simple = style in _SIMPLE_STYLES
    font_family = _FONT_FAMILIES.get(options.font.lower(), _FONT_FAMILIES["verdana"])

    label = escape(options.text)
    count = str(value)
    padding_horizontal = font_size * 0.75
    padding_vertical = font_size * 0.45
    height = math.ceil((font_size * 1.2) + (padding_vertical * 2))
    right_width = math.ceil(_text_width(count, font_size) + (padding_horizontal * 2))
    left_width = 0 if simple else math.ceil(
        _text_width(options.text, font_size) + (padding_horizontal * 2)
    )
    total_width = left_width + right_width
    center_y = _fmt((height + font_size) / 2 - 1)
    shadow_y = _fmt(float(center_y) + 1)
    right_x = _fmt(left_width + right_width / 2)
    left_x = _fmt(left_width / 2)
    radius = _fmt(min(5, max(2, height * 0.15)))
    aria_label = escape(
        count if simple else f"{options.text}: {count}",
        {'"': "&quot;", "'": "&apos;"},
    )

    gradient = ""
    overlay = ""
    if style in {"flat", "flat-simple"}:
        gradient = (
            '<linearGradient id="smooth" x2="0" y2="100%">'
            '<stop offset="0" stop-color="#bbb" stop-opacity=".1"/>'
            '<stop offset="1" stop-opacity=".1"/>'
            "</linearGradient>"
        )
        overlay = f'<rect width="{total_width}" height="{height}" fill="url(#smooth)"/>'
    elif style in {"plastic", "plastic-simple"}:
        gradient = (
            '<linearGradient id="gradient" x2="0" y2="100%">'
            '<stop offset="0" stop-color="#fff" stop-opacity=".7"/>'
            '<stop offset="1" stop-opacity=".1"/>'
            "</linearGradient>"
        )
        overlay = f'<rect width="{total_width}" height="{height}" fill="url(#gradient)"/>'

    square = style in {"flat-square", "flat-square-simple"}
    mask = "" if square else (
        f'<mask id="round"><rect width="{total_width}" height="{height}" '
        f'rx="{radius}" fill="#fff"/></mask>'
    )
    group_mask = "" if square else ' mask="url(#round)"'

    if simple:
        backgrounds = (
            f'<rect width="{right_width}" height="{height}" fill="{background}"/>'
            f"{overlay}"
        )
        text_nodes = _text_nodes(count, right_x, center_y, shadow_y, style)
    else:
        backgrounds = (
            f'<rect width="{left_width}" height="{height}" fill="#555"/>'
            f'<rect x="{left_width}" width="{right_width}" height="{height}" '
            f'fill="{background}"/>{overlay}'
        )
        text_nodes = (
            _text_nodes(label, left_x, center_y, shadow_y, style)
            + _text_nodes(count, right_x, center_y, shadow_y, style)
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" '
        f'height="{height}" role="img" aria-label="{aria_label}">'
        f"<title>{aria_label}</title>{gradient}{mask}"
        f"<g{group_mask}>{backgrounds}</g>"
        f'<g fill="{text_color}" text-anchor="middle" font-family="{font_family}" '
        f'font-size="{_fmt(font_size)}">{text_nodes}</g></svg>'
    )


def _text_nodes(text: str, x: str, y: str, shadow_y: str, style: str) -> str:
    if style in {"flat-square", "flat-square-simple"}:
        return f'<text x="{x}" y="{y}">{text}</text>'
    return (
        f'<text aria-hidden="true" x="{x}" y="{shadow_y}" fill="#010101" '
        f'fill-opacity=".3">{text}</text><text x="{x}" y="{y}">{text}</text>'
    )
