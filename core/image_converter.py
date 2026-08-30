"""
Fylorra - Image Conversion (built-in)
Folder-based image conversion using Pillow (no external apps required).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImageConvertResult:
    ok: bool
    message: str
    converted: int = 0
    skipped: int = 0
    output_dir: str | None = None


def _require_pillow():
    try:
        from PIL import Image  # noqa: F401

        return Image
    except Exception as e:
        raise RuntimeError("Image conversion requires 'Pillow'. Install: pip install pillow") from e


def convert_images_in_folder(
    folder: Path,
    *,
    include_subfolders: bool = True,
    input_exts: set[str] | None = None,
    output_format: str = "png",
    output_mode: str = "subfolder",
    output_subfolder: str = "Converted_Images",
    overwrite: bool = False,
    progress_cb=None,
    cancel_event=None,
) -> ImageConvertResult:
    Image = _require_pillow()
    try:
        from PIL import ImageOps  # type: ignore
    except Exception:
        ImageOps = None

    folder = Path(folder)
    if not folder.exists():
        return ImageConvertResult(ok=False, message="Folder not found.")

    output_format = (output_format or "png").strip().lower().lstrip(".")
    if output_format not in {"png", "jpg", "jpeg", "webp", "bmp", "tiff"}:
        return ImageConvertResult(ok=False, message="Unsupported output format.")

    if input_exts is None:
        input_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
    input_exts = {("." + e.strip().lower().lstrip(".")) for e in input_exts}

    out_dir = folder / output_subfolder if output_mode == "subfolder" else folder
    out_dir.mkdir(parents=True, exist_ok=True)

    pattern = "**/*" if include_subfolders else "*"
    out_dir_resolved = None
    try:
        out_dir_resolved = out_dir.resolve()
    except Exception:
        out_dir_resolved = None

    # Snapshot inputs up-front to avoid infinite loops when output is inside the scanned tree.
    input_files: list[Path] = []
    for p in folder.glob(pattern):
        if not p.is_file():
            continue
        if p.suffix.lower() not in input_exts:
            continue
        if out_dir_resolved is not None:
            try:
                rp = p.resolve()
                if rp == out_dir_resolved or rp.is_relative_to(out_dir_resolved):
                    continue
            except Exception:
                pass
        input_files.append(p)

    converted = 0
    skipped = 0
    total = max(1, len(input_files))
    for idx, p in enumerate(input_files, start=1):
        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
            return ImageConvertResult(ok=False, message="Cancelled.", converted=converted, skipped=skipped, output_dir=str(out_dir))
        if progress_cb:
            try:
                progress_cb(idx, total, p)
            except Exception:
                pass
        rel = p.relative_to(folder)
        dest_dir = (out_dir / rel.parent) if include_subfolders else out_dir
        dest_dir.mkdir(parents=True, exist_ok=True)

        out_ext = ".jpg" if output_format == "jpeg" else f".{output_format}"
        out_path = dest_dir / (p.stem + out_ext)
        if out_path.exists() and not overwrite:
            skipped += 1
            continue

        try:
            with Image.open(p) as im:
                if ImageOps is not None:
                    try:
                        im = ImageOps.exif_transpose(im)
                    except Exception:
                        pass
                if output_format in {"jpg", "jpeg"}:
                    if im.mode in {"RGBA", "LA"}:
                        im = im.convert("RGB")
                    im.save(out_path, format="JPEG", quality=92, optimize=True)
                elif output_format == "webp":
                    im.save(out_path, format="WEBP", quality=92, method=6)
                else:
                    im.save(out_path, format=output_format.upper())
            converted += 1
        except Exception:
            skipped += 1

    return ImageConvertResult(
        ok=True,
        message=f"Converted {converted} images (skipped {skipped}).",
        converted=converted,
        skipped=skipped,
        output_dir=str(out_dir),
    )
