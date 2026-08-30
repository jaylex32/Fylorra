from __future__ import annotations

import os
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QSize, QByteArray
from PySide6.QtGui import QIcon, QPixmap, QPainter, QLinearGradient, QColor, QFont, QPen, QFontMetrics
from PySide6.QtWidgets import QApplication, QSplashScreen
from PySide6.QtSvg import QSvgRenderer

from core.branding import APP_NAME, APP_ORGANIZATION


def _install_crash_logger() -> None:
    def _log_exception(exc_type, exc, tb) -> None:
        try:
            base = Path.home() / ".fylorra" / "logs"
            base.mkdir(parents=True, exist_ok=True)
            log_path = base / "crash.log"
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            text = "".join(traceback.format_exception(exc_type, exc, tb))
            with log_path.open("a", encoding="utf-8") as f:
                f.write(f"\n[{stamp}] Unhandled exception\n{text}\n")
        except Exception:
            pass
        try:
            sys.__excepthook__(exc_type, exc, tb)
        except Exception:
            pass

    sys.excepthook = _log_exception


def _load_svg_renderer(svg_path: Path, *, viewbox: str | None = None) -> QSvgRenderer:
    if viewbox:
        try:
            text = svg_path.read_text(encoding="utf-8")
            text = re.sub(r'viewBox="[^"]+"', f'viewBox="{viewbox}"', text, count=1)
            renderer = QSvgRenderer()
            renderer.load(QByteArray(text.encode("utf-8")))
            if renderer.isValid():
                return renderer
        except Exception:
            pass
    return QSvgRenderer(str(svg_path))


def _build_splash_pixmap() -> QPixmap | None:
    size = QSize(760, 420)
    pm = QPixmap(size)
    if pm.isNull():
        return None
    pm.fill(Qt.transparent)

    painter = QPainter(pm)
    try:
        painter.setRenderHint(QPainter.Antialiasing, True)

        grad = QLinearGradient(0, 0, size.width(), size.height())
        grad.setColorAt(0.0, QColor("#10151d"))
        grad.setColorAt(0.58, QColor("#141a23"))
        grad.setColorAt(1.0, QColor("#1d2530"))
        painter.fillRect(pm.rect(), grad)

        painter.setPen(QPen(QColor("#253244"), 1))
        painter.drawRoundedRect(QRectF(22, 22, size.width() - 44, size.height() - 44), 18, 18)

        icon_path = Path(__file__).resolve().parents[1] / "assets" / "fylorra-icon.svg"
        brand_font = QFont("Segoe UI", 38, QFont.Bold)
        painter.setFont(brand_font)
        metrics = QFontMetrics(brand_font)
        fyl_w = metrics.horizontalAdvance("Fyl")
        orra_w = metrics.horizontalAdvance("orra")
        name_w = fyl_w + orra_w
        icon_size = 96
        icon_gap = 4
        lockup_w = icon_size + icon_gap + name_w
        lockup_x = int((size.width() - lockup_w) / 2) - 28
        icon_x = lockup_x
        text_x = lockup_x + icon_size + icon_gap

        if icon_path.exists():
            renderer = _load_svg_renderer(icon_path, viewbox="38 28 224 224")
            renderer.render(painter, QRectF(icon_x, 116, icon_size, icon_size))

        painter.setPen(QColor("#2f8cff"))
        painter.drawText(QRectF(text_x, 126, fyl_w + 8, 48), Qt.AlignLeft | Qt.AlignVCenter, "Fyl")
        painter.setPen(QColor("#dbe7f5"))
        painter.drawText(QRectF(text_x + fyl_w, 126, orra_w + 12, 48), Qt.AlignLeft | Qt.AlignVCenter, "orra")

        painter.setFont(QFont("Segoe UI", 11, QFont.DemiBold))
        painter.setPen(QColor("#9fb6d6"))
        painter.drawText(QRectF(text_x + 2, 174, 260, 22), Qt.AlignLeft | Qt.AlignVCenter, "Watch | Route | Verify")

        line_x = text_x + 2
        line_w = max(174, int(name_w + 18))
        line_grad = QLinearGradient(line_x, 202, line_x + line_w, 202)
        line_grad.setColorAt(0.0, QColor(47, 140, 255, 0))
        line_grad.setColorAt(0.32, QColor(47, 140, 255, 230))
        line_grad.setColorAt(0.72, QColor(56, 182, 255, 220))
        line_grad.setColorAt(1.0, QColor(56, 182, 255, 0))
        painter.fillRect(QRectF(line_x, 202, line_w, 3), line_grad)

        painter.setPen(QColor("#e6e9ef"))
        painter.setFont(QFont("Segoe UI", 15, QFont.DemiBold))
        painter.drawText(0, 282, size.width(), 28, Qt.AlignCenter, APP_NAME)

        painter.setPen(QColor("#aeb8c7"))
        painter.setFont(QFont("Segoe UI", 11))
        painter.drawText(0, 314, size.width(), 24, Qt.AlignCenter, "Preparing monitors and safe automation...")

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#263346"))
        painter.drawRoundedRect(QRectF(250, 354, 260, 6), 3, 3)
        progress_grad = QLinearGradient(250, 354, 510, 354)
        progress_grad.setColorAt(0.0, QColor("#2f8cff"))
        progress_grad.setColorAt(1.0, QColor("#49d3ff"))
        painter.setBrush(progress_grad)
        painter.drawRoundedRect(QRectF(250, 354, 182, 6), 3, 3)
    finally:
        painter.end()

    return pm


