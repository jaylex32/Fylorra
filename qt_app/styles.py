from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPen, QPalette, QColor, QPixmap, QIcon, QImage
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle


class _SpinBoxGlyphStyle(QProxyStyle):
    """
    Qt style proxy that draws visible + / − glyphs on spinbox step buttons.
    Some platform styles render PlusMinus/arrow indicators faintly (or not at all)
    under heavy QSS; this makes them consistent.
    """

    def drawComplexControl(self, control: QStyle.ComplexControl, option, painter: QPainter, widget=None) -> None:
        super().drawComplexControl(control, option, painter, widget)
        if control != QStyle.CC_SpinBox:
            return
        try:
            up = self.subControlRect(QStyle.CC_SpinBox, option, QStyle.SC_SpinBoxUp, widget)
            down = self.subControlRect(QStyle.CC_SpinBox, option, QStyle.SC_SpinBoxDown, widget)
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing, True)
            try:
                glyph = option.palette.color(QPalette.ColorRole.ButtonText)
            except Exception:
                glyph = QColor(Qt.GlobalColor.white)
            pen = QPen(glyph)
            # Scale stroke width to DPI/geometry.
            pen.setWidth(max(2, min(up.width(), up.height(), down.width(), down.height()) // 8))
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            for rect, is_plus in ((up, True), (down, False)):
                inset = max(4, min(rect.width(), rect.height()) // 4)
                r = rect.adjusted(inset, inset, -inset, -inset)
                if r.width() <= 6 or r.height() <= 6:
                    continue
                cx = r.center().x()
                cy = r.center().y()
                half = max(4, min(r.width(), r.height()) // 3)
                painter.drawLine(cx - half, cy, cx + half, cy)
                if is_plus:
                    painter.drawLine(cx, cy - half, cx, cy + half)
        except Exception:
            pass
        finally:
            try:
                painter.restore()
            except Exception:
                pass

    def _is_light_monochrome(self, pm: QPixmap) -> bool:
        try:
            if not isinstance(pm, QPixmap) or pm.isNull():
                return False
            img = pm.toImage().convertToFormat(QImage.Format_ARGB32)
            w, h = int(img.width()), int(img.height())
            if w <= 0 or h <= 0:
                return False
            step = max(1, min(w, h) // 18)
            count = 0
            lum_sum = 0.0
            sat_sum = 0.0
            for y in range(0, h, step):
                for x in range(0, w, step):
                    c = img.pixelColor(x, y)
                    if c.alpha() < 24:
                        continue
                    count += 1
                    lum = 0.2126 * c.red() + 0.7152 * c.green() + 0.0722 * c.blue()
                    lum_sum += lum
                    sat_sum += float(c.hslSaturation())
            if count < 6:
                return False
            avg_lum = lum_sum / float(count)
            avg_sat = sat_sum / float(count)
            return avg_lum >= 178.0 and avg_sat <= 58.0
        except Exception:
            return False

    def _tint(self, pm: QPixmap, color: QColor) -> QPixmap:
        try:
            out = QPixmap(pm.size())
            out.fill(Qt.transparent)
            p = QPainter(out)
            p.drawPixmap(0, 0, pm)
            p.setCompositionMode(QPainter.CompositionMode_SourceIn)
            p.fillRect(out.rect(), color)
            p.end()
            return out
        except Exception:
            return pm

    def generatedIconPixmap(self, iconMode: QIcon.Mode, pixmap: QPixmap, opt) -> QPixmap:  # noqa: N802
        pm = super().generatedIconPixmap(iconMode, pixmap, opt)
        try:
            app = QApplication.instance()
            mode = "dark"
            if app:
                mode = str(app.property("fg_theme_mode") or "dark").strip().lower()
            if mode != "light":
                return pm
            if not self._is_light_monochrome(pm):
                return pm
            tint = QColor("#334155")
            try:
                if opt is not None:
                    tint = opt.palette.color(QPalette.ColorRole.ButtonText)
            except Exception:
                pass
            if iconMode == QIcon.Disabled:
                tint = QColor("#94a3b8")
            return self._tint(pm, tint)
        except Exception:
            return pm


_VALID_THEMES = {"dark", "light", "black"}
_VALID_ACCENTS = {"blue", "teal", "green", "orange", "rose", "violet", "cyan"}


def _normalize_theme(theme: str | None) -> str:
    value = str(theme or "dark").strip().lower()
    return value if value in _VALID_THEMES else "dark"


def _normalize_accent(accent: str | None) -> str:
    value = str(accent or "blue").strip().lower()
    return value if value in _VALID_ACCENTS else "blue"


def _accent_tokens(name: str, *, theme: str = "dark") -> dict[str, str]:
    theme = _normalize_theme(theme)
    accent = _normalize_accent(name)
    dark_table = {
        "blue": {"main": "#0d6efd", "hover": "#0b5ed7", "active_bg": "#1f3a5c", "active_fg": "#ffffff"},
        "teal": {"main": "#14b8a6", "hover": "#0d9488", "active_bg": "#1f4d48", "active_fg": "#ffffff"},
        "green": {"main": "#22c55e", "hover": "#16a34a", "active_bg": "#1f4f36", "active_fg": "#ffffff"},
        "orange": {"main": "#f59e0b", "hover": "#d97706", "active_bg": "#5c4320", "active_fg": "#ffffff"},
        "rose": {"main": "#f43f5e", "hover": "#e11d48", "active_bg": "#5d2332", "active_fg": "#ffffff"},
        "violet": {"main": "#8b5cf6", "hover": "#7c3aed", "active_bg": "#40306a", "active_fg": "#ffffff"},
        "cyan": {"main": "#06b6d4", "hover": "#0891b2", "active_bg": "#1d4f5a", "active_fg": "#ffffff"},
    }
    light_table = {
        "blue": {"main": "#0d6efd", "hover": "#0b5ed7", "active_bg": "#dbeafe", "active_fg": "#0f172a"},
        "teal": {"main": "#14b8a6", "hover": "#0d9488", "active_bg": "#ccfbf1", "active_fg": "#0f172a"},
        "green": {"main": "#22c55e", "hover": "#16a34a", "active_bg": "#dcfce7", "active_fg": "#0f172a"},
        "orange": {"main": "#f59e0b", "hover": "#d97706", "active_bg": "#ffedd5", "active_fg": "#0f172a"},
        "rose": {"main": "#f43f5e", "hover": "#e11d48", "active_bg": "#ffe4e6", "active_fg": "#0f172a"},
        "violet": {"main": "#8b5cf6", "hover": "#7c3aed", "active_bg": "#ede9fe", "active_fg": "#0f172a"},
        "cyan": {"main": "#06b6d4", "hover": "#0891b2", "active_bg": "#cffafe", "active_fg": "#0f172a"},
    }
    table = light_table if theme == "light" else dark_table
    return table.get(accent, table["blue"])


def _theme_tokens(name: str) -> dict[str, str]:
    table = {
        "dark": {
            "window": "#121417",
            "surface": "#171a1f",
            "border": "#232730",
            "text": "#e6e8ee",
            "title": "#ffffff",
            "muted": "#9aa0a9",
            "input_bg": "#1b1f26",
            "input_border": "#2a303a",
            "panel": "#14171c",
            "hover": "#232834",
            "hover_strong": "#313847",
            "badge": "#1b2433",
            "header": "#101318",
            "alt_bg": "#151a21",
            "tooltip_bg": "#171a1f",
            "tooltip_fg": "#e6e8ee",
            "tooltip_border": "#232730",
        },
        "black": {
            "window": "#000000",
            "surface": "#0a0a0a",
            "border": "#1a1a1a",
            "text": "#f2f2f2",
            "title": "#ffffff",
            "muted": "#a0a0a0",
            "input_bg": "#0e0e0e",
            "input_border": "#222222",
            "panel": "#070707",
            "hover": "#171717",
            "hover_strong": "#242424",
            "badge": "#121212",
            "header": "#0b0b0b",
            "alt_bg": "#111111",
            "tooltip_bg": "#0b0b0b",
            "tooltip_fg": "#f2f2f2",
            "tooltip_border": "#1a1a1a",
        },
        "light": {
            "window": "#f4f6fb",
            "surface": "#ffffff",
            "border": "#d8dee9",
            "text": "#1f2937",
            "title": "#0f172a",
            "muted": "#5f6b7a",
            "input_bg": "#ffffff",
            "input_border": "#c5cedb",
            "panel": "#fbfcff",
            "hover": "#e8edf6",
            "hover_strong": "#dfe6f2",
            "badge": "#edf2f9",
            "header": "#eaf0f8",
            "alt_bg": "#f7f9fd",
            "tooltip_bg": "#ffffff",
            "tooltip_fg": "#1f2937",
            "tooltip_border": "#cfd7e4",
        },
    }
    return table.get(_normalize_theme(name), table["dark"])


def _replace_colors(qss: str, mapping: dict[str, str]) -> str:
    out = str(qss or "")
    placeholders: dict[str, str] = {}
    for idx, src in enumerate(mapping.keys()):
        ph = f"__QSS_COLOR_{idx}__"
        placeholders[src] = ph
        out = re.sub(re.escape(src), ph, out, flags=re.IGNORECASE)
    for src, ph in placeholders.items():
        out = out.replace(ph, str(mapping[src]))
    return out


def apply_app_theme(app: QApplication, *, theme: str = "dark", accent: str = "blue") -> None:
    theme = _normalize_theme(theme)
    accent = _normalize_accent(accent)
    base = _theme_tokens(theme)
    acc = _accent_tokens(accent, theme=theme)

    # Ensure spinbox steppers remain visible even when platform theme renders them faintly.
    try:
        app.setStyle(_SpinBoxGlyphStyle(app.style()))
    except Exception:
        pass

    # Qt Widgets stylesheet (QSS) tuned to resemble the current Fylorra dark style,
    # while keeping a clean modern look.
    qss = """
    * {
        font-family: "Segoe UI";
        font-size: 12px;
    }

    QDialog, QMessageBox {
        background: #121417;
    }

    QMainWindow {
        background: #121417;
    }

    QFrame#HeaderBar {
        background: #171a1f;
        border-bottom: 1px solid #232730;
    }

    QFrame#Sidebar {
        background: #171a1f;
        border-right: 1px solid #232730;
    }

    QFrame#ContentShell {
        background: #121417;
    }

    /* Rounded main content area (the large dark region on each page). */
    QFrame#ContentCard {
        background: #171a1f;
        border: 1px solid #232730;
        border-radius: 16px;
    }

    /* Make stacked pages transparent so the rounded ContentCard shows through. */
    QStackedWidget {
        background: transparent;
        border: 0px;
    }

    QLabel#BrandTitle {
        font-size: 15px;
        font-weight: 700;
        color: #ffffff;
    }
    QLabel#BrandSub {
        font-size: 10px;
        color: #9aa0a9;
    }

    /* Custom nav item (QFrame-based) for precise icon/text spacing */
    QFrame#NavButton {
        background: transparent;
        border-radius: 8px;
    }
    QFrame#NavButton:hover {
        background: #232834;
    }
    QFrame#NavButton[active="true"] {
        background: #1f3a5c;
    }
    QLabel#NavText {
        color: #e6e8ee;
        font-size: 12px;
        font-weight: 500;
    }

    QToolButton#NavButton {
        text-align: left;
        padding: 10px 14px;
        border-radius: 8px;
        color: #e6e8ee;
        background: transparent;
    }
    QToolButton#NavButton:hover {
        background: #232834;
    }
    QToolButton#NavButton[active="true"] {
        background: #1f3a5c;
    }

    QFrame#TopBar {
        background: #171a1f;
        border-bottom: 1px solid #232730;
    }

    QToolButton#HamburgerButton {
        background: transparent;
        border: 1px solid transparent;
        border-radius: 8px;
        padding: 6px;
    }
    QToolButton#HamburgerButton:hover {
        background: #232834;
        border: 1px solid #232730;
    }

    QLineEdit#CommandBar {
        background: #1b1f26;
        border: 1px solid #2a303a;
        border-radius: 10px;
        padding: 10px 12px;
        color: #e6e8ee;
    }

    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QAbstractSpinBox {
        background: #1b1f26;
        border: 1px solid #2a303a;
        border-radius: 10px;
        padding: 8px 10px;
        color: #e6e8ee;
        selection-background-color: #1f3a5c;
    }
    /* Spinboxes: make the stepper controls larger + more visible (we also set Plus/Minus symbols in code). */
    QSpinBox, QDoubleSpinBox, QAbstractSpinBox {
        padding-right: 40px; /* room for stepper buttons */
    }
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
    QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
        subcontrol-origin: padding;
        width: 34px;
        border-left: 1px solid #2a303a;
        background: #232834;
    }
    QSpinBox::up-button, QDoubleSpinBox::up-button, QAbstractSpinBox::up-button {
        subcontrol-position: top right;
        border-top-right-radius: 10px;
    }
    QSpinBox::down-button, QDoubleSpinBox::down-button, QAbstractSpinBox::down-button {
        subcontrol-position: bottom right;
        border-bottom-right-radius: 10px;
    }
    QSpinBox::up-button:hover, QSpinBox::down-button:hover,
    QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover,
    QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {
        background: #313847;
    }
    QSpinBox::up-button:pressed, QSpinBox::down-button:pressed,
    QDoubleSpinBox::up-button:pressed, QDoubleSpinBox::down-button:pressed,
    QAbstractSpinBox::up-button:pressed, QAbstractSpinBox::down-button:pressed {
        background: #1f3a5c;
    }
    /* Spinbox arrow glyphs are drawn by _SpinBoxGlyphStyle for consistent visibility. */
    QComboBox::drop-down {
        border: 0px;
        width: 28px;
    }
    QComboBox QAbstractItemView {
        background: #171a1f;
        border: 1px solid #232730;
        selection-background-color: #1f3a5c;
        color: #e6e8ee;
    }

    QGroupBox {
        border: 1px solid #232730;
        border-radius: 12px;
        margin-top: 12px;
        padding: 12px;
        background: #171a1f;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
        color: #9aa0a9;
        font-weight: 600;
        background: #121417;
    }

    QLabel {
        color: #e6e8ee;
    }

    QCheckBox {
        color: #e6e8ee;
        spacing: 8px;
    }
    QCheckBox::indicator {
        width: 16px;
        height: 16px;
        border-radius: 4px;
        border: 1px solid #2a303a;
        background: #14171c;
    }
    QCheckBox::indicator:checked {
        background: #0d6efd;
        border: 1px solid #0b5ed7;
    }

    /* Modern tables / trees (used in Cloud Sync Jobs + Explorer, Search results, etc). */
    QTableView, QTableWidget, QTreeView, QListView {
        background: #14171c;
        border: 1px solid #232730;
        border-radius: 10px;
        color: #e6e8ee;
        gridline-color: #232730;
        alternate-background-color: #151a21;
        selection-background-color: #1f3a5c;
        selection-color: #ffffff;
        outline: 0;
    }
    QTableView::item, QTableWidget::item, QTreeView::item, QListView::item {
        padding: 6px 10px;
        border: 0px;
    }
    QTableView::item:selected, QTableWidget::item:selected, QTreeView::item:selected, QListView::item:selected {
        background: #1f3a5c;
    }
    QTableView::item:hover, QTableWidget::item:hover, QTreeView::item:hover, QListView::item:hover {
        background: #232834;
    }
    QHeaderView::section {
        background: #101318;
        color: #9aa0a9;
        padding: 8px 10px;
        border: 0px;
        border-right: 1px solid #232730;
    }
    QTableCornerButton::section {
        background: #101318;
        border: 0px;
    }

    QPushButton#PrimaryButton {
        background: #0d6efd;
        border: 1px solid #0b5ed7;
        border-radius: 10px;
        padding: 10px 16px;
        color: #ffffff;
        font-weight: 600;
    }
    QPushButton#PrimaryButton:hover {
        background: #0b5ed7;
    }

    QDialogButtonBox QPushButton#PrimaryButton {
        padding: 8px 14px;
        border-radius: 10px;
    }

    QFrame#PageHost {
        background: transparent;
    }

    QFrame#PageCard {
        background: #171a1f;
        border: 1px solid #232730;
        border-radius: 14px;
    }

    QFrame#ToolTile {
        background: #14171c;
        border: 1px solid #232730;
        border-radius: 14px;
    }
    QFrame#ToolTile:hover {
        border: 1px solid #1f3a5c;
        background: #171a1f;
    }

    QFrame#IconBadge {
        background: #1b2433;
        border: 1px solid #232730;
        border-radius: 22px;
    }

    /* Workspace action cards can reuse PageCard, but make them slightly tighter. */
    QFrame#PageCard QCheckBox {
        font-weight: 600;
    }

    QPushButton {
        background: #2a303a;
        border: 1px solid #232730;
        border-radius: 10px;
        padding: 8px 10px;
        color: #e6e8ee;
    }
    QPushButton:hover {
        background: #313847;
    }

    QProgressBar {
        border: 1px solid #232730;
        border-radius: 8px;
        background: #14171c;
        text-align: center;
        color: #9aa0a9;
        height: 14px;
    }
    QProgressBar::chunk {
        background: #0d6efd;
        border-radius: 8px;
    }

    QLabel#PageTitle {
        font-size: 22px;
        font-weight: 700;
        color: #ffffff;
    }
    QLabel#PageSubTitle {
        font-size: 12px;
        color: #9aa0a9;
    }

    QToolTip {
        background: #171a1f;
        color: #e6e8ee;
        border: 1px solid #232730;
        padding: 6px 8px;
        border-radius: 8px;
    }
    """
    mapping = {
        "#121417": base["window"],
        "#171a1f": base["surface"],
        "#232730": base["border"],
        "#1f3a5c": acc["active_bg"],
        "#e6e8ee": base["text"],
        "#9aa0a9": base["muted"],
        "#1b1f26": base["input_bg"],
        "#2a303a": base["input_border"],
        "#14171c": base["panel"],
        "#0d6efd": acc["main"],
        "#0b5ed7": acc["hover"],
        "#232834": base["hover"],
        "#313847": base["hover_strong"],
        "#1b2433": base["badge"],
        "#101318": base["header"],
        "#151a21": base["alt_bg"],
        "#ffffff": base["title"],
    }
    qss = _replace_colors(qss, mapping)
    qss += (
        f"\nQToolTip{{background:{base['tooltip_bg']}; color:{base['tooltip_fg']}; border:1px solid {base['tooltip_border']};}}"
        f"\nQPushButton#PrimaryButton{{color:#ffffff;}}"
        f"\nQDialogButtonBox QPushButton#PrimaryButton{{color:#ffffff;}}"
        f"\nQFrame#NavButton{{border:1px solid transparent;}}"
        f"\nQFrame#NavButton:hover{{border:1px solid {base['border']};}}"
        f"\nQFrame#NavButton[active=\"true\"]{{background:{acc['active_bg']}; border:1px solid {acc['main']};}}"
        f"\nQFrame#NavButton[active=\"true\"] QLabel#NavText{{color:{acc['active_fg']}; font-weight:700;}}"
        f"\nQToolButton#NavButton{{border:1px solid transparent;}}"
        f"\nQToolButton#NavButton:hover{{border:1px solid {base['border']};}}"
        f"\nQToolButton#NavButton[active=\"true\"]{{background:{acc['active_bg']}; color:{acc['active_fg']}; border:1px solid {acc['main']};}}"
    )

    try:
        app.setProperty("fg_theme_mode", theme)
        app.setProperty("fg_color_theme", accent)
    except Exception:
        pass

    try:
        pal = app.palette()
        pal.setColor(QPalette.Window, QColor(base["window"]))
        pal.setColor(QPalette.Base, QColor(base["input_bg"]))
        pal.setColor(QPalette.AlternateBase, QColor(base["alt_bg"]))
        pal.setColor(QPalette.WindowText, QColor(base["text"]))
        pal.setColor(QPalette.Text, QColor(base["text"]))
        pal.setColor(QPalette.Button, QColor(base["surface"]))
        pal.setColor(QPalette.ButtonText, QColor(base["text"]))
        pal.setColor(QPalette.Highlight, QColor(acc["main"]))
        pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        app.setPalette(pal)
    except Exception:
        pass

    app.setStyleSheet(qss)


def apply_dark_theme(app: QApplication) -> None:
    # Backward compatibility for older call sites.
    apply_app_theme(app, theme="dark", accent="blue")
