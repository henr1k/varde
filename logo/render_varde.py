"""Draws the Varde cairn and renders every logo and icon file from it.

Dev-only. Needs `resvg-py` and `pillow` (not app dependencies):
    python -m venv /tmp/v && /tmp/v/bin/pip install resvg-py pillow
    /tmp/v/bin/python logo/render_varde.py
"""

from io import BytesIO
from pathlib import Path

import resvg_py
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
LOGO = ROOT / "logo"
PUBLIC = ROOT / "frontend" / "public"

PLUM = "#8e3f9e"
PLUM_DARK_SURFACE = "#2e1234"
PLUM_LIGHT = "#f5e8f6"
PLUM_DARK_FG = "#d17fc4"
CAP_LIGHT = "#f0c6e8"

# Four stacked stones on a 500 x 500 grid: (cx, cy, rx, ry, rotation in degrees).
STONES = [
    (250, 384, 152, 46, 0),
    (244, 293, 114, 38, -4),
    (256, 218, 80, 31, 5),
    (247, 158, 47, 23, -7),
]


def _stones(body: str, cap: str) -> str:
    shapes = []
    for i, (cx, cy, rx, ry, rot) in enumerate(STONES):
        fill = cap if i == len(STONES) - 1 else body
        shapes.append(
            f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{fill}" transform="rotate({rot} {cx} {cy})"/>'
        )
    return "".join(shapes)


def mark(tile: str, body: str, cap: str, *, radius: int = 112, inset: float = 1.0) -> str:
    """A square icon: rounded tile with the cairn. `inset` < 1 shrinks the cairn (maskable safe zone)."""
    offset = 250 * (1 - inset)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500">'
        f'<rect width="500" height="500" rx="{radius}" fill="{tile}"/>'
        f'<g transform="translate({offset} {offset + 6 * inset}) scale({inset})">{_stones(body, cap)}</g>'
        "</svg>"
    )


def full_logo(tile: str, body: str, cap: str, text: str) -> str:
    """Mark plus the "Varde" wordmark, 1200 x 500."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 500">'
        f'<g transform="translate(40 60) scale(0.76)">'
        f'<rect width="500" height="500" rx="112" fill="{tile}"/>{_stones(body, cap)}</g>'
        f'<text x="460" y="318" font-family="Inter, Helvetica Neue, Arial, sans-serif" font-size="200" '
        f'font-weight="500" letter-spacing="-4" fill="{text}">Varde</text>'
        "</svg>"
    )


def _png(svg: str, size: int, width: int | None = None) -> bytes:
    return bytes(resvg_py.svg_to_bytes(svg_string=svg, width=width or size, height=size))


def main() -> None:
    light = mark(PLUM, PLUM_LIGHT, CAP_LIGHT)
    dark = mark(PLUM_DARK_SURFACE, PLUM_DARK_FG, PLUM_LIGHT)
    files = {
        PUBLIC / "logo_light.svg": light,
        PUBLIC / "logo_dark.svg": dark,
        LOGO / "brand_logo_light_theme.svg": light,
        LOGO / "brand_logo_dark_theme.svg": dark,
        LOGO / "brand_full_logo_light_theme.svg": full_logo(PLUM, PLUM_LIGHT, CAP_LIGHT, "#18181b"),
        LOGO / "brand_full_logo_dark_theme.svg": full_logo(PLUM_DARK_SURFACE, PLUM_DARK_FG, PLUM_LIGHT, "#f4f4f5"),
    }
    for path, svg in files.items():
        path.write_text(svg + "\n")
        png = path.with_suffix(".png")
        if png.exists() or path.parent == LOGO:
            png.write_bytes(_png(svg, 500, 1200 if "full" in path.name else None))

    square = mark(PLUM, PLUM_LIGHT, CAP_LIGHT, radius=0)
    (PUBLIC / "apple-touch-icon.png").write_bytes(_png(square, 180))
    (PUBLIC / "android-chrome-192x192.png").write_bytes(_png(mark(PLUM, PLUM_LIGHT, CAP_LIGHT, radius=0, inset=0.8), 192))
    (PUBLIC / "android-chrome-512x512.png").write_bytes(_png(mark(PLUM, PLUM_LIGHT, CAP_LIGHT, radius=0, inset=0.8), 512))
    (PUBLIC / "favicon-32x32.png").write_bytes(_png(light, 32))
    (PUBLIC / "favicon-16x16.png").write_bytes(_png(light, 16))
    icon = Image.open(BytesIO(_png(light, 64)))
    icon.save(PUBLIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    print("rendered", len(files), "SVGs and their PNGs, favicons and app icons")


if __name__ == "__main__":
    main()
