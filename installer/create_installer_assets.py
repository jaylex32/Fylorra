from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "installer_sidebar.bmp"
ICON = ROOT / "assets" / "fylorra.ico"


def _font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            if Path(path).exists():
                return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def main() -> int:
    canvas = Image.new("RGB", (164, 314), "#101720")
    draw = ImageDraw.Draw(canvas)

    for y in range(canvas.height):
        shade = int(18 + (y / max(1, canvas.height - 1)) * 18)
        draw.line([(0, y), (canvas.width, y)], fill=(shade, shade + 8, shade + 18))

    draw.rectangle([0, 0, canvas.width - 1, canvas.height - 1], outline="#243247")
    draw.rectangle([0, canvas.height - 72, canvas.width, canvas.height], fill="#0d1118")

    if ICON.exists():
        icon = Image.open(ICON)
        try:
            icon.seek(icon.n_frames - 1)
        except Exception:
            pass
        icon = icon.convert("RGBA").resize((64, 64), Image.LANCZOS)
        canvas.paste(icon, (50, 42), icon)

    title_font = _font(22, bold=True)
    sub_font = _font(11)
    small_font = _font(10)

    draw.text((24, 126), "Fylorra", fill="#f8fbff", font=title_font)
    draw.text((24, 156), "Watch | Route | Verify", fill="#b9d7ff", font=sub_font)
    draw.line([(24, 178), (140, 178)], fill="#1784ff", width=2)

    draw.text((18, 236), "File intake automation", fill="#d5e4f7", font=small_font)
    draw.text((18, 252), "for home and office", fill="#8ea6c5", font=small_font)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUT, "BMP")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