def run(argv: list[str]) -> int:
    _install_crash_logger()
    # High-DPI settings should be applied before QApplication is constructed.
    try:
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except Exception:
        pass

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORGANIZATION)

    # Set app icon (Windows taskbar/titlebar).
    ico = Path(__file__).resolve().parents[1] / "assets" / "fylorra.ico"
    if ico.exists():
        app.setWindowIcon(QIcon(str(ico)))

    splash = None
    try:
        pm = _build_splash_pixmap()
        if pm is not None and not pm.isNull():
            splash = QSplashScreen(pm, Qt.WindowStaysOnTopHint)
            splash.show()
            app.processEvents()
    except Exception:
        splash = None

    from core.monitor_manager import MonitorManager
    from core.settings_manager import SettingsManager
    from qt_app.backend import FylorraBackend
    from qt_app.main_window import FylorraQtMainWindow
    from qt_app.styles import apply_app_theme

    settings_manager = SettingsManager()
    theme_mode = str(settings_manager.get_setting("theme", "dark") or "dark")
    accent = str(settings_manager.get_setting("color_theme", "blue") or "blue")
    apply_app_theme(app, theme=theme_mode, accent=accent)
    monitor_manager = MonitorManager(settings_manager)
    ai_manager = None
    # Lazy AI import: keep Qt UI usable even if heavy AI deps aren't installed in this environment yet.
    try:
        from core.ai_manager import AIManager  # type: ignore

        ai_manager = AIManager(settings_manager.app_folder, settings_manager)
    except Exception:
        ai_manager = None
    backend = FylorraBackend(
        settings_manager=settings_manager,
        monitor_manager=monitor_manager,
        ai_manager=ai_manager,
    )
    backend.load()

    win = FylorraQtMainWindow(backend=backend)
    try:
        screen = app.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            target_w = min(int(avail.width() * 0.92), 1600)
            target_h = min(int(avail.height() * 0.90), 980)
            if avail.width() < 1280 or avail.height() < 760:
                win.showMaximized()
            else:
                win.resize(target_w, target_h)
                x = int(avail.x() + (avail.width() - target_w) / 2)
                y = int(avail.y() + (avail.height() - target_h) / 2)
                win.move(x, y)
                win.show()
        else:
            win.show()
    except Exception:
        win.show()
    if splash is not None:
        try:
            splash.finish(win)
        except Exception:
            pass

    code = app.exec()
    try:
        backend.shutdown()
    except Exception:
        pass
    return code
