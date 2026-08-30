from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QIcon, QPixmap, QImage, QPainter


@dataclass(frozen=True)
class IconPaths:
    root: Path

    @property
    def icons_dir(self) -> Path:
        return self.root / "assets" / "icons"


class QtIconLoader:
    def __init__(self, root: Path | None = None):
        self._root = root or Path(__file__).resolve().parents[1]
        self._paths = IconPaths(self._root)

    def _resolve_icon_path(self, name: str) -> Path | None:
        base = self._paths.icons_dir / name
        candidates: list[Path] = []
        if base.suffix:
            candidates.append(base)
        else:
            candidates.extend([base.with_suffix(".png"), base.with_suffix(".svg")])
        for p in candidates:
            if p.exists():
                return p
        return None

    @lru_cache(maxsize=256)
    def icon(self, name: str) -> QIcon:
        # Prefer png, then svg.
        p = self._resolve_icon_path(name)
        if p:
            return QIcon(str(p))
        return QIcon()

    def _normalized_png_pixmap(self, path: Path, size: int) -> QPixmap:
        img = QImage(str(path))
        if img.isNull():
            return QPixmap()

        if img.format() != QImage.Format_ARGB32:
            img = img.convertToFormat(QImage.Format_ARGB32)

        w = img.width()
        h = img.height()
        if w <= 0 or h <= 0:
            return QPixmap()

        min_x, min_y = w, h
        max_x, max_y = -1, -1
        threshold = 10  # alpha threshold (0..255)
        for y in range(h):
            scan = img.scanLine(y)
            # QImage scanLine returns a sip.voidptr; use pixelColor to keep it simple (icons are small).
            for x in range(w):
                if img.pixelColor(x, y).alpha() > threshold:
                    if x < min_x:
                        min_x = x
                    if y < min_y:
                        min_y = y
                    if x > max_x:
                        max_x = x
                    if y > max_y:
                        max_y = y

        if max_x < 0 or max_y < 0:
            # Fully transparent; fall back
            pm = QPixmap.fromImage(img)
            return pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        rect = QRect(min_x, min_y, (max_x - min_x + 1), (max_y - min_y + 1))
        cropped = img.copy(rect)
        scaled = cropped.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        out = QImage(size, size, QImage.Format_ARGB32)
        out.fill(Qt.transparent)
        p = QPainter(out)
        try:
            x0 = (size - scaled.width()) // 2
            y0 = (size - scaled.height()) // 2
            p.drawImage(x0, y0, scaled)
        finally:
            p.end()
        return QPixmap.fromImage(out)

    @lru_cache(maxsize=256)
    def pixmap(self, name: str, size: int) -> QPixmap:
        p = self._resolve_icon_path(name)
        if not p:
            return QPixmap()
        if p.suffix.lower() == ".png":
            # Normalize padding so icons appear the same visual weight (fixes e.g. small-looking glyphs).
            return self._normalized_png_pixmap(p, int(size))
        ic = QIcon(str(p))
        return ic.pixmap(int(size), int(size))
