from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "src" / "novaura" / "assets" / "novaura.ico"


def gradient(size: int, start: tuple[int, int, int], middle: tuple[int, int, int], end: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pixels = image.load()
    for x in range(size):
        p = x / max(1, size - 1)
        if p < 0.5:
            t = p * 2
            color = tuple(round(start[i] * (1 - t) + middle[i] * t) for i in range(3))
        else:
            t = (p - 0.5) * 2
            color = tuple(round(middle[i] * (1 - t) + end[i] * t) for i in range(3))
        for y in range(size):
            pixels[x, y] = (*color, 255)
    return image


def render(size: int = 512) -> Image.Image:
    scale = 4
    s = size * scale
    image = Image.new("RGBA", (s, s), (13, 9, 19, 255))
    draw = ImageDraw.Draw(image)
    pad = round(s * 0.035)
    radius = round(s * 0.25)
    draw.rounded_rectangle((pad, pad, s - pad, s - pad), radius=radius, fill="#130d1c")
    draw.rounded_rectangle((pad, pad, s - pad, s - pad), radius=radius, outline="#e84bba", width=max(3, round(s * 0.022)))
    # Geometric N emblem, inspired by the NOVAURA vector mark.
    points = [(0.24, 0.28), (0.43, 0.28), (0.63, 0.53), (0.63, 0.28),
              (0.76, 0.28), (0.76, 0.73), (0.62, 0.73), (0.42, 0.47),
              (0.42, 0.73), (0.29, 0.73), (0.29, 0.42), (0.40, 0.42),
              (0.40, 0.56), (0.24, 0.37)]
    polygon = [(round(x * s), round(y * s)) for x, y in points]
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).polygon(polygon, fill=255)
    logo_gradient = gradient(s, (255, 66, 154), (180, 71, 255), (59, 225, 218))
    image.alpha_composite(Image.composite(logo_gradient, Image.new("RGBA", (s, s), (0, 0, 0, 0)), mask))
    draw = ImageDraw.Draw(image)
    cx, cy, r = round(.79 * s), round(.22 * s), round(.065 * s)
    star = [(cx, cy-r), (cx+round(.22*r), cy-round(.22*r)), (cx+r, cy),
            (cx+round(.22*r), cy+round(.22*r)), (cx, cy+r),
            (cx-round(.22*r), cy+round(.22*r)), (cx-r, cy),
            (cx-round(.22*r), cy-round(.22*r))]
    draw.polygon(star, fill="#f4b7ff")
    draw.arc((round(.15*s), round(.67*s), round(.38*s), round(.85*s)), 205, 340, fill="#ff4ca3", width=max(3, round(.012*s)))
    image = image.resize((size, size), Image.Resampling.LANCZOS)
    return image


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    master = render(512)
    master.save(OUTPUT, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"Created {OUTPUT}")


if __name__ == "__main__":
    main()
