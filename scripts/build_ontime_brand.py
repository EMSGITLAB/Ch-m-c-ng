"""Render the approved OnTime concept 02 as local SVG and launcher assets.

Development only: Pillow is used for raster exports, never in the web runtime.
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "frontend/public/brand"
BLUE = "#2563eb"
NAVY = "#0f172a"
WHITE = "#ffffff"
CORNERS = "M45 18H28Q18 18 18 28V45 M83 18H100Q110 18 110 28V45 M110 83V100Q110 110 100 110H83 M45 110H28Q18 110 18 100V83"


def shapes(check):
    return (f'<path d="{CORNERS}" fill="none" stroke="{BLUE}" stroke-width="12" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
            f'<path d="M42 64L58 80L88 50" fill="none" stroke="{check}" stroke-width="14" '
            'stroke-linecap="round" stroke-linejoin="round"/>')


def svg(body, width=128, height=128, title="OnTime"):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title">'
            f'<title id="title">{title}</title>{body}</svg>\n')


def raster(size, *, background=None, check=NAVY):
    scale = size * 4 / 128
    image = Image.new("RGBA", (size * 4, size * 4), background or (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def stroke(points, color, width):
        points = [(round(x * scale), round(y * scale)) for x, y in points]
        thickness = round(width * scale)
        draw.line(points, fill=color, width=thickness, joint="curve")
        radius = thickness / 2
        for x, y in (points[0], points[-1]):
            draw.ellipse((round(x-radius), round(y-radius), round(x+radius), round(y+radius)), fill=color)

    # One corner, including the same quadratic curve as the SVG. Rotate it
    # around the center for four consistent corner brackets.
    corner = [(45, 18), (28, 18)]
    for index in range(1, 25):
        t = index / 24
        corner.append(((1-t)**2*28 + 2*(1-t)*t*18 + t*t*18,
                       (1-t)**2*18 + 2*(1-t)*t*18 + t*t*28))
    corner.append((18, 45))
    for _ in range(4):
        stroke(corner, BLUE, 12)
        corner = [(128-y, x) for x, y in corner]
    stroke([(42, 64), (58, 80), (88, 50)], check, 14)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "ontime-mark.svg").write_text(svg(shapes(NAVY)), encoding="utf-8")
    (OUTPUT / "ontime-mark-dark.svg").write_text(svg(shapes(WHITE)), encoding="utf-8")
    (OUTPUT / "ontime-favicon.svg").write_text(svg(
        f'<rect width="128" height="128" rx="26" fill="{NAVY}"/>'+shapes(WHITE)), encoding="utf-8")
    for variant, color in (("light", NAVY), ("dark", WHITE)):
        body = ('<g transform="translate(0 2) scale(.75)">'+shapes(color)+'</g>'
                f'<text x="108" y="67" fill="{color}" font-family="Segoe UI,Arial,sans-serif" '
                'font-size="56" font-weight="800" letter-spacing="-2">OnTime</text>')
        (OUTPUT / f"ontime-logo-{variant}.svg").write_text(svg(body, 380, 100), encoding="utf-8")
    for size in (32, 192, 512):
        raster(size, background=NAVY, check=WHITE).save(OUTPUT / f"ontime-icon-{size}.png")
    raster(180, background=NAVY, check=WHITE).save(OUTPUT / "ontime-apple-touch-icon.png")
    raster(512).save(OUTPUT / "ontime-mark-512.png")
    manifest = {"id": "/", "name": "OnTime — Chấm công khuôn mặt", "short_name": "OnTime",
                "description": "Chấm công khuôn mặt trên máy chủ nội bộ", "lang": "vi",
                "start_url": "/#kiosk", "scope": "/", "display": "standalone",
                "background_color": NAVY, "theme_color": NAVY,
                "icons": [{"src": f"/brand/ontime-icon-{size}.png", "sizes": f"{size}x{size}",
                           "type": "image/png", "purpose": "any"} for size in (192, 512)]}
    (OUTPUT.parent / "manifest.webmanifest").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"brand": "OnTime", "approved_concept": 2, "assets": 10, "local_only": True}))


if __name__ == "__main__":
    main()
