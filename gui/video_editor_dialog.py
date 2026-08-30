"""
Fylorra - Video Editor Dialog
Advanced single-file video edit/export UI (ffmpeg-based).
Layout inspired by Fylorra mockups (media bin + preview + timeline + render bar).
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
import re
import time
import random
import logging
import sys
import faulthandler

from PySide6.QtCore import Qt, QTimer, QPoint, QSize, QRect, QObject, Signal, QEvent, QSignalBlocker, QThread, qInstallMessageHandler, QUrl, QMimeData
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QBrush, QFont, QIcon, QDrag
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGridLayout,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QLabel,
    QPushButton,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QSlider,
    QProgressBar,
    QScrollArea,
    QWidget,
    QFileDialog,
    QMessageBox,
    QSplitter,
    QButtonGroup,
    QSizePolicy,
    QSpacerItem,
    QStackedWidget,
    QToolTip,
    QGraphicsBlurEffect,
    QMenu,
)

try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PySide6.QtMultimediaWidgets import QVideoWidget
except Exception:
    QMediaPlayer = None
    QAudioOutput = None
    QVideoWidget = None

from core.ffmpeg_manager import get_ffmpeg_exe, get_ffplay_exe, get_ffprobe_exe
from core.media_edit import MediaEditRequest, TimelineClip, edit_media, render_video_timeline
from core.nl_media_prompt import ai_video_from_nl, heuristic_video_from_nl
from core.time_parse import parse_timestamp_to_seconds

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
except Exception:  # pragma: no cover
    Image = None  # type: ignore
    ImageEnhance = None  # type: ignore
    ImageFilter = None  # type: ignore
    ImageOps = None  # type: ignore


THEME = {
    "bg": "#1f1f1f",
    "panel": "#2b2f36",
    "panel_dark": "#242424",
    "text": "#e6e6e6",
    "text_muted": "#a7abb3",
    "accent": "#2fa4ff",
    "border": "#3a3f46",
    "btn": "#3a3a3a",
    "btn_hover": "#4a4a4a",
}

_LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "video_editor.log"
_LOG_INIT = False
_FAULT_FH = None
_AFTER_PENDING = object()
_AFTER_CANCELLED = object()


def _dbg(msg: str):
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        ts = ""
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"{ts} | {msg}\n")
    except Exception:
        pass


def _init_logging():
    global _LOG_INIT, _FAULT_FH
    if _LOG_INIT:
        return
    _LOG_INIT = True
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    try:
        logging.basicConfig(
            filename=str(_LOG_PATH),
            level=logging.DEBUG,
            format="%(asctime)s | %(levelname)s | %(message)s",
        )
    except Exception:
        pass
    try:
        _FAULT_FH = open(_LOG_PATH, "a", encoding="utf-8")
        faulthandler.enable(_FAULT_FH)
    except Exception:
        pass
    try:
        logging.info("VideoEditorDialog logging initialized")
    except Exception:
        pass
    _dbg("logging initialized")


def _subprocess_kwargs() -> dict:
    kwargs: dict = {}
    if os.name == "nt":
        try:
            import subprocess

            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            kwargs["startupinfo"] = si
        except Exception:
            return {}
    return kwargs


def _excepthook(exctype, value, tb):
    try:
        logging.error("Unhandled exception", exc_info=(exctype, value, tb))
    except Exception:
        pass
    _dbg(f"Unhandled exception: {exctype.__name__}: {value}")
    try:
        sys.__excepthook__(exctype, value, tb)
    except Exception:
        pass


def _qt_message_handler(_mode, _context, message):
    try:
        logging.error("Qt: %s", message)
    except Exception:
        pass
    _dbg(f"Qt: {message}")


_init_logging()
_dbg("module import complete")
try:
    sys.excepthook = _excepthook
except Exception:
    pass
try:
    qInstallMessageHandler(_qt_message_handler)
except Exception:
    pass


class _Var:
    def __init__(self, value=None):
        self._value = value
        self._watchers = []

    def get(self):
        return self._value

    def set(self, value):
        self._value = value
        for cb in list(self._watchers):
            try:
                cb(value)
            except Exception:
                pass

    def bind(self, cb):
        if cb not in self._watchers:
            self._watchers.append(cb)


class StringVar(_Var):
    def set(self, value):
        super().set("" if value is None else str(value))


class DoubleVar(_Var):
    def set(self, value):
        try:
            v = float(value)
        except Exception:
            v = 0.0
        super().set(v)


class BooleanVar(_Var):
    def set(self, value):
        super().set(bool(value))


@dataclass
class MouseEvent:
    x: int = 0
    y: int = 0
    x_root: int = 0
    y_root: int = 0
    state: int = 0
    widget: QWidget | None = None


def _pil_to_qimage(im):
    if im is None:
        return None
    try:
        from PySide6.QtGui import QImage
        if isinstance(im, QImage):
            return im
        if isinstance(im, QPixmap):
            return im.toImage()
        if getattr(im, "mode", "") != "RGBA":
            im = im.convert("RGBA")
        data = im.tobytes("raw", "RGBA")
        w, h = im.size
        img = QImage(data, w, h, QImage.Format_RGBA8888)
        # Ensure the image owns its memory (avoids use-after-free).
        return img.copy()
    except Exception:
        return None


def _pil_to_pixmap(im) -> QPixmap | None:
    if im is None:
        return None
    if isinstance(im, QPixmap):
        return im
    try:
        try:
            app = QApplication.instance()
            if app is not None and QThread.currentThread() != app.thread():
                return None
        except Exception:
            pass
        qimg = _pil_to_qimage(im)
        if qimg is None:
            return None
        return QPixmap.fromImage(qimg)
    except Exception:
        return None


def _clear_layout(layout):
    if layout is None:
        return
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            try:
                w.setParent(None)
                w.deleteLater()
            except Exception:
                pass


class SegmentedButton(QWidget):
    valueChanged = Signal(str)

    def __init__(self, values=None, variable: StringVar | None = None, parent=None):
        super().__init__(parent)
        self._var = variable
        self._buttons = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        group = QButtonGroup(self)
        group.setExclusive(True)
        self._group = group
        for v in values or []:
            btn = QPushButton(str(v))
            btn.setCheckable(True)
            btn.clicked.connect(lambda _c=False, vv=str(v): self._on_select(vv))
            btn.setStyleSheet(
                "QPushButton{background-color:#2b2f36;color:#e6e6e6;border:1px solid #3a3f46;border-radius:6px;padding:4px 10px;}"
                "QPushButton:checked{background-color:#2fa4ff;color:#0b0c0e;}"
            )
            layout.addWidget(btn)
            group.addButton(btn)
            self._buttons[str(v)] = btn
        if variable is not None:
            try:
                self.set_value(variable.get())
                variable.bind(self.set_value)
            except Exception:
                pass

    def _on_select(self, value: str):
        self.set_value(value)
        self.valueChanged.emit(value)
        if self._var is not None:
            try:
                self._var.set(value)
            except Exception:
                pass

    def set_value(self, value: str):
        key = str(value)
        for k, btn in self._buttons.items():
            btn.setChecked(k == key)


class ScrollAreaFrame(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.viewport().installEventFilter(self)
        content = QWidget()
        self._content = content
        self._layout = QGridLayout(content)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.setWidget(content)
        self.on_drag_enter = None
        self.on_drag_move = None
        self.on_drag_leave = None
        self.on_drop = None

    @property
    def content(self):
        return self._content

    @property
    def layout(self):
        return self._layout

    def dragEnterEvent(self, event):
        try:
            if callable(self.on_drag_enter) and self.on_drag_enter(event):
                event.acceptProposedAction()
                return
        except Exception:
            pass
        event.ignore()

    def dragMoveEvent(self, event):
        try:
            if callable(self.on_drag_move) and self.on_drag_move(event):
                event.acceptProposedAction()
                return
        except Exception:
            pass
        event.ignore()

    def dragLeaveEvent(self, event):
        try:
            if callable(self.on_drag_leave):
                self.on_drag_leave(event)
        except Exception:
            pass
        return super().dragLeaveEvent(event)

    def dropEvent(self, event):
        try:
            if callable(self.on_drop) and self.on_drop(event):
                event.acceptProposedAction()
                return
        except Exception:
            pass
        event.ignore()




    def eventFilter(self, obj, event):
        if obj is self.viewport():
            et = event.type()
            if et == QEvent.DragEnter:
                self.dragEnterEvent(event)
                return event.isAccepted()
            if et == QEvent.DragMove:
                self.dragMoveEvent(event)
                return event.isAccepted()
            if et == QEvent.DragLeave:
                self.dragLeaveEvent(event)
                return True
            if et == QEvent.Drop:
                self.dropEvent(event)
                return event.isAccepted()
        return super().eventFilter(obj, event)
class TimelineCanvas(QWidget):
    def __init__(self, parent=None, height=190):
        super().__init__(parent)
        self._items = []
        self.setMinimumHeight(int(height))
        self.setStyleSheet("background-color: #1b1f25;")
        self.setAcceptDrops(True)
        self.on_configure = None
        self.on_click = None
        self.on_drag = None
        self.on_release = None
        self.on_double = None
        self.on_drag_enter = None
        self.on_drag_move = None
        self.on_drag_leave = None
        self.on_drop = None

    def _to_mouse_event(self, event):
        gp = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
        state = 0x0001 if event.modifiers() & Qt.ShiftModifier else 0
        return MouseEvent(
            x=int(event.position().x()) if hasattr(event, "position") else int(event.x()),
            y=int(event.position().y()) if hasattr(event, "position") else int(event.y()),
            x_root=int(gp.x()),
            y_root=int(gp.y()),
            state=state,
            widget=self,
        )

    def winfo_width(self):
        try:
            return int(self.width())
        except Exception:
            return 0

    def winfo_height(self):
        try:
            return int(self.height())
        except Exception:
            return 0

    def winfo_rootx(self):
        try:
            return int(self.mapToGlobal(QPoint(0, 0)).x())
        except Exception:
            return 0

    def winfo_rooty(self):
        try:
            return int(self.mapToGlobal(QPoint(0, 0)).y())
        except Exception:
            return 0

    def delete(self, item):
        if item == "all":
            self._items = []
        else:
            try:
                idx = int(item) - 1
                if 0 <= idx < len(self._items):
                    self._items[idx] = None
            except Exception:
                pass
        self.update()

    def create_rectangle(self, x1, y1, x2, y2, fill=None, outline=None, width=1, **kwargs):
        self._items.append(("rect", x1, y1, x2, y2, fill, outline, width, kwargs))
        self.update()
        return len(self._items)

    def create_line(self, x1, y1, x2, y2, fill=None, width=1, **kwargs):
        self._items.append(("line", x1, y1, x2, y2, fill, width, kwargs))
        self.update()
        return len(self._items)

    def create_text(self, x, y, text="", anchor="w", fill=None, **kwargs):
        self._items.append(("text", x, y, text, anchor, fill, kwargs))
        self.update()
        return len(self._items)

    def create_polygon(self, *points, fill=None, outline=None, **kwargs):
        self._items.append(("poly", points, fill, outline, kwargs))
        self.update()
        return len(self._items)

    def create_image(self, x, y, anchor="nw", image=None, **kwargs):
        self._items.append(("image", x, y, anchor, image, kwargs))
        self.update()
        return len(self._items)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        for item in self._items:
            if not item:
                continue
            itype = item[0]
            if itype == "rect":
                _, x1, y1, x2, y2, fill, outline, width, kw = item
                if fill:
                    c = QColor(fill)
                    if kw.get("stipple"):
                        c.setAlpha(90)
                    painter.fillRect(QRect(int(x1), int(y1), int(x2 - x1), int(y2 - y1)), c)
                if outline:
                    pen = QPen(QColor(outline))
                    pen.setWidth(int(width or 1))
                    painter.setPen(pen)
                    painter.drawRect(int(x1), int(y1), int(x2 - x1), int(y2 - y1))
            elif itype == "line":
                _, x1, y1, x2, y2, fill, width, _kw = item
                pen = QPen(QColor(fill or "#ffffff"))
                pen.setWidth(int(width or 1))
                painter.setPen(pen)
                painter.drawLine(int(x1), int(y1), int(x2), int(y2))
            elif itype == "text":
                _, x, y, text, anchor, fill, _kw = item
                if fill:
                    painter.setPen(QPen(QColor(fill)))
                fm = painter.fontMetrics()
                tx = int(x)
                ty = int(y)
                if anchor in ("nw", "n"):
                    ty += fm.ascent()
                elif anchor in ("w", "center"):
                    ty += fm.ascent() // 2
                painter.drawText(tx, ty, str(text))
            elif itype == "poly":
                _, points, fill, outline, _kw = item
                poly = []
                for i in range(0, len(points), 2):
                    try:
                        poly.append(QPoint(int(points[i]), int(points[i + 1])))
                    except Exception:
                        pass
                if fill:
                    painter.setBrush(QBrush(QColor(fill)))
                if outline:
                    painter.setPen(QPen(QColor(outline)))
                if poly:
                    painter.drawPolygon(poly)
            elif itype == "image":
                _, x, y, _anchor, image, _kw = item
                pm = image
                if isinstance(pm, QPixmap):
                    painter.drawPixmap(int(x), int(y), pm)

    def resizeEvent(self, event):
        if callable(self.on_configure):
            try:
                self.on_configure(event)
            except Exception:
                pass
        return super().resizeEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and callable(self.on_click):
            self.on_click(self._to_mouse_event(event))
        return super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and callable(self.on_drag):
            self.on_drag(self._to_mouse_event(event))
        return super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and callable(self.on_release):
            self.on_release(self._to_mouse_event(event))
        return super().mouseReleaseEvent(event)


class DragTag(QFrame):
    def __init__(self, text: str, mime_type: str, payload: str, parent=None):
        super().__init__(parent)
        self._mime_type = mime_type
        self._payload = payload
        self._drag_start = None
        self.setObjectName("dragTag")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)
        label = QLabel(text)
        label.setStyleSheet("color:#e6e6e6;")
        layout.addWidget(label)
        self.setStyleSheet(
            "QFrame#dragTag{background-color:#2b2f36;border:1px solid #3a3f46;border-radius:8px;}"
            "QFrame#dragTag:hover{background-color:#313640;}"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.position().toPoint() if hasattr(event, "position") else event.pos()
        return super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return super().mouseMoveEvent(event)
        if self._drag_start is None:
            return super().mouseMoveEvent(event)
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        if (pos - self._drag_start).manhattanLength() < 6:
            return super().mouseMoveEvent(event)
        drag = QDrag(self)
        mime = QMimeData()
        try:
            mime.setData(self._mime_type, bytes(self._payload, "utf-8"))
        except Exception:
            mime.setText(self._payload)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)
        return super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and callable(self.on_double):
            self.on_double(self._to_mouse_event(event))
        return super().mouseDoubleClickEvent(event)

    def dragEnterEvent(self, event):
        try:
            if callable(self.on_drag_enter) and self.on_drag_enter(event):
                event.acceptProposedAction()
                return
        except Exception:
            pass
        event.ignore()

    def dragMoveEvent(self, event):
        try:
            if callable(self.on_drag_move) and self.on_drag_move(event):
                event.acceptProposedAction()
                return
        except Exception:
            pass
        event.ignore()

    def dragLeaveEvent(self, event):
        try:
            if callable(self.on_drag_leave):
                self.on_drag_leave(event)
        except Exception:
            pass
        return super().dragLeaveEvent(event)

    def dropEvent(self, event):
        try:
            if callable(self.on_drop) and self.on_drop(event):
                event.acceptProposedAction()
                return
        except Exception:
            pass
        event.ignore()

    def _to_mouse_event(self, event):
        gp = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
        state = 0x0001 if event.modifiers() & Qt.ShiftModifier else 0
        return MouseEvent(
            x=int(event.position().x()) if hasattr(event, "position") else int(event.x()),
            y=int(event.position().y()) if hasattr(event, "position") else int(event.y()),
            x_root=int(gp.x()),
            y_root=int(gp.y()),
            state=state,
            widget=self,
        )

    def winfo_width(self):
        return int(self.width())

    def winfo_height(self):
        return int(self.height())

    def winfo_rootx(self):
        try:
            return int(self.mapToGlobal(QPoint(0, 0)).x())
        except Exception:
            return 0

    def winfo_rooty(self):
        try:
            return int(self.mapToGlobal(QPoint(0, 0)).y())
        except Exception:
            return 0

    def winfo_width(self):
        try:
            return int(self.width())
        except Exception:
            return 0

    def winfo_height(self):
        try:
            return int(self.height())
        except Exception:
            return 0

    def resizeEvent(self, event):
        try:
            self._position_sidebar_toggle()
        except Exception:
            pass
        return super().resizeEvent(event)

    def showEvent(self, event):
        _dbg("VideoEditorDialog showEvent")
        try:
            self._position_sidebar_toggle()
            QTimer.singleShot(0, self._position_sidebar_toggle)
            QTimer.singleShot(120, self._position_sidebar_toggle)
            QTimer.singleShot(320, self._position_sidebar_toggle)
        except Exception:
            pass
        return super().showEvent(event)

    def closeEvent(self, event):
        _dbg("VideoEditorDialog closeEvent")
        return super().closeEvent(event)

    def keyPressEvent(self, event):
        try:
            fw = QApplication.focusWidget()
            if fw and (
                isinstance(fw, QLineEdit)
                or isinstance(fw, QComboBox)
                or fw.inherits("QAbstractSpinBox")
                or fw.inherits("QTextEdit")
                or fw.inherits("QPlainTextEdit")
            ):
                return super().keyPressEvent(event)
        except Exception:
            pass
        if self.left_stack.currentWidget() == self.media_list and self._selected:
            try:
                if fw and fw is not self.media_list and not self.media_list.isAncestorOf(fw):
                    return super().keyPressEvent(event)
            except Exception:
                pass
            key = event.key()
            mods = event.modifiers()
            if key in (Qt.Key_Delete, Qt.Key_Backspace):
                self._remove_media(self._selected)
                event.accept()
                return
            if key == Qt.Key_R:
                if mods & Qt.ShiftModifier:
                    self._rotate_media(self._selected, -90)
                else:
                    self._rotate_media(self._selected, 90)
                event.accept()
                return
            if key == Qt.Key_0:
                self._reset_media_rotation(self._selected)
                event.accept()
                return
        return super().keyPressEvent(event)


class EventRelay(QObject):
    def __init__(self, on_double=None, on_press=None, on_move=None, on_release=None):
        super().__init__()
        self._on_double = on_double
        self._on_press = on_press
        self._on_move = on_move
        self._on_release = on_release

    def eventFilter(self, obj, event):
        try:
            if event.type() == QEvent.MouseButtonDblClick and self._on_double:
                self._on_double(self._to_mouse_event(event, obj))
                return True
            if event.type() == QEvent.MouseButtonPress and self._on_press:
                if event.button() == Qt.LeftButton:
                    self._on_press(self._to_mouse_event(event, obj))
                    return True
            if event.type() == QEvent.MouseMove and self._on_move:
                if event.buttons() & Qt.LeftButton:
                    self._on_move(self._to_mouse_event(event, obj))
                    return True
            if event.type() == QEvent.MouseButtonRelease and self._on_release:
                if event.button() == Qt.LeftButton:
                    self._on_release(self._to_mouse_event(event, obj))
                    return True
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _to_mouse_event(self, event, widget):
        gp = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
        state = 0x0001 if event.modifiers() & Qt.ShiftModifier else 0
        return MouseEvent(
            x=int(event.position().x()) if hasattr(event, "position") else int(event.x()),
            y=int(event.position().y()) if hasattr(event, "position") else int(event.y()),
            x_root=int(gp.x()),
            y_root=int(gp.y()),
            state=state,
            widget=widget,
        )


class UiDispatcher(QObject):
    call = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.call.connect(self._run, Qt.QueuedConnection)

    def _run(self, fn):
        try:
            fn()
        except Exception:
            pass


class FloatSlider(QSlider):
    valueChangedFloat = Signal(float)

    def __init__(self, from_=0.0, to=1.0, steps=1000, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._from = float(from_ or 0.0)
        self._to = float(to or 1.0)
        self._steps = int(steps or 1000)
        self.setRange(0, self._steps)
        self.valueChanged.connect(self._emit_float)

    def _emit_float(self, value: int):
        span = self._to - self._from
        if span == 0:
            self.valueChangedFloat.emit(self._from)
            return
        f = self._from + (span * (float(value) / float(self._steps)))
        self.valueChangedFloat.emit(float(f))

    def setValueFloat(self, value: float):
        span = self._to - self._from
        if span == 0:
            self.setValue(0)
            return
        v = int(round(((float(value) - self._from) / span) * float(self._steps)))
        v = max(0, min(self._steps, v))
        self.setValue(v)

    def valueFloat(self) -> float:
        span = self._to - self._from
        if span == 0:
            return float(self._from)
        return float(self._from + (span * (float(self.value()) / float(self._steps))))


def bind_line_edit(var: StringVar, edit: QLineEdit):
    try:
        edit.setText(var.get() or "")
    except Exception:
        pass

    def update_from_var(value):
        try:
            if edit.text() == ("" if value is None else str(value)):
                return
            with QSignalBlocker(edit):
                edit.setText("" if value is None else str(value))
        except Exception:
            pass

    var.bind(update_from_var)
    edit.textChanged.connect(lambda t: var.set(t))


def bind_combo(var: StringVar, combo: QComboBox):
    def update_from_var(value):
        try:
            text = "" if value is None else str(value)
            idx = combo.findText(text)
            if idx >= 0:
                with QSignalBlocker(combo):
                    combo.setCurrentIndex(idx)
        except Exception:
            pass

    var.bind(update_from_var)
    combo.currentTextChanged.connect(lambda t: var.set(t))


def bind_checkbox(var: BooleanVar, checkbox: QCheckBox):
    def update_from_var(value):
        try:
            with QSignalBlocker(checkbox):
                checkbox.setChecked(bool(value))
        except Exception:
            pass

    var.bind(update_from_var)
    checkbox.toggled.connect(lambda v: var.set(bool(v)))


def bind_float_slider(var: DoubleVar, slider: FloatSlider):
    def update_from_var(value):
        try:
            with QSignalBlocker(slider):
                slider.setValueFloat(float(value))
        except Exception:
            pass

    var.bind(update_from_var)
    slider.valueChangedFloat.connect(lambda v: var.set(float(v)))


def _parse_time(s: str) -> float | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        pass
    try:
        return float(parse_timestamp_to_seconds(s))
    except Exception:
        return None


def _fmt_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    hh = int(seconds // 3600)
    mm = int((seconds % 3600) // 60)
    ss = seconds % 60
    return f"{hh:02d}:{mm:02d}:{ss:06.3f}".replace(".000", "")


def _is_image_suffix(path: Path) -> bool:
    return path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


def _is_audio_suffix(path: Path) -> bool:
    return path.suffix.lower() in {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus"}


class VideoEditorDialog(QDialog):
    _instances = []
    _qt_app = None

    def __init__(self, parent, ai_manager=None, initial_file: Path | None = None):
        _dbg("VideoEditorDialog init start")
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        try:
            app.setQuitOnLastWindowClosed(False)
        except Exception:
            pass

        if parent is not None and not isinstance(parent, QDialog) and not hasattr(parent, "windowTitle"):
            parent = None

        super().__init__(parent)
        try:
            self.__class__._instances.append(self)
            self.destroyed.connect(lambda _=None, inst=self: self._instances.remove(inst) if inst in self._instances else None)
            self.__class__._qt_app = app
        except Exception:
            pass
        self.ai_manager = ai_manager
        self.setWindowTitle("Video Editor - Fylorra")
        self.resize(1440, 860)
        self.setMinimumSize(1280, 800)
        self.setWindowFlags(Qt.Window)
        self._root_layout = None
        self._bind_handlers = {}
        self._after_timers = {}
        self._after_lock = threading.Lock()
        self._ui_dispatcher = UiDispatcher(self)

        self._files: list[Path] = []
        self._selected: Path | None = None
        self._timeline: list[TimelineClip] = []
        self._timeline_selected: int | None = None
        self._audio_track: list[TimelineClip] = []
        self._timeline_transitions: dict[int, dict] = {}
        self._audio_selected: int | None = None
        self._audio_bed_path: Path | None = None
        self._cancel = threading.Event()
        self._render_thread: threading.Thread | None = None
        self._thumb_lock = threading.Lock()
        self._thumb_images: dict[str, QPixmap] = {}
        self._filmstrip_cache: dict[str, list] = {}
        self._filmstrip_inflight: set[str] = set()
        self._meta_lock = threading.Lock()
        self._media_meta: dict[str, dict] = {}
        self._meta_inflight: set[str] = set()
        self._media_rotations: dict[str, int] = {}
        self._preview_busy = False
        self._is_playing = False
        self._play_after_id: str | None = None
        self._preview_after_id: str | None = None
        self._play_timer: QTimer | None = None
        self._preview_cache: dict[str, QPixmap] = {}
        self._preview_cache_order: list[str] = []
        self._play_last_ts: float | None = None
        self._media_player = None
        self._audio_output = None
        self._video_widget = None
        self._preview_stack = None
        self._video_blur_effect = None
        self._use_qt_player = False
        self._live_transition_preview = False
        self._player_syncing = False
        self._player_mode = None
        self._player_clip_idx = None
        self._player_clip_start_t = 0.0
        self._player_clip_start_ms = 0
        self._player_clip_end_ms = None
        self._player_src_path = None

        self._range_selecting: bool = False
        self._range_start_s: float | None = None
        self._range_end_s: float | None = None
        self._tl_zoom: float = 1.0
        self._tl_pan: float = 0.0
        self._dur_cache: dict[str, float] = {}
        self._audio_wave_cache: dict[str, list[float]] = {}
        self._audio_wave_inflight: set[str] = set()
        self._drag_state = None
        self._duration: float = 0.0
        self._fps: float = 0.0
        self._audio_lane_count: int = 2
        self._drag_media_path: Path | None = None
        self._drag_pending_path: Path | None = None
        self._drag_press_xy: tuple[int, int] | None = None
        self._drag_indicator_id: int | None = None
        self._drag_indicator_time: float | None = None
        self._toast_after_id: str | None = None
        self._tooltip_win = None
        self._tip_text = "Shift+drag on timeline to select a range (then Cut Out)."

        try:
            self._build_ui()
        except Exception:
            try:
                logging.exception("VideoEditorDialog _build_ui failed")
            except Exception:
                pass
            _dbg("VideoEditorDialog _build_ui failed")
            raise
        try:
            self._switch_left_mode()
        except Exception:
            pass
        try:
            self._apply_realtime_fx()
        except Exception:
            pass
        try:
            self._play_timer = QTimer(self)
            self._play_timer.setInterval(120)
            self._play_timer.timeout.connect(self._play_tick)
        except Exception:
            self._play_timer = None
        if initial_file:
            self.add_files([Path(initial_file)])
        self.show()
        _dbg("VideoEditorDialog shown")

        # Some Windows configurations apply toolwindow attributes late for CTkToplevel;
        # force a second pass after the window is realized.
        self.after(0, self._ensure_native_window_buttons)
        # Ensure this editor opens in front of the main window.
        self.after(0, self._bring_to_front)
        self.after(200, self._bring_to_front)
        _dbg("VideoEditorDialog init end")

    def _ensure_root_layout(self):
        if self._root_layout is None:
            try:
                existing = self.layout()
            except Exception:
                existing = None
            if existing is not None:
                self._root_layout = existing
                try:
                    setattr(self, "_grid_layout", existing)
                except Exception:
                    pass
                return self._root_layout
            layout = QGridLayout()
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self.setLayout(layout)
            self._root_layout = layout
            try:
                setattr(self, "_grid_layout", layout)
            except Exception:
                pass
        return self._root_layout

    def grid_columnconfigure(self, index, weight=0, minsize=None):
        layout = self._ensure_root_layout()
        try:
            layout.setColumnStretch(int(index), int(weight))
        except Exception:
            pass
        if minsize is not None:
            try:
                layout.setColumnMinimumWidth(int(index), int(minsize))
            except Exception:
                pass

    def grid_rowconfigure(self, index, weight=0, minsize=None):
        layout = self._ensure_root_layout()
        try:
            layout.setRowStretch(int(index), int(weight))
        except Exception:
            pass
        if minsize is not None:
            try:
                layout.setRowMinimumHeight(int(index), int(minsize))
            except Exception:
                pass

    def bind(self, sequence, func):
        self._bind_handlers.setdefault(sequence, []).append(func)
        try:
            self.installEventFilter(self)
        except Exception:
            pass

    def eventFilter(self, obj, event):
        try:
            handlers = self._bind_handlers

            def fire(seq):
                for cb in handlers.get(seq, []):
                    try:
                        cb(event)
                    except Exception:
                        pass

            if event.type() == event.Resize:
                fire("<Configure>")
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _after_ui_token(self, tid, ms, callback):
        with self._after_lock:
            state = self._after_timers.get(tid)
            if state is None:
                return
            if state is _AFTER_CANCELLED:
                self._after_timers.pop(tid, None)
                return
            if isinstance(state, QTimer):
                return
            timer = QTimer(self)
            self._after_timers[tid] = timer

        def _fire():
            try:
                callback()
            finally:
                with self._after_lock:
                    self._after_timers.pop(tid, None)
                try:
                    timer.deleteLater()
                except Exception:
                    pass

        timer.setSingleShot(True)
        timer.timeout.connect(_fire)
        timer.start(int(ms))

    def after(self, ms, callback):
        tid = f"after_{time.monotonic_ns()}"
        with self._after_lock:
            self._after_timers[tid] = _AFTER_PENDING
        self._ui_dispatcher.call.emit(lambda: self._after_ui_token(tid, ms, callback))
        return tid

    def _after_cancel_ui(self, tid):
        with self._after_lock:
            state = self._after_timers.pop(str(tid), None)
        if isinstance(state, QTimer):
            try:
                state.stop()
            except Exception:
                pass
            try:
                state.deleteLater()
            except Exception:
                pass

    def after_cancel(self, tid):
        if not tid:
            return
        with self._after_lock:
            state = self._after_timers.get(str(tid))
            if state is None:
                return
            self._after_timers[str(tid)] = _AFTER_CANCELLED
        self._ui_dispatcher.call.emit(lambda: self._after_cancel_ui(tid))

    def state(self, value=None):
        if value is None:
            return "zoomed" if self.isMaximized() else "normal"
        if str(value).lower() == "zoomed":
            self.showMaximized()
        else:
            self.showNormal()

    def winfo_containing(self, x_root, y_root):
        try:
            return QApplication.widgetAt(QPoint(int(x_root), int(y_root)))
        except Exception:
            return None

    def winfo_rootx(self):
        try:
            return int(self.mapToGlobal(QPoint(0, 0)).x())
        except Exception:
            return 0

    def winfo_rooty(self):
        try:
            return int(self.mapToGlobal(QPoint(0, 0)).y())
        except Exception:
            return 0

    def _bring_to_front(self):
        try:
            self.raise_()
        except Exception:
            pass
        try:
            # Temporarily toggle topmost to reliably raise on Windows.
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
            self.show()
            self.after(150, lambda: self.setWindowFlag(Qt.WindowStaysOnTopHint, False))
        except Exception:
            pass
        try:
            self.activateWindow()
        except Exception:
            pass

    def _ensure_native_window_buttons(self):
        try:
            self.setWindowFlags(self.windowFlags() | Qt.Window)
            self.show()
        except Exception:
            pass

    def _show_prompt_examples(self):
        msg = (
            "Examples:\n"
            "1) grab clip 1 - intro.mp4 and cut between 0:10 to 0:25 and export as intro_cut.mp4 720p h265 30fps gpu\n"
            "2) cut 1:23-1:41, export mkv 1080p h264 crf 18\n"
            "3) export mp4 720p h264 30fps\n"
            "\n"
            "Tip: the editor applies a fast offline parse immediately, then (if the AI model is loaded) it refines the parse in the background."
        )
        try:
            QMessageBox.information(self, "Video Prompt Examples", msg)
        except Exception:
            pass
        # Note: do not call transient/grab here; it can remove native maximize/minimize buttons on Windows
        # and also makes the editor modal (closing the launcher would close it).
        return

    def _build_ui(self):
        self._sidebar_width = 420
        self._sidebar_collapsed = False
        self._icons: dict[str, QPixmap] = {}

        self.setStyleSheet(
            "QDialog{background-color:#1f1f1f;}"
            "QLabel{color:#e6e6e6;}"
            "QLineEdit{background-color:#2b2f36;color:#e6e6e6;border:1px solid #3a3f46;border-radius:8px;padding:6px;}"
            "QComboBox{background-color:#2b2f36;color:#e6e6e6;border:1px solid #3a3f46;border-radius:6px;padding:4px 6px;}"
            "QComboBox::drop-down{border:0;}"
            "QCheckBox{color:#e6e6e6;}"
            "QFrame#panel{background-color:#2b2f36;border-radius:10px;}"
        )

        root = self._ensure_root_layout()
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)
        root.setRowStretch(1, 1)

        # Top bar
        top = QFrame(self)
        top.setObjectName("panel")
        self._top_bar = top
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(12, 10, 12, 10)
        top_layout.setSpacing(10)
        self.prompt_var = StringVar(value="")
        self.prompt_entry = QLineEdit()
        self.prompt_entry.setPlaceholderText("Ask: grab clip 1 - intro.mp4, cut 0:10-0:25, export intro_cut.mp4 720p h265 30fps")
        bind_line_edit(self.prompt_var, self.prompt_entry)
        self.prompt_entry.returnPressed.connect(self._apply_prompt)
        top_layout.addWidget(self.prompt_entry, 1)

        apply_btn = QPushButton("Apply")
        apply_btn.setFixedWidth(90)
        apply_btn.setFixedHeight(36)
        apply_btn.clicked.connect(self._apply_prompt)
        render_btn = QPushButton("Render")
        render_btn.setFixedWidth(120)
        render_btn.setFixedHeight(36)
        render_btn.clicked.connect(self._start_render)
        help_btn = QPushButton("i")
        help_btn.setFixedSize(36, 36)
        help_btn.clicked.connect(self._show_prompt_examples)
        help_btn.setStyleSheet(f"QPushButton{{background-color:{THEME['btn']};border-radius:6px;color:{THEME['text']};}}QPushButton:hover{{background-color:{THEME['btn_hover']};}}")
        top_layout.addWidget(apply_btn)
        top_layout.addWidget(render_btn)
        top_layout.addWidget(help_btn)
        help_btn.enterEvent = lambda _e: self._show_tooltip(help_btn, "Prompt examples")
        help_btn.leaveEvent = lambda _e: self._hide_tooltip()
        root.addWidget(top, 0, 0, 1, 2)

        # Main splitter (left sidebar + right editor)
        self._main_splitter = QSplitter(Qt.Horizontal, self)
        self._main_splitter.setHandleWidth(6)
        self._main_splitter.splitterMoved.connect(self._on_splitter_moved)
        root.addWidget(self._main_splitter, 1, 0, 1, 2)

        # Left sidebar
        left = QFrame(self)
        left.setObjectName("panel")
        self.sidebar_frame = left
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(10)

        left_top = QWidget(left)
        left_top_layout = QHBoxLayout(left_top)
        left_top_layout.setContentsMargins(0, 0, 0, 0)
        left_top_layout.setSpacing(6)
        self.left_mode = StringVar(value="Media")
        self.left_tabs = SegmentedButton(values=["Media", "Transitions", "Effects"], variable=self.left_mode, parent=left_top)
        self.left_tabs.valueChanged.connect(self._switch_left_mode)
        left_top_layout.addWidget(self.left_tabs, 1)
        left_layout.addWidget(left_top)

        self.left_header = QWidget(left)
        header_layout = QHBoxLayout(self.left_header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)
        self._sidebar_title = QLabel("Project Media")
        self._sidebar_title.setFont(QFont("", 10, QFont.Bold))
        header_layout.addWidget(self._sidebar_title, 1)
        self._icon_add = self._load_icon("add-media.png", (18, 18), pack="video_editor") or self._load_icon("add.png", (18, 18))
        self._icon_rotate = self._load_icon("loop.png", (16, 16), pack="video_editor")
        self._info_btn = QPushButton("i")
        self._info_btn.setFixedSize(30, 30)
        self._info_btn.setStyleSheet(f"QPushButton{{background-color:{THEME['btn']};border-radius:6px;}}QPushButton:hover{{background-color:{THEME['btn_hover']};}}")
        self._info_btn.enterEvent = lambda _e: self._show_tooltip(self._info_btn, self._sidebar_help_text())
        self._info_btn.leaveEvent = lambda _e: self._hide_tooltip()
        header_layout.addWidget(self._info_btn)

        self._sidebar_import_btn = QPushButton("" if self._icon_add else "Import")
        self._sidebar_import_btn.setFixedSize(36, 30)
        if self._icon_add:
            self._sidebar_import_btn.setIcon(QIcon(self._icon_add))
            self._sidebar_import_btn.setIconSize(QSize(18, 18))
        self._sidebar_import_btn.clicked.connect(self._import_files)
        header_layout.addWidget(self._sidebar_import_btn)

        self._sidebar_hide_btn = QPushButton("<")
        self._sidebar_hide_btn.setFixedSize(36, 30)
        self._sidebar_hide_btn.setStyleSheet(f"QPushButton{{background-color:{THEME['btn']};border-radius:6px;}}QPushButton:hover{{background-color:{THEME['btn_hover']};}}")
        self._sidebar_hide_btn.clicked.connect(self._toggle_sidebar)
        self._sidebar_hide_btn.setVisible(False)
        header_layout.addWidget(self._sidebar_hide_btn)

        left_layout.addWidget(self.left_header)

        self.left_stack = QStackedWidget(left)

        self.media_list = ScrollAreaFrame(left)
        self.media_list.content.setObjectName("mediaList")
        self.media_list.layout.setSpacing(8)
        self.media_list.layout.setContentsMargins(0, 0, 0, 0)
        self.left_stack.addWidget(self.media_list)

        self.transitions_panel = QFrame(left)
        trans_layout = QVBoxLayout(self.transitions_panel)
        trans_layout.setContentsMargins(8, 8, 8, 8)
        trans_layout.setSpacing(8)
        trans_title = QLabel("Transitions")
        trans_title.setStyleSheet(f"color:{THEME['text']};font-weight:600;")
        trans_layout.addWidget(trans_title)

        trans_row = QWidget(self.transitions_panel)
        trans_row_layout = QGridLayout(trans_row)
        trans_row_layout.setContentsMargins(0, 0, 0, 0)
        trans_row_layout.setHorizontalSpacing(8)
        trans_row_layout.setVerticalSpacing(8)
        trans_row_layout.addWidget(QLabel("Type"), 0, 0)
        self.transition_var = StringVar(value="None")
        self.transition_menu = QComboBox()
        self.transition_menu.addItems(["None", "Cross Dissolve", "Dip to Black", "Slide Left", "Wipe Left"])
        bind_combo(self.transition_var, self.transition_menu)
        self.transition_menu.currentTextChanged.connect(self._on_transition_change)
        trans_row_layout.addWidget(self.transition_menu, 0, 1, 1, 2)

        trans_row_layout.addWidget(QLabel("Duration"), 1, 0)
        self.transition_dur_var = DoubleVar(value=0.6)
        self.transition_dur_slider = FloatSlider(from_=0.0, to=2.0, steps=200)
        bind_float_slider(self.transition_dur_var, self.transition_dur_slider)
        self.transition_dur_slider.valueChangedFloat.connect(lambda _v=None: self._on_transition_change())
        trans_row_layout.addWidget(self.transition_dur_slider, 1, 1)
        self.transition_dur_label = QLabel("0.60s")
        self.transition_dur_label.setStyleSheet(f"color:{THEME['text_muted']};")
        trans_row_layout.addWidget(self.transition_dur_label, 1, 2)
        trans_layout.addWidget(trans_row)

        trans_hint = QLabel("Select a transition + duration. It applies between adjacent clips when rendering.")
        trans_hint.setStyleSheet(f"color:{THEME['text_muted']};")
        trans_layout.addWidget(trans_hint)
        drag_hint = QLabel("Drag a transition onto the cut between clips.")
        drag_hint.setStyleSheet(f"color:{THEME['text_muted']};")
        trans_layout.addWidget(drag_hint)
        trans_drag = QWidget(self.transitions_panel)
        trans_drag_layout = QGridLayout(trans_drag)
        trans_drag_layout.setContentsMargins(0, 0, 0, 0)
        trans_drag_layout.setHorizontalSpacing(8)
        trans_drag_layout.setVerticalSpacing(8)
        transition_items = ["Cross Dissolve", "Dip to Black", "Slide Left", "Wipe Left", "Clear"]
        row = 0
        col = 0
        for name in transition_items:
            tag = DragTag(name, "application/x-fylorra-transition", name, trans_drag)
            trans_drag_layout.addWidget(tag, row, col)
            col += 1
            if col >= 2:
                col = 0
                row += 1
        trans_layout.addWidget(trans_drag)
        trans_layout.addStretch(1)
        self.left_stack.addWidget(self.transitions_panel)

        self.effects_panel = QFrame(left)
        eff_layout = QVBoxLayout(self.effects_panel)
        eff_layout.setContentsMargins(8, 8, 8, 8)
        eff_layout.setSpacing(8)
        eff_title = QLabel("Effects")
        eff_title.setStyleSheet(f"color:{THEME['text']};font-weight:600;")
        eff_layout.addWidget(eff_title)
        eff_drag_label = QLabel("Drag a preset onto a clip (applies globally for now).")
        eff_drag_label.setStyleSheet(f"color:{THEME['text_muted']};")
        eff_layout.addWidget(eff_drag_label)
        eff_drag = QWidget(self.effects_panel)
        eff_drag_layout = QGridLayout(eff_drag)
        eff_drag_layout.setContentsMargins(0, 0, 0, 0)
        eff_drag_layout.setHorizontalSpacing(8)
        eff_drag_layout.setVerticalSpacing(8)
        effect_items = ["Warm", "Cool", "B&W", "Punchy", "Soft", "Reset"]
        row = 0
        col = 0
        for name in effect_items:
            tag = DragTag(name, "application/x-fylorra-effect", name, eff_drag)
            eff_drag_layout.addWidget(tag, row, col)
            col += 1
            if col >= 2:
                col = 0
                row += 1
        eff_layout.addWidget(eff_drag)

        eff_scroll = QScrollArea(self.effects_panel)
        eff_scroll.setWidgetResizable(True)
        eff_scroll.setFrameShape(QFrame.NoFrame)
        eff_content = QWidget(eff_scroll)
        eff_scroll.setWidget(eff_content)
        eff_content_layout = QVBoxLayout(eff_content)
        eff_content_layout.setContentsMargins(0, 0, 0, 0)
        eff_content_layout.setSpacing(10)

        def add_fx_slider(title, var, vmin, vmax, steps=200, fmt="{:.2f}", hint=None):
            row = QFrame(eff_content)
            row.setObjectName("panel")
            row_layout = QGridLayout(row)
            row_layout.setContentsMargins(8, 8, 8, 8)
            row_layout.setHorizontalSpacing(8)
            row_layout.setVerticalSpacing(4)
            label = QLabel(title)
            row_layout.addWidget(label, 0, 0)
            value_lbl = QLabel(fmt.format(float(var.get() or 0.0)))
            value_lbl.setStyleSheet(f"color:{THEME['text_muted']};")
            row_layout.addWidget(value_lbl, 0, 1, alignment=Qt.AlignRight)
            slider = FloatSlider(from_=vmin, to=vmax, steps=steps)
            bind_float_slider(var, slider)
            slider.valueChangedFloat.connect(lambda _v=None, v=var, l=value_lbl, f=fmt: l.setText(f.format(float(v.get() or 0.0))))
            slider.valueChangedFloat.connect(lambda _v=None: self._on_fx_change())
            row_layout.addWidget(slider, 1, 0, 1, 2)
            if hint:
                hint_lbl = QLabel(hint)
                hint_lbl.setStyleSheet(f"color:{THEME['text_muted']};")
                row_layout.addWidget(hint_lbl, 2, 0, 1, 2)
            eff_content_layout.addWidget(row)
            return slider

        self.fx_brightness = DoubleVar(value=0.0)
        self.fx_contrast = DoubleVar(value=1.0)
        self.fx_saturation = DoubleVar(value=1.0)
        self.fx_hue = DoubleVar(value=0.0)
        self.fx_blur = DoubleVar(value=0.0)
        self.fx_sharpen = DoubleVar(value=0.0)

        add_fx_slider("Brightness", self.fx_brightness, -0.5, 0.5, fmt="{:.2f}")
        add_fx_slider("Contrast", self.fx_contrast, 0.5, 1.5, fmt="{:.2f}")
        add_fx_slider("Saturation", self.fx_saturation, 0.0, 2.0, fmt="{:.2f}")
        add_fx_slider("Hue (deg)", self.fx_hue, -45.0, 45.0, fmt="{:.0f}")
        add_fx_slider("Blur", self.fx_blur, 0.0, 6.0, fmt="{:.2f}")
        add_fx_slider("Sharpen", self.fx_sharpen, 0.0, 2.0, fmt="{:.2f}")

        reset_fx = QPushButton("Reset Effects")
        reset_fx.clicked.connect(self._reset_fx)
        eff_content_layout.addWidget(reset_fx)
        eff_content_layout.addStretch(1)
        eff_layout.addWidget(eff_scroll, 1)
        self.left_stack.addWidget(self.effects_panel)

        left_layout.addWidget(self.left_stack, 1)

        # Sidebar toggle handle (left edge)
        self._sidebar_toggle_btn = QPushButton(">", self)
        self._sidebar_toggle_btn.setFixedSize(16, 74)
        self._sidebar_toggle_btn.setStyleSheet(
            "QPushButton{background-color:#3a3f46;color:#e6e6e6;border-radius:8px;}"
            "QPushButton:hover{background-color:#4a515a;}"
        )
        self._sidebar_toggle_btn.clicked.connect(self._toggle_sidebar)

        # Right container
        right = QFrame(self)
        right.setObjectName("panel")
        self.right_frame = right
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        # Vertical splitter (center + timeline)
        self._paned = QSplitter(Qt.Vertical, right)
        self._paned.setHandleWidth(6)
        right_layout.addWidget(self._paned, 1)

        center = QFrame(self._paned)
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(12, 12, 12, 12)
        center_layout.setSpacing(10)

        toolbar = QWidget(center)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(8)

        icon_px = 20
        self._icon_play = self._load_icon("play.png", (icon_px, icon_px), pack="video_editor") or self._load_icon("play.png", (icon_px, icon_px))
        self._icon_pause = self._load_icon("pause.png", (icon_px, icon_px))
        self._icon_stop = self._load_icon("stop.png", (icon_px, icon_px), pack="video_editor") or self._load_icon("delete.png", (icon_px, icon_px))
        self._icon_open = self._load_icon("folder.png", (icon_px, icon_px))
        self._icon_rewind = self._load_icon("rewind.png", (icon_px, icon_px), pack="video_editor")
        self._icon_forward = self._load_icon("foward.png", (icon_px, icon_px), pack="video_editor")

        def icon_button(pix, fallback, width=44):
            btn = QPushButton("" if pix else fallback)
            btn.setFixedSize(width, 34)
            if pix:
                btn.setIcon(QIcon(pix))
                btn.setIconSize(QSize(icon_px, icon_px))
            return btn

        self.play_btn = icon_button(self._icon_play, "▶")
        self.play_btn.clicked.connect(self._toggle_preview_playback)
        self.stop_btn = icon_button(self._icon_stop, "■")
        self.stop_btn.clicked.connect(self._stop_preview_playback)
        self.stop_btn.setStyleSheet(f"QPushButton{{background-color:{THEME['btn']};}}")
        self.open_btn = icon_button(self._icon_open, "Open", width=80 if not self._icon_open else 44)
        self.open_btn.clicked.connect(self._play_external)
        self.step_back_btn = QPushButton("◀ 1f")
        self.step_back_btn.setFixedWidth(60)
        self.step_back_btn.clicked.connect(lambda: self._step_frame(-1))
        self.step_fwd_btn = QPushButton("1f ▶")
        self.step_fwd_btn.setFixedWidth(60)
        self.step_fwd_btn.clicked.connect(lambda: self._step_frame(1))
        self.fps_info = QLabel("FPS: ?")
        self.fps_info.setStyleSheet(f"color:{THEME['text_muted']};")
        self.render_summary = QLabel("")
        self.render_summary.setStyleSheet(f"color:{THEME['text_muted']};")

        self.preview_quality_var = StringVar(value="Fast")
        self.preview_quality_menu = QComboBox()
        self.preview_quality_menu.addItems(["Fast", "Quality"])
        self.preview_quality_menu.setFixedWidth(110)
        bind_combo(self.preview_quality_var, self.preview_quality_menu)

        toolbar_layout.addWidget(self.play_btn)
        toolbar_layout.addWidget(self.stop_btn)
        toolbar_layout.addWidget(self.open_btn)
        toolbar_layout.addWidget(self.step_back_btn)
        toolbar_layout.addWidget(self.step_fwd_btn)
        toolbar_layout.addWidget(self.fps_info)
        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(self.render_summary)
        toolbar_layout.addWidget(self.preview_quality_menu)
        center_layout.addWidget(toolbar)

        self.preview = QFrame(center)
        self.preview.setObjectName("panel")
        preview_layout = QVBoxLayout(self.preview)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_stack = QStackedWidget(self.preview)
        self.preview_label = QLabel("No media selected")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet(f"color:{THEME['text_muted']};")
        self.preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_stack.addWidget(self.preview_label)
        if QVideoWidget is not None and QMediaPlayer is not None and QAudioOutput is not None:
            self._video_widget = QVideoWidget(self.preview)
            self._video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.preview_stack.addWidget(self._video_widget)
            self._media_player = QMediaPlayer(self)
            self._audio_output = QAudioOutput(self)
            self._audio_output.setVolume(1.0)
            self._media_player.setAudioOutput(self._audio_output)
            self._media_player.setVideoOutput(self._video_widget)
            self._media_player.positionChanged.connect(self._on_player_position)
            self._media_player.mediaStatusChanged.connect(self._on_player_status)
            try:
                self._media_player.errorOccurred.connect(self._on_player_error)
            except Exception:
                pass
            try:
                self._media_player.durationChanged.connect(self._on_player_duration)
            except Exception:
                pass
        self.preview_stack.setCurrentWidget(self.preview_label)
        preview_layout.addWidget(self.preview_stack, 1)
        center_layout.addWidget(self.preview, 1)

        scrub = QWidget(center)
        scrub_layout = QGridLayout(scrub)
        scrub_layout.setContentsMargins(0, 0, 0, 0)
        scrub_layout.setHorizontalSpacing(10)
        scrub_layout.setVerticalSpacing(6)
        self.time_label = QLabel("00:00:00")
        self.time_label.setStyleSheet(f"color:{THEME['text_muted']};")
        self.dur_label = QLabel("00:00:00")
        self.dur_label.setStyleSheet(f"color:{THEME['text_muted']};")
        self.scrub_var = DoubleVar(value=0.0)
        self.scrub_slider = FloatSlider(from_=0.0, to=1.0, steps=1000)
        self.scrub_slider.valueChangedFloat.connect(self._on_scrub)
        bind_float_slider(self.scrub_var, self.scrub_slider)
        scrub_layout.addWidget(self.time_label, 0, 0, alignment=Qt.AlignLeft)
        scrub_layout.addWidget(self.scrub_slider, 0, 1)
        scrub_layout.addWidget(self.dur_label, 0, 2, alignment=Qt.AlignRight)

        transport = QWidget(center)
        transport_layout = QHBoxLayout(transport)
        transport_layout.setContentsMargins(0, 0, 0, 0)
        transport_layout.setSpacing(8)
        transport_layout.addStretch(1)
        self.btn_home = icon_button(self._icon_rewind, "⏮", width=42)
        self.btn_home.clicked.connect(lambda: self._seek_seconds(0.0, absolute=True))
        self.btn_back = QPushButton("5s")
        self.btn_back.setFixedWidth(70)
        if self._icon_rewind:
            self.btn_back.setIcon(QIcon(self._icon_rewind))
            self.btn_back.setIconSize(QSize(icon_px, icon_px))
        self.btn_back.clicked.connect(lambda: self._seek_seconds(-5.0))
        self.btn_play2 = icon_button(self._icon_play, "▶", width=42)
        self.btn_play2.clicked.connect(self._toggle_preview_playback)
        self.btn_stop2 = icon_button(self._icon_stop, "■", width=42)
        self.btn_stop2.setStyleSheet(f"QPushButton{{background-color:{THEME['btn']};}}")
        self.btn_stop2.clicked.connect(self._stop_preview_playback)
        self.btn_fwd = QPushButton("5s\u00A0")
        self.btn_fwd.setFixedWidth(70)
        if self._icon_forward:
            self.btn_fwd.setIcon(QIcon(self._icon_forward))
            self.btn_fwd.setIconSize(QSize(icon_px, icon_px))
        self.btn_fwd.setLayoutDirection(Qt.RightToLeft)
        self.btn_fwd.clicked.connect(lambda: self._seek_seconds(5.0))
        base_height = self.btn_home.sizeHint().height()
        self.btn_back.setFixedHeight(base_height)
        self.btn_fwd.setFixedHeight(base_height)
        self.btn_end = icon_button(self._icon_forward, "⏭", width=42)
        self.btn_end.clicked.connect(lambda: self._seek_seconds(0.0, absolute=True, to_end=True))

        for b in (self.btn_home, self.btn_back, self.btn_play2, self.btn_stop2, self.btn_fwd, self.btn_end):
            transport_layout.addWidget(b)
        transport_layout.addStretch(1)

        scrub_layout.addWidget(transport, 1, 0, 1, 3)
        self.range_label = QLabel("")
        self.range_label.setStyleSheet(f"color:{THEME['text_muted']};")
        self.range_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._tip_btn = QPushButton("i")
        self._tip_btn.setFixedSize(20, 20)
        self._tip_btn.setCursor(Qt.PointingHandCursor)
        self._tip_btn.setStyleSheet(
            f"QPushButton{{background-color:{THEME['btn']};color:{THEME['text']};border-radius:10px;font-weight:bold;}}"
            f"QPushButton:hover{{background-color:{THEME['btn_hover']};}}"
        )
        self._tip_btn.enterEvent = lambda _e: self._show_tooltip(self._tip_btn, self._tip_text or "")
        self._tip_btn.leaveEvent = lambda _e: self._hide_tooltip()
        tip_row = QWidget(center)
        tip_row_layout = QHBoxLayout(tip_row)
        tip_row_layout.setContentsMargins(0, 0, 0, 0)
        tip_row_layout.setSpacing(6)
        tip_row_layout.addWidget(self.range_label, 1)
        tip_row_layout.addWidget(self._tip_btn, 0, Qt.AlignRight)
        scrub_layout.addWidget(tip_row, 2, 0, 1, 3)
        center_layout.addWidget(scrub)

        # Timeline container
        timeline = QFrame(self._paned)
        timeline_layout = QVBoxLayout(timeline)
        timeline_layout.setContentsMargins(12, 12, 12, 12)
        timeline_layout.setSpacing(8)

        header = QWidget(timeline)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)

        leftbar = QWidget(header)
        leftbar_layout = QVBoxLayout(leftbar)
        leftbar_layout.setContentsMargins(0, 0, 0, 0)
        leftbar_layout.setSpacing(6)
        leftbar_top = QWidget(leftbar)
        leftbar_top_layout = QHBoxLayout(leftbar_top)
        leftbar_top_layout.setContentsMargins(0, 0, 0, 0)
        leftbar_top_layout.setSpacing(6)
        leftbar_top_layout.addWidget(QLabel("Timeline"))

        self.include_audio_var = BooleanVar(value=True)
        include_audio_cb = QCheckBox("Include audio")
        bind_checkbox(self.include_audio_var, include_audio_cb)
        leftbar_top_layout.addWidget(include_audio_cb)
        self.use_clip_audio_var = BooleanVar(value=True)
        use_clip_cb = QCheckBox("Use clip audio")
        bind_checkbox(self.use_clip_audio_var, use_clip_cb)
        leftbar_top_layout.addWidget(use_clip_cb)

        self.snap_var = BooleanVar(value=True)
        snap_cb = QCheckBox("Snap")
        bind_checkbox(self.snap_var, snap_cb)
        leftbar_top_layout.addWidget(snap_cb)
        self.snap_step_var = StringVar(value="0.1s")
        snap_menu = QComboBox()
        snap_menu.addItems(["0.1s", "0.25s", "0.5s", "1s"])
        snap_menu.setFixedWidth(80)
        bind_combo(self.snap_step_var, snap_menu)
        leftbar_top_layout.addWidget(snap_menu)

        self.ripple_var = BooleanVar(value=True)
        ripple_cb = QCheckBox("Ripple")
        bind_checkbox(self.ripple_var, ripple_cb)
        leftbar_top_layout.addWidget(ripple_cb)

        self.image_dur_var = StringVar(value="3.0")
        image_dur_edit = QLineEdit()
        image_dur_edit.setFixedWidth(70)
        image_dur_edit.setPlaceholderText("Img s")
        bind_line_edit(self.image_dur_var, image_dur_edit)
        leftbar_top_layout.addWidget(image_dur_edit)

        self.view_toggle_btn = QPushButton("View v")
        self.view_toggle_btn.setFixedWidth(70)
        self.view_toggle_btn.clicked.connect(self._toggle_view_controls)
        leftbar_top_layout.addWidget(self.view_toggle_btn)

        leftbar_layout.addWidget(leftbar_top)

        self.view_controls_frame = QWidget(leftbar)
        view_controls_layout = QHBoxLayout(self.view_controls_frame)
        view_controls_layout.setContentsMargins(0, 0, 0, 0)
        view_controls_layout.setSpacing(8)

        view_controls_layout.addWidget(QLabel("Zoom"))
        self.tl_zoom_var = DoubleVar(value=1.0)
        self.tl_zoom_slider = FloatSlider(from_=1.0, to=10.0, steps=18)
        self.tl_zoom_slider.setFixedWidth(160)
        self.tl_zoom_slider.valueChangedFloat.connect(self._on_tl_zoom)
        bind_float_slider(self.tl_zoom_var, self.tl_zoom_slider)
        self.tl_zoom_label = QLabel("1.0x")
        self.tl_zoom_label.setStyleSheet(f"color:{THEME['text_muted']};")
        view_controls_layout.addWidget(self.tl_zoom_slider)
        view_controls_layout.addWidget(self.tl_zoom_label)

        view_controls_layout.addWidget(QLabel("Pan"))
        self.tl_pan_var = DoubleVar(value=0.0)
        self.tl_pan_slider = FloatSlider(from_=0.0, to=1.0, steps=100)
        self.tl_pan_slider.setFixedWidth(160)
        self.tl_pan_slider.valueChangedFloat.connect(self._on_tl_pan)
        bind_float_slider(self.tl_pan_var, self.tl_pan_slider)
        self.tl_pan_label = QLabel("0%")
        self.tl_pan_label.setStyleSheet(f"color:{THEME['text_muted']};")
        view_controls_layout.addWidget(self.tl_pan_slider)
        view_controls_layout.addWidget(self.tl_pan_label)

        self.view_controls_visible = BooleanVar(value=False)
        self.view_controls_frame.setVisible(False)
        leftbar_layout.addWidget(self.view_controls_frame)

        header_layout.addWidget(leftbar, 1)

        actions = QWidget(header)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(6)
        icon_add = self._load_icon("add-media.png", (18, 18), pack="video_editor") or self._load_icon("add.png", (18, 18))
        icon_audio = self._load_icon("audio-file.png", (18, 18), pack="video_editor")
        icon_img = self._load_icon("image-upload.png", (18, 18), pack="video_editor")
        icon_split = self._load_icon("split-video.png", (18, 18), pack="video_editor")
        icon_cut = self._load_icon("video-trimming.png", (18, 18), pack="video_editor")
        icon_del = self._load_icon("delete.png", (18, 18))

        def icon_btn(img, fallback_text: str, hint: str, cmd):
            b = QPushButton("" if img else fallback_text)
            b.setFixedSize(44, 34)
            if img:
                b.setIcon(QIcon(img))
                b.setIconSize(QSize(18, 18))
            b.clicked.connect(cmd)
            b.enterEvent = lambda _e: self._set_toast(hint, ms=1200)
            b.leaveEvent = lambda _e: self._update_range_label()
            return b

        for btn in (
            icon_btn(icon_add, "+C", "Add selected media as clip", self._timeline_add_selected),
            icon_btn(icon_audio, "+A", "Add an audio file to timeline", self._audio_add_clip),
            icon_btn(icon_img, "Img", "Build slideshow from images", self._slideshow_add_images),
            icon_btn(icon_split, "S", "Split selected clip at playhead", self._timeline_split_selected),
            icon_btn(icon_cut, "Cut", "Cut out selected range", self._timeline_cut_out_range),
            icon_btn(icon_del, "X", "Remove selected clip", self._timeline_remove_selected),
        ):
            actions_layout.addWidget(btn)

        self.more_action_var = StringVar(value="More v")
        self.more_action_menu = QComboBox()
        self.more_action_menu.addItems(["More v", "Add Track", "Clear Range", "Clear All"])
        self.more_action_menu.setFixedWidth(120)
        bind_combo(self.more_action_var, self.more_action_menu)
        self.more_action_menu.currentTextChanged.connect(self._on_more_action)
        actions_layout.addWidget(self.more_action_menu)
        header_layout.addWidget(actions, 0)

        timeline_layout.addWidget(header)

        # Properties bar
        props_bar = QFrame(timeline)
        props_bar.setObjectName("panel")
        props_layout = QHBoxLayout(props_bar)
        props_layout.setContentsMargins(12, 8, 12, 8)
        props_layout.setSpacing(10)
        self.props_mode = StringVar(value="Clip")
        self.props_tabs = SegmentedButton(values=["Clip", "Audio"], variable=self.props_mode, parent=props_bar)
        self.props_tabs.valueChanged.connect(self._switch_props_mode)
        props_layout.addWidget(self.props_tabs)

        self.props_stack = QStackedWidget(props_bar)
        props_layout.addWidget(self.props_stack, 1)

        self.start_var = StringVar(value="")
        self.end_var = StringVar(value="")
        self.clip_props_frame = QWidget(props_bar)
        clip_layout = QGridLayout(self.clip_props_frame)
        clip_layout.setContentsMargins(0, 0, 0, 0)
        clip_layout.setSpacing(8)
        clip_layout.addWidget(QLabel("Selected clip"), 0, 0)
        start_edit = QLineEdit()
        start_edit.setPlaceholderText("In")
        bind_line_edit(self.start_var, start_edit)
        clip_layout.addWidget(start_edit, 0, 1)
        end_edit = QLineEdit()
        end_edit.setPlaceholderText("Out / Dur")
        bind_line_edit(self.end_var, end_edit)
        clip_layout.addWidget(end_edit, 0, 2)
        btn_set_in = QPushButton("Set In")
        btn_set_in.setFixedWidth(74)
        btn_set_in.clicked.connect(self._set_in_from_scrub)
        clip_layout.addWidget(btn_set_in, 0, 3)
        btn_set_out = QPushButton("Set Out")
        btn_set_out.setFixedWidth(74)
        btn_set_out.clicked.connect(self._set_out_from_scrub)
        clip_layout.addWidget(btn_set_out, 0, 4)
        btn_apply = QPushButton("Apply")
        btn_apply.setFixedWidth(74)
        btn_apply.clicked.connect(self._apply_selected_properties)
        clip_layout.addWidget(btn_apply, 0, 5)
        self.props_stack.addWidget(self.clip_props_frame)

        self.audio_pos_var = StringVar(value="0")
        self.audio_in_var = StringVar(value="0")
        self.audio_out_var = StringVar(value="")
        self.audio_vol_var = StringVar(value="0")
        self.audio_fade_in_var = StringVar(value="")
        self.audio_fade_out_var = StringVar(value="")

        self.audio_props_frame = QWidget(props_bar)
        audio_layout = QGridLayout(self.audio_props_frame)
        audio_layout.setContentsMargins(0, 0, 0, 0)
        audio_layout.setSpacing(8)
        audio_layout.addWidget(QLabel("Audio lane"), 0, 0)
        self.audio_lane_var = StringVar(value="1")
        self.audio_lane_menu = QComboBox()
        self.audio_lane_menu.addItems(["1"])
        self.audio_lane_menu.setFixedWidth(70)
        bind_combo(self.audio_lane_var, self.audio_lane_menu)
        audio_layout.addWidget(self.audio_lane_menu, 0, 1)

        def make_audio_edit(var, placeholder, width=90):
            edit = QLineEdit()
            edit.setFixedWidth(width)
            edit.setPlaceholderText(placeholder)
            bind_line_edit(var, edit)
            return edit

        audio_layout.addWidget(make_audio_edit(self.audio_pos_var, "Pos"), 0, 2)
        audio_layout.addWidget(make_audio_edit(self.audio_in_var, "In"), 0, 3)
        audio_layout.addWidget(make_audio_edit(self.audio_out_var, "Out"), 0, 4)
        audio_layout.addWidget(make_audio_edit(self.audio_vol_var, "Gain dB"), 0, 5)
        audio_layout.addWidget(make_audio_edit(self.audio_fade_in_var, "Fade in (s)"), 0, 6)
        audio_layout.addWidget(make_audio_edit(self.audio_fade_out_var, "Fade out (s)"), 0, 7)
        audio_apply = QPushButton("Apply Audio")
        audio_apply.setFixedWidth(110)
        audio_apply.clicked.connect(self._apply_audio_properties)
        audio_layout.addWidget(audio_apply, 0, 8)
        self.props_stack.addWidget(self.audio_props_frame)
        self.props_stack.setCurrentWidget(self.clip_props_frame)
        timeline_layout.addWidget(props_bar)

        # Timeline panes
        self._timeline_panes = QSplitter(Qt.Vertical, timeline)
        self._timeline_panes.setHandleWidth(6)
        timeline_layout.addWidget(self._timeline_panes, 1)

        self._tl_canvas_frame = QFrame(self._timeline_panes)
        canvas_layout = QVBoxLayout(self._tl_canvas_frame)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        self.timeline_canvas = TimelineCanvas(self._tl_canvas_frame, height=190)
        self.timeline_canvas.on_configure = lambda _e: self._redraw_timeline()
        self.timeline_canvas.on_click = self._on_timeline_click
        self.timeline_canvas.on_drag = self._on_timeline_drag
        self.timeline_canvas.on_release = self._on_timeline_up
        self.timeline_canvas.on_double = self._on_timeline_double_click
        self.timeline_canvas.on_drag_enter = self._on_timeline_drag_enter
        self.timeline_canvas.on_drag_move = self._on_timeline_drag_move
        self.timeline_canvas.on_drag_leave = self._on_timeline_drag_leave
        self.timeline_canvas.on_drop = self._on_timeline_drop
        canvas_layout.addWidget(self.timeline_canvas)

        self._tl_list_frame = QFrame(self._timeline_panes)
        list_layout = QVBoxLayout(self._tl_list_frame)
        list_layout.setContentsMargins(0, 0, 0, 0)
        self.timeline_list = ScrollAreaFrame(self._tl_list_frame)
        self.timeline_list.on_drag_enter = self._on_timeline_drag_enter
        self.timeline_list.on_drag_move = self._on_timeline_drag_move
        self.timeline_list.on_drag_leave = self._on_timeline_drag_leave
        self.timeline_list.on_drop = self._on_timeline_drop
        list_layout.addWidget(self.timeline_list)

        self._paned.addWidget(center)
        self._paned.addWidget(timeline)
        self._paned.setStretchFactor(0, 2)
        self._paned.setStretchFactor(1, 1)

        # Render settings (bottom bar)
        bottom = QFrame(right)
        bottom.setObjectName("panel")
        self.bottom_frame = bottom
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(12, 10, 12, 10)
        bottom_layout.setSpacing(6)

        header_row = QWidget(bottom)
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        self.render_expanded = BooleanVar(value=False)
        self.adv_btn = QPushButton("Advanced >")
        self.adv_btn.setFixedWidth(110)
        self.adv_btn.clicked.connect(self._toggle_render_settings)
        header_layout.addWidget(self.adv_btn)

        self.out_name = StringVar(value="Edited_Video")
        out_name_edit = QLineEdit()
        out_name_edit.setPlaceholderText("Output name (no ext)")
        bind_line_edit(self.out_name, out_name_edit)
        header_layout.addWidget(out_name_edit, 1)
        browse_btn = QPushButton("Browse...")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._pick_output_folder)
        header_layout.addWidget(browse_btn)
        bottom_layout.addWidget(header_row)

        self.out_folder = Path.home()
        self.out_path_label = QLabel("")
        self.out_path_label.setStyleSheet(f"color:{THEME['text_muted']};")
        bottom_layout.addWidget(self.out_path_label)

        self.render_body = QWidget(bottom)
        render_body_layout = QGridLayout(self.render_body)
        render_body_layout.setContentsMargins(0, 0, 0, 0)
        render_body_layout.setSpacing(8)

        self.format_var = StringVar(value="mp4")
        fmt_menu = QComboBox()
        fmt_menu.addItems(["mp4", "mkv", "mov", "webm"])
        fmt_menu.setFixedWidth(90)
        bind_combo(self.format_var, fmt_menu)
        fmt_menu.currentTextChanged.connect(lambda _v: self._update_output_preview())
        render_body_layout.addWidget(fmt_menu, 0, 0)

        self.preset_var = StringVar(value="Custom")
        self._video_presets = {
            "Custom": {},
            "YouTube 1080p": {"res": "1080p", "fps": "30", "codec": "h264", "crf": "20"},
            "YouTube 4K": {"res": "4k", "fps": "60", "codec": "h265", "crf": "18"},
            "TikTok 1080p": {"res": "1080p", "fps": "30", "codec": "h264", "crf": "21"},
            "Instagram Reel": {"res": "1080p", "fps": "30", "codec": "h264", "crf": "21"},
            "Low Size": {"res": "720p", "fps": "30", "codec": "h264", "crf": "28"},
        }
        preset_menu = QComboBox()
        preset_menu.addItems(list(self._video_presets.keys()))
        preset_menu.setFixedWidth(190)
        bind_combo(self.preset_var, preset_menu)
        preset_menu.currentTextChanged.connect(self._apply_preset)
        render_body_layout.addWidget(preset_menu, 0, 1)

        self.res_var = StringVar(value="keep")
        res_menu = QComboBox()
        res_menu.addItems(["keep", "360p", "480p", "720p", "1080p", "4k"])
        res_menu.setFixedWidth(110)
        bind_combo(self.res_var, res_menu)
        res_menu.currentTextChanged.connect(lambda _v: self._update_output_preview())
        render_body_layout.addWidget(res_menu, 0, 2)

        self.fps_var = StringVar(value="keep")
        fps_menu = QComboBox()
        fps_menu.addItems(["keep", "24", "25", "30", "50", "60", "120"])
        fps_menu.setFixedWidth(90)
        bind_combo(self.fps_var, fps_menu)
        fps_menu.currentTextChanged.connect(lambda _v: self._update_output_preview())
        render_body_layout.addWidget(fps_menu, 0, 3)

        self.codec_var = StringVar(value="h264")
        codec_menu = QComboBox()
        codec_menu.addItems(["h264", "h265", "vp9", "av1"])
        codec_menu.setFixedWidth(100)
        bind_combo(self.codec_var, codec_menu)
        codec_menu.currentTextChanged.connect(lambda _v: self._update_output_preview())
        render_body_layout.addWidget(codec_menu, 0, 4)

        self.crf_var = StringVar(value="20")
        crf_edit = QLineEdit()
        crf_edit.setPlaceholderText("CRF")
        crf_edit.setFixedWidth(80)
        bind_line_edit(self.crf_var, crf_edit)
        render_body_layout.addWidget(crf_edit, 0, 5)

        self.use_gpu_var = BooleanVar(value=False)
        gpu_cb = QCheckBox("GPU")
        bind_checkbox(self.use_gpu_var, gpu_cb)
        gpu_cb.toggled.connect(lambda _v: self._update_output_preview())
        render_body_layout.addWidget(gpu_cb, 0, 6)

        self.render_body.setVisible(False)
        bottom_layout.addWidget(self.render_body)
        right_layout.addWidget(bottom)

        self._main_splitter.addWidget(left)
        self._main_splitter.addWidget(right)
        self._main_splitter.setSizes([self._sidebar_width, 1000])

        # Progress + cancel (full width)
        prog = QWidget(self)
        prog_layout = QHBoxLayout(prog)
        prog_layout.setContentsMargins(0, 0, 0, 0)
        prog_layout.setSpacing(10)
        self.progress = QProgressBar(prog)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet(f"color:{THEME['text_muted']};")
        cancel_btn = QPushButton("Cancel Render")
        cancel_btn.setFixedWidth(120)
        cancel_btn.clicked.connect(self._cancel_render)
        prog_layout.addWidget(self.progress, 1)
        prog_layout.addWidget(self.progress_label)
        prog_layout.addWidget(cancel_btn)
        root.addWidget(prog, 2, 0, 1, 2)

        self._position_sidebar_toggle()
        try:
            QTimer.singleShot(0, self._position_sidebar_toggle)
            QTimer.singleShot(180, self._position_sidebar_toggle)
            QTimer.singleShot(420, self._position_sidebar_toggle)
        except Exception:
            pass
        self._timeline_refresh()

    def _load_icon(self, filename: str, size: tuple[int, int], *, pack: str | None = None) -> QPixmap | None:
        try:
            base = Path(__file__).resolve().parent.parent / "assets" / "icons"
            if pack:
                candidates = [base / pack / filename, base / filename]
            else:
                candidates = [base / filename]
            p = None
            for cand in candidates:
                if cand.exists():
                    p = cand
                    break
            if p is None:
                return None
            key = f"{p}:{size[0]}x{size[1]}"
            if key in self._icons:
                return self._icons[key]
            pm = QPixmap(str(p))
            if pm.isNull():
                return None
            pm = pm.scaled(int(size[0]), int(size[1]), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._icons[key] = pm
            return pm
        except Exception:
            return None

    def _toggle_render_settings(self):
        expanded = bool(self.render_expanded.get())
        expanded = not expanded
        self.render_expanded.set(expanded)
        try:
            self.render_body.setVisible(expanded)
            self.adv_btn.setText("Advanced v" if expanded else "Advanced >")
        except Exception:
            pass

    def _toggle_selected(self, path: Path):
        self._selected = path
        self._timeline_selected = None
        try:
            if _is_image_suffix(Path(path)):
                self._duration = 0.0
            else:
                self._duration = float(self._probe_duration_cached(Path(path)) or 0.0)
        except Exception:
            self._duration = 0.0
        self._refresh_media_list()
        self._stop_preview_playback()
        self._load_preview_frame_async()
        self._update_output_preview()

    def _refresh_media_list(self):
        layout = self.media_list.layout
        _clear_layout(layout)
        self._media_relays = []
        try:
            layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        except Exception:
            pass

        try:
            view_w = int(self.media_list.viewport().width() or 0)
        except Exception:
            view_w = 0
        if view_w <= 0:
            try:
                view_w = int(self.media_list.width() or 0)
            except Exception:
                view_w = 0
        target_card_w = 220
        columns = 1
        if view_w > 0:
            columns = max(1, min(2, int((view_w + 12) // (target_card_w + 12))))

        # 2-column thumbnail grid
        col = 0
        rowi = 0
        total = len(self._files or [])
        for idx, p in enumerate(self._files):
            card = QFrame(self.media_list.content)
            card.setObjectName("panel")
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 8, 8, 8)
            card_layout.setSpacing(6)

            thumb = QLabel("")
            thumb.setFixedHeight(135)
            thumb.setAlignment(Qt.AlignCenter)
            thumb.setStyleSheet("background-color:#1b1e23;border-radius:6px;")
            thumb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            card_layout.addWidget(thumb)
            self._ensure_media_thumbnail(p, thumb)

            bar = QWidget(card)
            bar_layout = QHBoxLayout(bar)
            bar_layout.setContentsMargins(0, 0, 0, 0)
            bar_layout.setSpacing(6)
            name = p.name
            selected = (self._selected == p)
            btn = QPushButton("\u25b6" if selected else " ")
            btn.setFixedWidth(32)
            btn.clicked.connect(lambda _c=False, pp=p: self._toggle_selected(pp))
            name_lbl = QLabel(name)
            name_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            rot_btn = QPushButton("" if self._icon_rotate else "R")
            rot_btn.setFixedWidth(28)
            if self._icon_rotate:
                rot_btn.setIcon(QIcon(self._icon_rotate))
                rot_btn.setIconSize(QSize(14, 14))
            rot_btn.setToolTip("Rotate right (R)")
            if not _is_image_suffix(p):
                rot_btn.setEnabled(False)
                rot_btn.setToolTip("Rotation applies to images.")
            add_btn = QPushButton("+")
            add_btn.setFixedWidth(36)
            add_btn.clicked.connect(lambda _c=False, pp=p: self._add_media_to_timeline(pp, drop_time=None))
            def _rotate_click(_c=False, pp=p):
                self._toggle_selected(pp)
                self._rotate_media(pp, 90)

            rot_btn.clicked.connect(_rotate_click)
            bar_layout.addWidget(btn)
            bar_layout.addWidget(name_lbl, 1)
            bar_layout.addWidget(rot_btn)
            bar_layout.addWidget(add_btn)
            card_layout.addWidget(bar)

            # UX: click selects; double-click adds to timeline; drag onto timeline places at drop time.
            def _dbl(_e=None, pp=p):
                self._toggle_selected(pp)
                self._add_media_to_timeline(pp, drop_time=None)

            def _press(e, pp=p):
                self._toggle_selected(pp)
                self._drag_pending_path = pp
                self._drag_press_xy = (int(e.x_root), int(e.y_root))
                try:
                    self._drag_press_pixmap = thumb.pixmap()
                except Exception:
                    self._drag_press_pixmap = None

            def _motion(e, pp=p):
                if self._drag_pending_path != pp or not self._drag_press_xy:
                    return
                dx = int(e.x_root) - int(self._drag_press_xy[0])
                dy = int(e.y_root) - int(self._drag_press_xy[1])
                if (dx * dx + dy * dy) >= 64:
                    self._start_qt_drag(pp, getattr(self, "_drag_press_pixmap", None))
                    self._drag_pending_path = None
                    self._drag_press_xy = None

            def _release(e, pp=p):
                self._drag_pending_path = None
                self._drag_press_xy = None
                self._drag_press_pixmap = None

            relay = EventRelay(on_double=_dbl, on_press=_press, on_move=_motion, on_release=_release)
            for w in (card, thumb, bar, name_lbl):
                w.installEventFilter(relay)
            self._media_relays.append(relay)
            for w in (card, thumb, bar, name_lbl):
                try:
                    w.setContextMenuPolicy(Qt.CustomContextMenu)
                    w.customContextMenuRequested.connect(lambda pos, ww=w, pp=p: self._show_media_context_menu(ww, pp, pos))
                except Exception:
                    pass

            last_single = (columns > 1 and total % 2 == 1 and idx == total - 1)
            if last_single and col == 0:
                layout.addWidget(card, rowi, 0, 1, columns)
                col = 0
                rowi += 1
            else:
                layout.addWidget(card, rowi, col)
                col += 1
                if col >= columns:
                    col = 0
                    rowi += 1

        for c in range(columns):
            layout.setColumnStretch(c, 1)
        if columns == 1:
            layout.setColumnStretch(1, 0)
        if col != 0:
            rowi += 1
        layout.addItem(QSpacerItem(1, 1, QSizePolicy.Minimum, QSizePolicy.Expanding), rowi, 0, 1, max(1, columns))
        try:
            self.media_list.content.adjustSize()
        except Exception:
            pass
    def _switch_left_mode(self, _v=None):
        mode = (self.left_mode.get() or "Media").strip().lower()
        if mode == "transitions":
            self.left_header.setVisible(False)
            self.left_stack.setCurrentWidget(self.transitions_panel)
            return
        if mode == "effects":
            self.left_header.setVisible(False)
            self.left_stack.setCurrentWidget(self.effects_panel)
            return
        # media
        self.left_header.setVisible(True)
        self.left_stack.setCurrentWidget(self.media_list)

    def _on_transition_change(self, _v=None):
        try:
            d = float(self.transition_dur_var.get() or 0.0)
        except Exception:
            d = 0.0
        d = max(0.0, min(2.0, d))
        try:
            self.transition_dur_var.set(d)
        except Exception:
            pass
        try:
            self.transition_dur_label.setText(f"{d:.2f}s")
        except Exception:
            pass
        try:
            self._redraw_timeline()
        except Exception:
            pass

    def _transition_settings(self) -> tuple[str | None, float]:
        kind = (self.transition_var.get() or "None").strip()
        try:
            d = float(self.transition_dur_var.get() or 0.0)
        except Exception:
            d = 0.0
        if not kind or kind.lower() == "none" or d <= 0.01:
            return None, 0.0
        return kind, max(0.0, d)

    def _transition_ffmpeg_name(self) -> str | None:
        kind, _d = self._transition_settings()
        if not kind:
            return None
        mapping = {
            "cross dissolve": "fade",
            "dip to black": "fadeblack",
            "slide left": "slideleft",
            "wipe left": "wipeleft",
        }
        key = kind.strip().lower()
        return mapping.get(key, "fade")

    def _transition_ffmpeg_name_for(self, name: str | None) -> str | None:
        if not name:
            return None
        mapping = {
            "cross dissolve": "fade",
            "dip to black": "fadeblack",
            "slide left": "slideleft",
            "wipe left": "wipeleft",
        }
        key = str(name or "").strip().lower()
        if key in {"", "none", "clear"}:
            return None
        return mapping.get(key, "fade")

    def _transition_sequence(self) -> list[tuple[str | None, float]]:
        if len(self._timeline) < 2:
            return []
        seq: list[tuple[str | None, float]] = []
        for i in range(1, len(self._timeline)):
            item = self._timeline_transitions.get(i)
            name = None
            dur = 0.0
            if item:
                name = self._transition_ffmpeg_name_for(item.get("name"))
                try:
                    dur = float(item.get("duration") or 0.0)
                except Exception:
                    dur = 0.0
            if not name or dur <= 0.01:
                # fall back to global transition settings
                g_name = self._transition_ffmpeg_name()
                _g_kind, g_dur = self._transition_settings()
                if g_name and g_dur > 0.01:
                    name = g_name
                    dur = float(g_dur)
                else:
                    name = None
                    dur = 0.0
            seq.append((name, float(dur)))
        return seq

    def _has_active_transitions(self) -> bool:
        try:
            return any((nm and float(dur) > 0.01) for nm, dur in self._transition_sequence())
        except Exception:
            return False

    def _transition_preview_info(self, timeline_t: float):
        if len(self._timeline) < 2:
            return None
        seq = self._transition_sequence()
        if not seq:
            return None
        t = 0.0
        prev_clip = None
        prev_dur = 0.0
        for idx, clip in enumerate(self._timeline):
            dur = float(self._clip_duration_seconds(clip) or 0.0) or 0.0
            if idx > 0:
                name, td = seq[idx - 1] if (idx - 1) < len(seq) else (None, 0.0)
                if name and float(td or 0.0) > 0.01 and prev_clip is not None:
                    td = float(td)
                    start = t - td
                    end = t
                    if start <= float(timeline_t) <= end:
                        clip_a = prev_clip
                        clip_b = clip
                        clip_a_t0 = t - float(prev_dur)
                        clip_b_t0 = t
                        a_start = float(getattr(clip_a, "start_seconds", 0.0) or 0.0)
                        b_start = float(getattr(clip_b, "start_seconds", 0.0) or 0.0)
                        local_a = a_start + max(0.0, float(timeline_t) - float(clip_a_t0))
                        local_b = b_start + max(0.0, float(timeline_t) - float(start))
                        a_end = getattr(clip_a, "end_seconds", None)
                        if a_end is not None:
                            local_a = min(local_a, float(a_end))
                        b_end = getattr(clip_b, "end_seconds", None)
                        if b_end is not None:
                            local_b = min(local_b, float(b_end))
                        alpha = 0.0 if td <= 0 else (float(timeline_t) - float(start)) / float(td)
                        alpha = max(0.0, min(1.0, float(alpha)))
                        return {
                            "name": str(name),
                            "alpha": float(alpha),
                            "clip_a": clip_a,
                            "clip_b": clip_b,
                            "local_a": float(local_a),
                            "local_b": float(local_b),
                        }
            prev_clip = clip
            prev_dur = dur
            t += max(0.05, dur)
        return None

    def _fit_frame_to_box(self, im, size: tuple[int, int]):
        try:
            from PIL import Image
        except Exception:
            return im
        if im is None:
            return None
        w, h = size
        if w <= 0 or h <= 0:
            return im
        if getattr(im, "mode", "") != "RGB":
            try:
                im = im.convert("RGB")
            except Exception:
                pass
        try:
            img = im.copy()
            img.thumbnail((w, h))
        except Exception:
            img = im
        try:
            canvas = Image.new("RGB", (int(w), int(h)), (0, 0, 0))
            x = max(0, (int(w) - int(img.width)) // 2)
            y = max(0, (int(h) - int(img.height)) // 2)
            canvas.paste(img, (x, y))
            return canvas
        except Exception:
            return img

    def _blend_transition_frames(self, a_im, b_im, alpha: float, name: str):
        try:
            from PIL import Image
        except Exception:
            return a_im
        if a_im is None or b_im is None:
            return a_im or b_im
        name = str(name or "").strip().lower()
        alpha = max(0.0, min(1.0, float(alpha)))
        if name in {"fade", "cross dissolve"}:
            return Image.blend(a_im, b_im, alpha)
        if name in {"fadeblack", "dip to black"}:
            black = Image.new("RGB", a_im.size, (0, 0, 0))
            if alpha <= 0.5:
                return Image.blend(a_im, black, alpha * 2.0)
            return Image.blend(black, b_im, (alpha - 0.5) * 2.0)
        if name in {"slideleft", "slide left"}:
            w, h = a_im.size
            off = int(w * alpha)
            canvas = Image.new("RGB", (w, h), (0, 0, 0))
            canvas.paste(a_im, (-off, 0))
            canvas.paste(b_im, (w - off, 0))
            return canvas
        if name in {"wipeleft", "wipe left"}:
            w, h = a_im.size
            cut = int(w * alpha)
            canvas = Image.new("RGB", (w, h), (0, 0, 0))
            if cut > 0:
                canvas.paste(b_im.crop((w - cut, 0, w, h)), (w - cut, 0))
            if w - cut > 0:
                canvas.paste(a_im.crop((0, 0, w - cut, h)), (0, 0))
            return canvas
        return Image.blend(a_im, b_im, alpha)

    def _video_fx_cache_key(self) -> str:
        try:
            b = float(self.fx_brightness.get() or 0.0)
            c = float(self.fx_contrast.get() or 1.0)
            s = float(self.fx_saturation.get() or 1.0)
            h = float(self.fx_hue.get() or 0.0)
            blur = float(self.fx_blur.get() or 0.0)
            sharp = float(self.fx_sharpen.get() or 0.0)
        except Exception:
            return "fx0"
        return f"b{b:.2f}|c{c:.2f}|s{s:.2f}|h{h:.1f}|bl{blur:.2f}|sh{sharp:.2f}"

    def _build_video_filters(self) -> list[str]:
        filters: list[str] = []
        try:
            b = float(self.fx_brightness.get() or 0.0)
            c = float(self.fx_contrast.get() or 1.0)
            s = float(self.fx_saturation.get() or 1.0)
            h = float(self.fx_hue.get() or 0.0)
            blur = float(self.fx_blur.get() or 0.0)
            sharp = float(self.fx_sharpen.get() or 0.0)
        except Exception:
            return filters
        if abs(b) > 0.001 or abs(c - 1.0) > 0.001 or abs(s - 1.0) > 0.001:
            filters.append(f"eq=brightness={b:.3f}:contrast={c:.3f}:saturation={s:.3f}")
        if abs(h) > 0.1:
            filters.append(f"hue=h={h:.1f}")
        if sharp > 0.01:
            amt = max(0.0, min(2.0, sharp))
            filters.append(f"unsharp=7:7:{amt:.2f}:7:7:{max(0.0, amt * 0.6):.2f}")
        if blur > 0.01:
            filters.append(f"gblur=sigma={blur:.2f}")
        return filters

    def _apply_fx_to_pil(self, im):
        if im is None or ImageEnhance is None or ImageFilter is None:
            return im
        try:
            b = float(self.fx_brightness.get() or 0.0)
            c = float(self.fx_contrast.get() or 1.0)
            s = float(self.fx_saturation.get() or 1.0)
            h = float(self.fx_hue.get() or 0.0)
            blur = float(self.fx_blur.get() or 0.0)
            sharp = float(self.fx_sharpen.get() or 0.0)
        except Exception:
            return im

        try:
            if abs(b) > 0.001:
                im = ImageEnhance.Brightness(im).enhance(1.0 + float(b))
            if abs(c - 1.0) > 0.001:
                im = ImageEnhance.Contrast(im).enhance(float(c))
            if abs(s - 1.0) > 0.001:
                im = ImageEnhance.Color(im).enhance(float(s))
            if abs(h) > 0.1:
                hsv = im.convert("HSV")
                shift = int((float(h) / 360.0) * 255) % 255
                h_chan, s_chan, v_chan = hsv.split()
                h_chan = h_chan.point(lambda p: (int(p) + shift) % 255)
                im = Image.merge("HSV", (h_chan, s_chan, v_chan)).convert("RGB")
            if sharp > 0.01:
                pct = int(max(0.0, min(400.0, float(sharp) * 150.0)))
                if pct > 0:
                    im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=pct, threshold=3))
            if blur > 0.01:
                im = im.filter(ImageFilter.GaussianBlur(radius=float(blur)))
        except Exception:
            return im
        return im

    def _apply_realtime_fx(self):
        try:
            vw = self._video_widget
        except Exception:
            vw = None
        if vw is None:
            return
        try:
            b = float(self.fx_brightness.get() or 0.0)
            c = float(self.fx_contrast.get() or 1.0)
            s = float(self.fx_saturation.get() or 1.0)
            h = float(self.fx_hue.get() or 0.0)
        except Exception:
            return
        try:
            vw.setBrightness(int(max(-100, min(100, b * 100))))
            vw.setContrast(int(max(-100, min(100, (c - 1.0) * 100))))
            vw.setSaturation(int(max(-100, min(100, (s - 1.0) * 100))))
            vw.setHue(int(max(-100, min(100, (h / 90.0) * 100))))
        except Exception:
            pass
        try:
            blur = float(self.fx_blur.get() or 0.0)
        except Exception:
            blur = 0.0
        if blur <= 0.01:
            if self._video_blur_effect is not None:
                try:
                    vw.setGraphicsEffect(None)
                except Exception:
                    pass
            self._video_blur_effect = None
            return
        try:
            if self._video_blur_effect is None:
                self._video_blur_effect = QGraphicsBlurEffect(vw)
            self._video_blur_effect.setBlurRadius(float(min(20.0, blur * 4.0)))
            vw.setGraphicsEffect(self._video_blur_effect)
        except Exception:
            pass

    def _on_fx_change(self):
        try:
            self._apply_realtime_fx()
        except Exception:
            pass
        try:
            self._update_output_preview()
        except Exception:
            pass
        try:
            if not self._is_playing:
                self._load_preview_frame_async()
        except Exception:
            pass

    def _reset_fx(self):
        try:
            self.fx_brightness.set(0.0)
            self.fx_contrast.set(1.0)
            self.fx_saturation.set(1.0)
            self.fx_hue.set(0.0)
            self.fx_blur.set(0.0)
            self.fx_sharpen.set(0.0)
        except Exception:
            pass
        self._on_fx_change()

    def _apply_effect_preset(self, name: str):
        key = str(name or "").strip().lower()
        if key in {"", "reset", "none"}:
            self._reset_fx()
            return
        try:
            if key == "warm":
                self.fx_brightness.set(0.05)
                self.fx_contrast.set(1.1)
                self.fx_saturation.set(1.25)
                self.fx_hue.set(6.0)
                self.fx_blur.set(0.0)
                self.fx_sharpen.set(0.3)
            elif key == "cool":
                self.fx_brightness.set(0.02)
                self.fx_contrast.set(1.05)
                self.fx_saturation.set(1.1)
                self.fx_hue.set(-6.0)
                self.fx_blur.set(0.0)
                self.fx_sharpen.set(0.2)
            elif key == "b&w":
                self.fx_brightness.set(0.0)
                self.fx_contrast.set(1.2)
                self.fx_saturation.set(0.0)
                self.fx_hue.set(0.0)
                self.fx_blur.set(0.0)
                self.fx_sharpen.set(0.2)
            elif key == "punchy":
                self.fx_brightness.set(0.03)
                self.fx_contrast.set(1.25)
                self.fx_saturation.set(1.35)
                self.fx_hue.set(0.0)
                self.fx_blur.set(0.0)
                self.fx_sharpen.set(0.5)
            elif key == "soft":
                self.fx_brightness.set(0.04)
                self.fx_contrast.set(0.9)
                self.fx_saturation.set(1.05)
                self.fx_hue.set(0.0)
                self.fx_blur.set(0.6)
                self.fx_sharpen.set(0.0)
            else:
                return
        except Exception:
            return
        self._on_fx_change()

    def _on_splitter_moved(self, _pos, _index):
        try:
            sizes = self._main_splitter.sizes()
            if sizes:
                self._sidebar_width = int(sizes[0])
        except Exception:
            pass
        self._update_sidebar_compact()
        self._position_sidebar_toggle()

    def _on_sidebar_sash_press(self, event):
        try:
            self._sidebar_drag_x = int(getattr(event, "x_root", 0))
        except Exception:
            self._sidebar_drag_x = 0

    def _on_sidebar_sash_drag(self, event):
        if bool(getattr(self, "_sidebar_collapsed", False)):
            return
        try:
            x = int(getattr(event, "x_root", 0))
        except Exception:
            return
        dx = x - int(getattr(self, "_sidebar_drag_x", x))
        self._sidebar_drag_x = x
        w = int(getattr(self, "_sidebar_width", 420) or 420) + int(dx)
        # Prevent dragging into an unusable state (keeps header/buttons readable).
        w = max(260, min(720, w))
        self._sidebar_width = w
        try:
            if hasattr(self, "sidebar_frame"):
                try:
                    self.sidebar_frame.setFixedWidth(int(w))
                except Exception:
                    pass
        except Exception:
            pass
        self._update_sidebar_compact()
        self._position_sidebar_toggle()

    def _position_sidebar_toggle(self):
        """
        Keeps the sidebar toggle visually attached to the divider.
        - Expanded: sits centered on the draggable sash.
        - Collapsed: sits on the left edge so it's always reachable.
        """
        try:
            btn = self._sidebar_toggle_btn
        except Exception:
            return

        collapsed = bool(getattr(self, "_sidebar_collapsed", False))
        try:
            btn.setText(">" if collapsed else "<")
        except Exception:
            pass

        try:
            # Center vertically on the main splitter (below the top bar).
            btn_h = int(btn.height() or btn.sizeHint().height() or 74)
            min_y = 0
            try:
                if hasattr(self, "_top_bar") and self._top_bar is not None:
                    top = self._top_bar
                    tp = top.mapTo(self, QPoint(0, 0))
                    min_y = int(tp.y() + top.height() + 8)
            except Exception:
                min_y = 0
            try:
                splitter = self._main_splitter
                s_pos = splitter.mapTo(self, QPoint(0, 0))
                s_h = int(splitter.height() or 1)
                if s_h > 10:
                    y = int(s_pos.y() + max(0, (s_h // 2) - (btn_h // 2)))
                else:
                    raise ValueError("splitter height not ready")
            except Exception:
                h = int(self.winfo_height() or 1)
                y = max(0, (h // 2) - (btn_h // 2))
            y = max(min_y, y)
            x = 0
            if not collapsed:
                try:
                    if hasattr(self, "sidebar_frame") and self.sidebar_frame is not None:
                        s = self.sidebar_frame
                        pos = s.mapTo(self, QPoint(0, 0))
                        x = max(0, int(pos.x()) - btn.width() + 2)
                    else:
                        x = 0
                except Exception:
                    x = 0
            x = max(0, min(max(0, self.width() - btn.width()), x))
            btn.move(int(x), int(y))
        except Exception:
            pass

        try:
            btn.raise_()
        except Exception:
            pass

    def _toggle_sidebar(self):
        collapsed = bool(getattr(self, "_sidebar_collapsed", False))
        if not collapsed:
            self._sidebar_collapsed = True
            self._sidebar_restore_width = int(getattr(self, "_sidebar_width", 420) or 420)
            try:
                if hasattr(self, "sidebar_frame"):
                    self.sidebar_frame.setVisible(False)
            except Exception:
                pass
            try:
                sizes = self._main_splitter.sizes()
                total = sum(sizes) if sizes else int(self.width() or 1)
                self._main_splitter.setSizes([0, max(1, total)])
            except Exception:
                pass
            self._position_sidebar_toggle()
            return

        # restore
        self._sidebar_collapsed = False
        w = int(getattr(self, "_sidebar_restore_width", 420) or 420)
        self._sidebar_width = w
        try:
            if hasattr(self, "sidebar_frame"):
                self.sidebar_frame.setVisible(True)
        except Exception:
            pass
        try:
            sizes = self._main_splitter.sizes()
            total = sum(sizes) if sizes else int(self.width() or 1)
            right = max(1, int(total) - int(w))
            self._main_splitter.setSizes([int(w), right])
        except Exception:
            pass
        self._update_sidebar_compact()
        self._position_sidebar_toggle()

    def _update_sidebar_compact(self):
        """
        Responsive sidebar: hide verbose elements at smaller widths to avoid ugly clipping.
        """
        if bool(getattr(self, "_sidebar_collapsed", False)):
            return
        w = int(getattr(self, "_sidebar_width", 420) or 420)
        try:
            # responsive header title
            if w < 330:
                self._sidebar_title.setText("Media")
            else:
                self._sidebar_title.setText("Project Media")
        except Exception:
            pass

    def _media_rotation_for_path(self, path: Path) -> int:
        try:
            return int(self._media_rotations.get(str(path), 0)) % 360
        except Exception:
            return 0

    def _open_pil_image(self, path: Path):
        if Image is None:
            return None
        try:
            im = Image.open(path)
        except Exception:
            return None
        try:
            if ImageOps is not None:
                im = ImageOps.exif_transpose(im)
        except Exception:
            pass
        rot = self._media_rotation_for_path(path)
        if rot:
            try:
                im = im.rotate(-rot, expand=True)
            except Exception:
                pass
        return im

    def _invalidate_media_cache(self, path: Path):
        key = f"media::{str(path)}"
        with self._thumb_lock:
            self._thumb_images.pop(key, None)
        try:
            for k in list(self._preview_cache.keys()):
                if str(path) in k:
                    self._preview_cache.pop(k, None)
        except Exception:
            pass
        try:
            prefix = f"film::{path}"
            for k in list(self._filmstrip_cache.keys()):
                if str(k).startswith(prefix):
                    self._filmstrip_cache.pop(k, None)
        except Exception:
            pass

    def _rotate_media(self, path: Path, delta: int):
        if not _is_image_suffix(path):
            self._set_toast("Rotation applies to images only.")
            return
        rot = (self._media_rotation_for_path(path) + int(delta)) % 360
        if rot:
            self._media_rotations[str(path)] = rot
        else:
            self._media_rotations.pop(str(path), None)
        self._invalidate_media_cache(path)
        try:
            self._refresh_media_list()
        except Exception:
            pass
        try:
            if self._selected == path:
                self._load_preview_frame_async()
        except Exception:
            pass
        try:
            self._redraw_timeline()
        except Exception:
            pass

    def _reset_media_rotation(self, path: Path):
        self._media_rotations.pop(str(path), None)
        self._invalidate_media_cache(path)
        try:
            self._refresh_media_list()
        except Exception:
            pass
        try:
            if self._selected == path:
                self._load_preview_frame_async()
        except Exception:
            pass
        try:
            self._redraw_timeline()
        except Exception:
            pass

    def _remove_media(self, path: Path):
        try:
            self._files = [p for p in self._files if Path(p) != Path(path)]
        except Exception:
            pass
        if self._selected == path:
            self._selected = None
        try:
            self._timeline = [c for c in self._timeline if Path(c.path) != Path(path)]
        except Exception:
            pass
        try:
            self._audio_track = [c for c in self._audio_track if Path(c.path) != Path(path)]
        except Exception:
            pass
        if not self._timeline:
            self._timeline_selected = None
        else:
            self._timeline_selected = max(0, min(int(self._timeline_selected or 0), len(self._timeline) - 1))
        if not self._audio_track:
            self._audio_selected = None
        else:
            self._audio_selected = max(0, min(int(self._audio_selected or 0), len(self._audio_track) - 1))
        self._invalidate_media_cache(path)
        try:
            self._refresh_media_list()
        except Exception:
            pass
        try:
            self._timeline_refresh()
        except Exception:
            pass
        self._set_toast("Removed from Project Media.")

    def _show_media_context_menu(self, widget: QWidget, path: Path, pos: QPoint):
        try:
            menu = QMenu(widget)
            act_left = menu.addAction("Rotate Left")
            act_right = menu.addAction("Rotate Right")
            act_reset = menu.addAction("Reset Rotation")
            menu.addSeparator()
            act_remove = menu.addAction("Remove from Project")
            is_img = _is_image_suffix(path)
            act_left.setEnabled(is_img)
            act_right.setEnabled(is_img)
            act_reset.setEnabled(is_img)
            action = menu.exec(widget.mapToGlobal(pos))
            if action == act_left:
                self._rotate_media(path, -90)
            elif action == act_right:
                self._rotate_media(path, 90)
            elif action == act_reset:
                self._reset_media_rotation(path)
            elif action == act_remove:
                self._remove_media(path)
        except Exception:
            pass

    def _ensure_media_thumbnail(self, path: Path, label: QLabel):
        """
        Async thumbnail generation for the media bin.
        Uses a cached QPixmap per file key.
        """
        key = f"media::{str(path)}"
        with self._thumb_lock:
            cached = self._thumb_images.get(key)
        if cached is not None:
            try:
                label.setPixmap(cached)
                label.setText("")
                return
            except Exception:
                return

        def worker(p: Path, k: str):
            try:
                if Image is None:
                    return
                if _is_image_suffix(p):
                    im = self._open_pil_image(p)
                    if im is None:
                        raise RuntimeError("image load failed")
                else:
                    ffmpeg = get_ffmpeg_exe()
                    if not ffmpeg:
                        raise RuntimeError("ffmpeg not available")
                    import subprocess, tempfile
                    with tempfile.TemporaryDirectory(prefix="fylorra_mthumb_") as td:
                        outp = Path(td) / "thumb.jpg"
                        attempts: list[list[str]] = []
                        attempts.append(
                            [
                                str(ffmpeg),
                                "-hide_banner",
                                "-loglevel",
                                "error",
                                "-ss",
                                "1.0",
                                "-noaccurate_seek",
                                "-skip_frame",
                                "nokey",
                                "-i",
                                str(p),
                                "-an",
                                "-sn",
                                "-dn",
                                "-vf",
                                "scale=520:-2:force_original_aspect_ratio=decrease",
                                "-frames:v",
                                "1",
                                "-q:v",
                                "6",
                                str(outp),
                            ]
                        )
                        attempts.append(
                            [
                                str(ffmpeg),
                                "-hide_banner",
                                "-loglevel",
                                "error",
                                "-ss",
                                "1.0",
                                "-i",
                                str(p),
                                "-an",
                                "-sn",
                                "-dn",
                                "-vf",
                                "scale=520:-2:force_original_aspect_ratio=decrease",
                                "-frames:v",
                                "1",
                                "-q:v",
                                "6",
                                str(outp),
                            ]
                        )
                        attempts.append(
                            [
                                str(ffmpeg),
                                "-hide_banner",
                                "-loglevel",
                                "error",
                                "-ss",
                                "0.1",
                                "-i",
                                str(p),
                                "-an",
                                "-sn",
                                "-dn",
                                "-vf",
                                "scale=520:-2:force_original_aspect_ratio=decrease",
                                "-frames:v",
                                "1",
                                "-q:v",
                                "7",
                                str(outp),
                            ]
                        )
                        im = None
                        for cmd in attempts:
                            try:
                                if outp.exists():
                                    outp.unlink()
                            except Exception:
                                pass
                            subprocess.run(
                                cmd,
                                check=False,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                timeout=25,
                                **_subprocess_kwargs(),
                            )
                            if not outp.exists():
                                continue
                            try:
                                im = Image.open(outp)
                                im.load()
                                break
                            except Exception:
                                im = None
                                continue
                        if im is None:
                            raise RuntimeError("thumb extract failed")
                im = im.convert("RGB")
                im.thumbnail((260, 150))
                pil_thumb = im.copy()

                def apply():
                    try:
                        pm = _pil_to_pixmap(pil_thumb)
                        if pm is None:
                            raise RuntimeError("pixmap failed")
                        with self._thumb_lock:
                            self._thumb_images[k] = pm
                        label.setPixmap(pm)
                        label.setText("")
                    except Exception:
                        pass

                self.after(0, apply)
            except Exception:
                def apply_fallback():
                    try:
                        kind = "IMAGE" if _is_image_suffix(path) else ("AUDIO" if _is_audio_suffix(path) else "VIDEO")
                        label.setPixmap(QPixmap())
                        label.setText(kind)
                    except Exception:
                        pass

                self.after(0, apply_fallback)

        threading.Thread(target=worker, args=(Path(path), key), daemon=True).start()

    def add_files(self, paths: list[Path]):
        for p in paths:
            if p.exists() and p.is_file():
                if p not in self._files:
                    self._files.append(p)
        _dbg(f"add_files total={len(self._files)}")
        self._files.sort(key=lambda x: str(x).lower())
        if self._files and self._selected is None:
            self._selected = self._files[0]
        try:
            if self._selected and _is_image_suffix(Path(self._selected)):
                self._duration = 0.0
            elif self._selected:
                self._duration = float(self._probe_duration_cached(Path(self._selected)) or 0.0)
        except Exception:
            self._duration = 0.0
        self._refresh_media_list()
        self._stop_preview_playback()
        self._load_preview_frame_async()
        self._update_output_preview()

    def _import_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Import media",
            "",
            "Media files (*.mp4 *.mkv *.mov *.avi *.webm *.png *.jpg *.jpeg *.webp *.bmp *.gif *.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus);;"
            "Video files (*.mp4 *.mkv *.mov *.avi *.webm);;"
            "Image files (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;"
            "Audio files (*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus);;"
            "All files (*.*)",
        )
        _dbg(f"_import_files count={len(files) if files else 0}")
        if files:
            self.add_files([Path(f) for f in files])

    def _pick_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select output folder", str(self.out_folder or Path.home()))
        if folder:
            self.out_folder = Path(folder)
            self._update_output_preview()

    def _update_output_preview(self):
        if not self._selected:
            self.out_path_label.setText("")
            return
        ext = "." + self.format_var.get().strip().lower().lstrip(".")
        name = (self.out_name.get() or "Edited_Video").strip()
        safe = re.sub(r"[<>:\"/\\\\|?*]+", "_", name).strip(" ._")
        outp = self.out_folder / f"{safe}{ext}"
        self.out_path_label.setText(f"Output: {outp}")
        try:
            res = self.res_var.get()
            fps = self.fps_var.get()
            codec = self.codec_var.get()
            fmt = self.format_var.get().upper()
            gpu = " | GPU" if self.use_gpu_var.get() else ""
            tl = f" | {len(self._timeline)} clips" if self._timeline else ""
            self.render_summary.setText(f"{res} | {fps} FPS | {fmt} | {codec.upper()}{gpu}{tl}")
        except Exception:
            pass

    def _snap_seconds(self, seconds: float) -> float:
        if not bool(getattr(self, "snap_var", None) and self.snap_var.get()):
            return float(seconds)
        step_txt = (getattr(self, "snap_step_var", None) and self.snap_step_var.get()) or "0.1s"
        step = 0.1
        try:
            step = float(step_txt.replace("s", "").strip())
        except Exception:
            step = 0.1
        if step <= 0:
            return float(seconds)
        return round(float(seconds) / step) * step

    def _probe_duration_cached(self, path: Path) -> float | None:
        key = str(path)
        if key in self._dur_cache:
            return self._dur_cache[key]
        import subprocess
        ffprobe = get_ffprobe_exe()
        if ffprobe:
            try:
                proc = subprocess.run(
                    [str(ffprobe), "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                    **_subprocess_kwargs(),
                )
                out = (proc.stdout or "").strip()
                if out:
                    dur = max(0.0, float(out))
                    if dur > 0.1:
                        self._dur_cache[key] = dur
                        return dur
            except Exception:
                pass

        # Fallback: parse duration from `ffmpeg -i` stderr (works even without ffprobe).
        ffmpeg = get_ffmpeg_exe()
        if not ffmpeg:
            return None
        try:
            proc = subprocess.run(
                [str(ffmpeg), "-hide_banner", "-i", str(path)],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=12,
                **_subprocess_kwargs(),
            )
            txt = (proc.stderr or b"").decode("utf-8", errors="replace")
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", txt)
            if m:
                dur = float(m.group(1)) * 3600 + float(m.group(2)) * 60 + float(m.group(3))
                if dur > 0.1:
                    self._dur_cache[key] = dur
                    return dur
        except Exception:
            pass
        return None

    def _clip_duration_seconds(self, clip: TimelineClip) -> float:
        p = Path(clip.path)
        kind = (getattr(clip, "kind", "video") or "video").lower()
        if kind == "image" or _is_image_suffix(p):
            d = float(getattr(clip, "duration_seconds", 0.0) or 0.0)
            return d if d > 0 else 3.0
        if kind == "audio":
            dur_total = self._probe_duration_cached(p) or 0.0
            s = float(getattr(clip, "start_seconds", 0.0) or 0.0)
            e = getattr(clip, "end_seconds", None)
            if e is None and dur_total > 0:
                e = dur_total
            if e is None:
                e = s + 5.0
            return max(0.1, float(e) - s)
        # video
        dur_total = self._probe_duration_cached(p) or 0.0
        s = float(getattr(clip, "start_seconds", 0.0) or 0.0)
        e = getattr(clip, "end_seconds", None)
        if e is None and dur_total > 0:
            e = dur_total
        if e is None:
            e = s + max(0.1, dur_total or 5.0)
        return max(0.1, float(e) - s)

    def _video_clip_t0(self, idx: int) -> float:
        t = 0.0
        for i in range(max(0, idx)):
            t += self._clip_duration_seconds(self._timeline[i])
        return t

    def _ripple_shift_audio(self, after_time: float, delta: float):
        if not self._audio_track or abs(delta) < 1e-6:
            return
        for i, c in enumerate(list(self._audio_track)):
            pos = float(getattr(c, "timeline_start_seconds", 0.0) or 0.0)
            if pos + 1e-6 < float(after_time):
                continue
            new_pos = max(0.0, pos + float(delta))
            self._audio_track[i] = TimelineClip(
                path=Path(c.path),
                kind="audio",
                start_seconds=c.start_seconds,
                end_seconds=c.end_seconds,
                timeline_start_seconds=new_pos,
                volume_db=getattr(c, "volume_db", None),
                fade_in_seconds=getattr(c, "fade_in_seconds", None),
                fade_out_seconds=getattr(c, "fade_out_seconds", None),
            )

    def _apply_preset(self, name: str):
        p = self._video_presets.get(name or "Custom", {})
        if not p:
            return
        try:
            self.res_var.set(p.get("res", self.res_var.get()))
            self.fps_var.set(p.get("fps", self.fps_var.get()))
            self.codec_var.set(p.get("codec", self.codec_var.get()))
            self.crf_var.set(p.get("crf", self.crf_var.get()))
            self.use_gpu_var.set(bool(p.get("gpu", False)))
        except Exception:
            pass
        self._update_output_preview()

    def _probe_video_fps(self, path: Path) -> float | None:
        ffprobe = get_ffprobe_exe()
        if not ffprobe:
            return None
        import subprocess
        try:
            proc = subprocess.run(
                [str(ffprobe), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=avg_frame_rate,r_frame_rate", "-of", "default=nw=1:nk=1", str(path)],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=8,
                **_subprocess_kwargs(),
            )
            out = (proc.stdout or "").strip().splitlines()
            for v in out:
                v = v.strip()
                if not v:
                    continue
                if "/" in v:
                    a, b = v.split("/", 1)
                    try:
                        return float(a) / float(b)
                    except Exception:
                        continue
                try:
                    return float(v)
                except Exception:
                    continue
        except Exception:
            return None
        return None

    def _step_frame(self, direction: int):
        self._stop_preview_playback()
        fps = float(getattr(self, "_fps", 0.0) or 0.0)
        if fps <= 0:
            fps = 30.0
        dt = 1.0 / fps
        t = float(self._scrub_time_seconds() or 0.0)
        t2 = t + float(direction) * float(dt)
        self._set_scrub_time_seconds(t2)

    def _play_external(self):
        src = self._preview_source_at_time(self._scrub_time_seconds())
        if not src:
            return
        p, t = src
        ffplay = get_ffplay_exe()
        if ffplay:
            import subprocess
            try:
                subprocess.Popen(
                    [str(ffplay), "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}", str(p)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    **_subprocess_kwargs(),
                )
                return
            except Exception:
                pass
        try:
            import os
            os.startfile(str(p))  # type: ignore[attr-defined]
        except Exception:
            QMessageBox.information(self, "Play", "Could not launch an external player on this system.")

    def _has_qt_player(self) -> bool:
        return bool(self._media_player is not None and self._video_widget is not None)

    def _show_preview_label(self):
        try:
            if self.preview_stack and self.preview_label:
                self.preview_stack.setCurrentWidget(self.preview_label)
        except Exception:
            pass

    def _show_preview_video(self):
        try:
            if self.preview_stack and self._video_widget:
                self.preview_stack.setCurrentWidget(self._video_widget)
        except Exception:
            pass

    def _timeline_clip_at_time(self, timeline_t: float):
        timeline_t = max(0.0, float(timeline_t or 0.0))
        t = 0.0
        for idx, c in enumerate(self._timeline):
            p = Path(c.path)
            is_img = (getattr(c, 'kind', 'video') or '').lower() == 'image' or _is_image_suffix(p)
            if is_img:
                dur = float(getattr(c, 'duration_seconds', 0.0) or 0.0) or 3.0
                t0 = t
                t1 = t + dur
                if t0 <= timeline_t < t1:
                    return {"clip": c, "idx": idx, "t0": t0, "t1": t1, "local_start": 0.0, "local_end": 0.0, "is_image": True}
                t += dur
                continue
            dur_total = float(self._probe_duration_cached(p) or 0.0)
            s0 = float(getattr(c, 'start_seconds', 0.0) or 0.0)
            e0 = getattr(c, 'end_seconds', None)
            if e0 is None and dur_total > 0:
                e0 = dur_total
            if e0 is None:
                e0 = s0 + max(0.1, dur_total or 5.0)
            clip_dur = max(0.05, float(e0) - float(s0))
            t0 = t
            t1 = t + clip_dur
            if t0 <= timeline_t < t1:
                return {"clip": c, "idx": idx, "t0": t0, "t1": t1, "local_start": s0, "local_end": float(e0), "is_image": False}
            t += clip_dur
        return None

    def _start_qt_playback(self) -> bool:
        if not self._has_qt_player():
            self._stop_qt_playback()
            return False
        self._stop_play_timer()
        self._live_transition_preview = bool(self._timeline and self._has_active_transitions())
        timeline_t = float(self._scrub_time_seconds() or 0.0)
        in_trans = self._transition_preview_info(timeline_t) is not None if self._live_transition_preview else False
        info = self._timeline_clip_at_time(timeline_t) if self._timeline else None
        if info and info.get('is_image'):
            self._stop_qt_playback()
            return False
        if info:
            clip = info.get('clip')
            p = Path(clip.path)
            local_start = float(info.get('local_start', 0.0) or 0.0)
            local_end = float(info.get('local_end', 0.0) or 0.0)
            self._player_mode = 'timeline'
            self._player_clip_idx = int(info.get('idx') or 0)
            clip_start_t = float(info.get('t0') or 0.0)
            offset = max(0.0, float(timeline_t) - clip_start_t)
            start_local = float(local_start) + float(offset)
            if local_end > 0:
                start_local = min(start_local, max(0.0, float(local_end) - 0.02))
            self._player_clip_start_t = float(timeline_t)
            self._player_clip_start_ms = int(start_local * 1000.0)
            self._player_clip_end_ms = int(local_end * 1000.0) if local_end > 0 else None
        else:
            src = self._preview_source_at_time(timeline_t)
            if not src:
                return False
            p, local_start = src
            p = Path(p)
            if _is_image_suffix(p):
                return False
            self._player_mode = 'single'
            self._player_clip_idx = None
            self._player_clip_start_t = 0.0
            self._player_clip_start_ms = int(float(local_start or 0.0) * 1000.0)
            self._player_clip_end_ms = None
        if not p.exists():
            return False
        try:
            self._media_player.stop()
            self._media_player.setSource(QUrl.fromLocalFile(str(p)))
            self._media_player.setPosition(int(self._player_clip_start_ms or 0))
            self._apply_realtime_fx()
            if in_trans:
                self._show_preview_label()
            else:
                self._show_preview_video()
            self._use_qt_player = True
            self._player_src_path = str(p)
            self._media_player.play()
            return True
        except Exception:
            self._use_qt_player = False
            self._show_preview_label()
            return False

    def _stop_qt_playback(self):
        try:
            if self._media_player is not None:
                self._media_player.stop()
        except Exception:
            pass
        self._use_qt_player = False
        self._live_transition_preview = False
        self._player_mode = None
        self._player_clip_idx = None
        self._player_clip_end_ms = None
        self._player_src_path = None
        self._show_preview_label()

    def _start_play_timer(self):
        try:
            if self._play_timer is None:
                self._play_timer = QTimer(self)
                self._play_timer.setInterval(120)
                self._play_timer.timeout.connect(self._play_tick)
            if not self._play_timer.isActive():
                self._play_timer.start()
        except Exception:
            pass

    def _stop_play_timer(self):
        try:
            if self._play_timer is not None and self._play_timer.isActive():
                self._play_timer.stop()
        except Exception:
            pass

    def _on_player_duration(self, dur_ms: int):
        try:
            if dur_ms and dur_ms > 0 and not self._timeline:
                self._duration = float(dur_ms) / 1000.0
        except Exception:
            pass

    def _on_player_status(self, status):
        try:
            if not self._use_qt_player:
                return
        except Exception:
            return
        try:
            end_status = getattr(QMediaPlayer, "EndOfMedia", None)
            if end_status is None:
                end_status = getattr(getattr(QMediaPlayer, "MediaStatus", object()), "EndOfMedia", None)
            if end_status is not None and int(status) == int(end_status):
                if self._player_mode == 'timeline' and self._is_playing:
                    if self._advance_timeline_playback():
                        return
                self._stop_preview_playback()
        except Exception:
            pass

    def _on_player_error(self, *args):
        try:
            _dbg(f'QMediaPlayer error: {args}')
        except Exception:
            pass
        was_playing = bool(self._is_playing)
        try:
            if self._media_player is not None:
                self._media_player.stop()
        except Exception:
            pass
        self._use_qt_player = False
        self._show_preview_label()
        if was_playing:
            self._play_last_ts = time.time()
            self._play_tick()

    def _on_player_position(self, pos_ms: int):
        if not self._is_playing or not self._use_qt_player:
            return
        if self._player_syncing:
            return
        try:
            if self._player_mode == 'timeline':
                base_ms = int(self._player_clip_start_ms or 0)
                t = self._player_clip_start_t + max(0.0, (float(pos_ms) - float(base_ms)) / 1000.0)
            else:
                t = max(0.0, float(pos_ms) / 1000.0)
            self._player_syncing = True
            try:
                self._set_scrub_time_seconds(t)
            finally:
                self._player_syncing = False
            if self._player_clip_end_ms is not None and int(pos_ms) >= int(self._player_clip_end_ms) - 30:
                if self._player_mode == 'timeline' and self._is_playing:
                    if self._advance_timeline_playback():
                        return
                self._stop_preview_playback()
        except Exception:
            pass

    def _advance_timeline_playback(self) -> bool:
        if not self._timeline or not self._is_playing:
            return False
        if self._player_mode != 'timeline':
            return False
        try:
            idx = int(self._player_clip_idx or 0)
        except Exception:
            idx = 0
        next_idx = idx + 1
        if next_idx >= len(self._timeline):
            return False
        try:
            next_t = float(self._video_clip_t0(next_idx))
        except Exception:
            next_t = 0.0
            for i in range(next_idx):
                try:
                    next_t += float(self._clip_duration_seconds(self._timeline[i]) or 0.0)
                except Exception:
                    continue
        self._stop_qt_playback()
        self._set_scrub_time_seconds(next_t)
        if self._start_qt_playback():
            return True
        self._play_last_ts = time.time()
        self._play_tick()
        return True

    def _toggle_preview_playback(self):
        if self._is_playing:
            self._stop_preview_playback()
            return
        if self._preview_total_seconds() <= 0:
            return
        # If we're at the end, rewind before playing (common for image-only timelines).
        try:
            dur = float(self._preview_total_seconds() or 0.0)
            if dur > 0 and self._scrub_time_seconds() >= dur - 0.02:
                self._set_scrub_time_seconds(0.0)
        except Exception:
            pass
        self._is_playing = True
        try:
            if getattr(self, '_icon_pause', None):
                self.play_btn.setIcon(QIcon(self._icon_pause))
                self.play_btn.setText("")
                if hasattr(self, 'btn_play2'):
                    self.btn_play2.setIcon(QIcon(self._icon_pause))
                    self.btn_play2.setText("")
            else:
                self.play_btn.setText("Pause")
                if hasattr(self, 'btn_play2'):
                    self.btn_play2.setText("Pause")
        except Exception:
            pass
        force_frame = False
        try:
            force_frame = self._is_image_at_time(self._scrub_time_seconds()) or (self._timeline and not self._timeline_has_video())
        except Exception:
            force_frame = False
        if force_frame:
            self._stop_qt_playback()
        elif self._start_qt_playback():
            return
        self._stop_qt_playback()
        self._play_last_ts = time.time()
        self._play_tick()
        self._start_play_timer()

    def _stop_preview_playback(self):
        self._is_playing = False
        try:
            if getattr(self, '_icon_play', None):
                self.play_btn.setIcon(QIcon(self._icon_play))
                self.play_btn.setText("")
                if hasattr(self, 'btn_play2'):
                    self.btn_play2.setIcon(QIcon(self._icon_play))
                    self.btn_play2.setText("")
            else:
                self.play_btn.setText("Play")
                if hasattr(self, 'btn_play2'):
                    self.btn_play2.setText("Play")
        except Exception:
            pass
        self._stop_qt_playback()
        self._stop_play_timer()
        if self._play_after_id:
            try:
                self.after_cancel(self._play_after_id)
            except Exception:
                pass
            self._play_after_id = None
        self._play_last_ts = None

    def _play_tick(self):
        if not self._is_playing:
            return
        dur = float(self._preview_total_seconds() or 0.0)
        if dur <= 0:
            self._stop_preview_playback()
            return
        now = time.time()
        last = float(self._play_last_ts or now)
        self._play_last_ts = now
        dt = max(0.0, min(0.2, now - last))
        t = self._scrub_time_seconds() + dt
        if t >= dur:
            t = dur
            self._stop_preview_playback()
        self._set_scrub_time_seconds(t)
        if self._is_playing and not getattr(self, "_use_qt_player", False):
            if self._timeline and self._timeline_has_video() and not self._is_image_at_time(t):
                if self._start_qt_playback():
                    return
            if self._play_timer is None or not self._play_timer.isActive():
                self._start_play_timer()

    def _preview_total_seconds(self) -> float:
        if self._timeline:
            try:
                return float(self._timeline_total_seconds() or 0.0)
            except Exception:
                return 0.0
        d = float(getattr(self, "_duration", 0.0) or 0.0)
        if d <= 0 and self._selected and not _is_image_suffix(Path(self._selected)):
            try:
                d = float(self._probe_duration_cached(Path(self._selected)) or 0.0)
                self._duration = d
            except Exception:
                d = 0.0
        return float(d or 0.0)

    def _is_image_at_time(self, timeline_t: float) -> bool:
        try:
            timeline_t = max(0.0, float(timeline_t or 0.0))
        except Exception:
            timeline_t = 0.0
        if self._timeline:
            info = self._timeline_clip_at_time(timeline_t)
            return bool(info and info.get("is_image"))
        p = self._selected
        if p and _is_image_suffix(Path(p)):
            return True
        return False

    def _timeline_has_video(self) -> bool:
        for c in self._timeline:
            p = Path(c.path)
            is_img = (getattr(c, "kind", "video") or "").lower() == "image" or _is_image_suffix(p)
            if not is_img:
                return True
        return False

    def _scrub_time_seconds(self) -> float:
        dur = float(self._preview_total_seconds() or 0.0)
        if dur <= 0:
            return 0.0
        return max(0.0, min(dur, float(self.scrub_var.get() or 0.0) * dur))

    def _set_scrub_time_seconds(self, t: float):
        dur = float(self._preview_total_seconds() or 0.0)
        if dur <= 0:
            return
        t = max(0.0, min(dur, float(t)))
        self.scrub_var.set(0.0 if dur <= 0 else t / dur)
        self._on_scrub(self.scrub_var.get())
        if getattr(self, "_use_qt_player", False) and not getattr(self, "_player_syncing", False):
            self._seek_qt_player_to_time(t, autoplay=self._is_playing)

    def _seek_seconds(self, seconds: float, *, absolute: bool = False, to_end: bool = False):
        dur = float(self._preview_total_seconds() or 0.0)
        if dur <= 0:
            return
        if absolute:
            t = float(dur if to_end else seconds)
        else:
            t = self._scrub_time_seconds() + float(seconds)
        self._set_scrub_time_seconds(t)

    def _apply_prompt(self):
        raw = (self.prompt_var.get() or "").strip()
        text = raw.lower()
        if not raw:
            return

        def apply_result(r):
            if not r:
                return
            try:
                if getattr(r, "select_path", None):
                    self._select(r.select_path)
            except Exception:
                pass
            if getattr(r, "trim_start", None):
                try:
                    self.start_var.set(str(r.trim_start))
                except Exception:
                    pass
            if getattr(r, "trim_end", None):
                try:
                    self.end_var.set(str(r.trim_end))
                except Exception:
                    pass
            if getattr(r, "out_format", None):
                try:
                    self.format_var.set(str(r.out_format))
                except Exception:
                    pass
            if getattr(r, "resolution", None):
                try:
                    self.res_var.set(str(r.resolution))
                except Exception:
                    pass
            if getattr(r, "codec", None):
                try:
                    self.codec_var.set(str(r.codec))
                except Exception:
                    pass
            if getattr(r, "fps", None):
                try:
                    self.fps_var.set(str(r.fps))
                except Exception:
                    pass
            if getattr(r, "crf", None):
                try:
                    self.crf_var.set(str(r.crf))
                except Exception:
                    pass
            if getattr(r, "use_gpu", None) is True:
                try:
                    self.use_gpu_var.set(True)
                except Exception:
                    pass
            if getattr(r, "out_name", None):
                try:
                    self.out_name.set(str(r.out_name))
                except Exception:
                    pass
            self._update_output_preview()

        # Fast offline parse first.
        try:
            apply_result(heuristic_video_from_nl(list(self._files or []), raw))
        except Exception:
            pass

        # Optional AI enhancement.
        if self.ai_manager and getattr(self.ai_manager, "is_ready", False):
            def worker():
                r = ai_video_from_nl(self.ai_manager, list(self._files or []), raw)
                if r:
                    self.after(0, lambda: apply_result(r))

            try:
                threading.Thread(target=worker, daemon=True).start()
            except Exception:
                pass

    def _switch_props_mode(self, _value=None):
        mode = (self.props_mode.get() or "Clip").strip()
        if mode.lower() == "audio":
            try:
                self.props_stack.setCurrentWidget(self.audio_props_frame)
            except Exception:
                pass
            return
        try:
            self.props_stack.setCurrentWidget(self.clip_props_frame)
        except Exception:
            pass

    def _set_in_from_scrub(self):
        if self._timeline_selected is None or self._timeline_selected < 0 or self._timeline_selected >= len(self._timeline):
            return
        clip = self._timeline[int(self._timeline_selected)]
        p = Path(clip.path)
        is_img = (getattr(clip, "kind", "video") or "").lower() == "image" or _is_image_suffix(p)
        if is_img:
            return
        timeline_t = float(self._scrub_time_seconds() or 0.0)
        t0 = self._video_clip_t0(int(self._timeline_selected))
        local = float(getattr(clip, "start_seconds", 0.0) or 0.0) + max(0.0, timeline_t - float(t0))
        self.start_var.set(_fmt_time(local))

    def _set_out_from_scrub(self):
        if self._timeline_selected is None or self._timeline_selected < 0 or self._timeline_selected >= len(self._timeline):
            return
        clip = self._timeline[int(self._timeline_selected)]
        p = Path(clip.path)
        is_img = (getattr(clip, "kind", "video") or "").lower() == "image" or _is_image_suffix(p)
        if is_img:
            return
        timeline_t = float(self._scrub_time_seconds() or 0.0)
        t0 = self._video_clip_t0(int(self._timeline_selected))
        local = float(getattr(clip, "start_seconds", 0.0) or 0.0) + max(0.0, timeline_t - float(t0))
        self.end_var.set(_fmt_time(local))

    def _on_scrub(self, v):
        dur = float(self._preview_total_seconds() or 0.0)
        if dur <= 0:
            return
        t = float(v) * dur
        self.time_label.setText(_fmt_time(t))
        self.dur_label.setText(_fmt_time(dur))
        try:
            self._redraw_timeline()
        except Exception:
            pass
        self._update_range_label()
        if self._is_image_at_time(t) and getattr(self, "_use_qt_player", False):
            self._stop_qt_playback()
        if self._is_playing and not getattr(self, "_use_qt_player", False) and self._is_image_at_time(t):
            try:
                if self._preview_after_id:
                    self.after_cancel(self._preview_after_id)
                    self._preview_after_id = None
            except Exception:
                pass
            self._load_preview_frame_async()
            return
        live = bool(self._has_active_transitions())
        self._live_transition_preview = live
        if getattr(self, "_use_qt_player", False):
            if not live:
                return
            in_trans = self._transition_preview_info(t) is not None
            if not in_trans:
                self._show_preview_video()
                return
            self._show_preview_label()
        # Throttle preview extraction (cancel previous scheduled extraction).
        try:
            if self._preview_after_id:
                self.after_cancel(self._preview_after_id)
        except Exception:
            pass
        delay = 200 if self._is_playing else 120
        if live and self._is_playing:
            delay = 60
        try:
            self._preview_after_id = self.after(delay, self._load_preview_frame_async)
        except Exception:
            self._preview_after_id = None

    def _load_preview_frame_async(self):
        live = bool(self._has_active_transitions())
        self._live_transition_preview = live
        if getattr(self, "_use_qt_player", False) and not live:
            return
        try:
            self._show_preview_label()
        except Exception:
            pass
        timeline_t = float(self._scrub_time_seconds() or 0.0)
        transition = self._transition_preview_info(timeline_t) if live else None
        if transition:
            if self._preview_busy:
                return
            self._preview_busy = True

            def work_transition(info):
                try:
                    fast_preview = False
                    try:
                        fast_preview = bool((self.preview_quality_var.get() or "").strip().lower() == "fast")
                    except Exception:
                        fast_preview = True
                    if self._is_playing:
                        fast_preview = True

                    def load_frame(clip, t_local):
                        pth = Path(clip.path)
                        is_img = (getattr(clip, "kind", "video") or "").lower() == "image" or _is_image_suffix(pth)
                        if is_img:
                            im = self._open_pil_image(pth)
                            if im is None:
                                return None
                            im.thumbnail((900, 430))
                            im = self._apply_fx_to_pil(im)
                            return im
                        ffmpeg = get_ffmpeg_exe()
                        if not ffmpeg:
                            return None
                        import subprocess, tempfile
                        from PIL import Image
                        with tempfile.TemporaryDirectory(prefix="fylorra_tprev_") as td:
                            imgp = Path(td) / "frame.jpg"
                            cmd = [
                                str(ffmpeg),
                                "-hide_banner",
                                "-loglevel",
                                "error",
                                "-ss",
                                f"{float(t_local or 0.0):.3f}",
                            ]
                            if fast_preview:
                                cmd += ["-noaccurate_seek", "-skip_frame", "nokey"]
                            cmd += ["-i", str(pth), "-an", "-sn", "-dn"]
                            vf_chain = []
                            if fast_preview:
                                vf_chain.append("scale=960:-2:force_original_aspect_ratio=decrease")
                            vf_chain += self._build_video_filters()
                            if vf_chain:
                                cmd += ["-vf", ",".join(vf_chain)]
                            cmd += ["-frames:v", "1", "-q:v", "6" if fast_preview else "3", str(imgp)]
                            subprocess.run(
                                cmd,
                                check=False,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                timeout=18,
                                **_subprocess_kwargs(),
                            )
                            if imgp.exists():
                                im = Image.open(imgp)
                                im.thumbnail((900, 430))
                                return im
                        return None

                    clip_a = info.get("clip_a")
                    clip_b = info.get("clip_b")
                    im_a = load_frame(clip_a, float(info.get("local_a", 0.0) or 0.0)) if clip_a else None
                    im_b = load_frame(clip_b, float(info.get("local_b", 0.0) or 0.0)) if clip_b else None
                    if im_a is None and im_b is None:
                        raise RuntimeError("no frames")
                    target_w = int(self.preview_label.width() or 900)
                    target_h = int(self.preview_label.height() or 430)
                    im_a = self._fit_frame_to_box(im_a, (target_w, target_h)) if im_a is not None else None
                    im_b = self._fit_frame_to_box(im_b, (target_w, target_h)) if im_b is not None else None
                    im_out = self._blend_transition_frames(im_a, im_b, float(info.get("alpha", 0.0) or 0.0), str(info.get("name") or ""))
                    qimg = _pil_to_qimage(im_out)

                    def apply_img():
                        try:
                            if not self._transition_preview_info(self._scrub_time_seconds() or 0.0):
                                return
                            self._fps = 0.0
                            qual = "Fast" if fast_preview else "HQ"
                            self.fps_info.setText(f"FPS: live | {qual}")
                            pm = QPixmap.fromImage(qimg) if qimg is not None else None
                            if pm is not None:
                                self.preview_label.setPixmap(pm)
                                self.preview_label.setText("")
                            else:
                                self.preview_label.setPixmap(QPixmap())
                                self.preview_label.setText("Transition preview")
                        finally:
                            self._preview_busy = False

                    self.after(0, apply_img)
                except Exception:
                    self.after(0, lambda: setattr(self, "_preview_busy", False))

            threading.Thread(target=work_transition, args=(transition,), daemon=True).start()
            return
        if getattr(self, "_use_qt_player", False) and live:
            self._show_preview_video()
            return

        src = self._preview_source_at_time(timeline_t)
        if not src:
            return
        p, t_seek = src
        # Tiny cache (reduces repeated ffmpeg calls while scrubbing).
        try:
            cache_key = f"{Path(p)}::{int(float(t_seek or 0.0) * 10)}::{(self.preview_quality_var.get() or 'Fast').lower()}::{self._video_fx_cache_key()}"
        except Exception:
            cache_key = None
        if cache_key:
            cached = self._preview_cache.get(cache_key)
            if cached is not None:
                try:
                    self.preview_label.setPixmap(cached)
                    self.preview_label.setText("")
                except Exception:
                    pass
                return
        if self._preview_busy:
            return
        self._preview_busy = True
        t_seek = float(t_seek or 0.0)

        def work(path: Path, t_local: float):
            try:
                if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}:
                    im = self._open_pil_image(path)
                    if im is None:
                        raise RuntimeError("image load failed")
                    im.thumbnail((900, 430))
                    im = self._apply_fx_to_pil(im)
                    qimg = _pil_to_qimage(im)

                    def apply_img():
                        try:
                            self._fps = 0.0
                            self.fps_info.setText("FPS: -")
                            pm = QPixmap.fromImage(qimg) if qimg is not None else None
                            if pm is not None:
                                self.preview_label.setPixmap(pm)
                                self.preview_label.setText("")
                            else:
                                self.preview_label.setPixmap(QPixmap())
                                self.preview_label.setText(path.name)
                        finally:
                            self._preview_busy = False

                    self.after(0, apply_img)
                    return

                ffmpeg = get_ffmpeg_exe()
                if not ffmpeg:
                    self.after(0, lambda: (self.preview_label.setPixmap(QPixmap()), self.preview_label.setText("ffmpeg not available.")))
                    self.after(0, lambda: setattr(self, "_preview_busy", False))
                    return

                import subprocess
                fps = 0.0
                try:
                    fps = self._probe_video_fps(path) or 0.0
                except Exception:
                    fps = 0.0

                # Keep single-file duration fresh (enables scrub/play even without ffprobe).
                try:
                    if not self._timeline:
                        self._duration = float(self._probe_duration_cached(path) or 0.0)
                except Exception:
                    pass

                t = max(0.0, float(t_local or 0.0))
                fast_preview = False
                try:
                    fast_preview = bool((self.preview_quality_var.get() or "").strip().lower() == "fast")
                except Exception:
                    fast_preview = True
                # While playing, prefer fast preview automatically.
                if self._is_playing:
                    fast_preview = True

                import tempfile
                from PIL import Image

                with tempfile.TemporaryDirectory(prefix="fylorra_vidprev_") as td:
                    imgp = Path(td) / "frame.jpg"
                    cmd = [
                        str(ffmpeg),
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-ss",
                        f"{t:.3f}",
                    ]
                    if fast_preview:
                        cmd += ["-noaccurate_seek", "-skip_frame", "nokey"]
                    cmd += ["-i", str(path), "-an", "-sn", "-dn"]
                    vf_chain = []
                    if fast_preview:
                        vf_chain.append("scale=960:-2:force_original_aspect_ratio=decrease")
                    vf_chain += self._build_video_filters()
                    if vf_chain:
                        cmd += ["-vf", ",".join(vf_chain)]
                    cmd += ["-frames:v", "1", "-q:v", "6" if fast_preview else "3", str(imgp)]
                    subprocess.run(
                        cmd,
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=18,
                        **_subprocess_kwargs(),
                    )
                    if imgp.exists():
                        im = Image.open(imgp)
                        im.thumbnail((900, 430))
                        qimg = _pil_to_qimage(im)

                        def apply_img2():
                            try:
                                self._fps = float(fps or 0.0)
                                qual = "Fast" if fast_preview else "HQ"
                                self.fps_info.setText((f"FPS: {fps:.2f} | {qual}" if fps else f"FPS: ? | {qual}"))
                                pm = QPixmap.fromImage(qimg) if qimg is not None else None
                                if pm is not None:
                                    self.preview_label.setPixmap(pm)
                                    self.preview_label.setText("")
                                else:
                                    self.preview_label.setPixmap(QPixmap())
                                    self.preview_label.setText(path.name)
                                # update cache
                                try:
                                    if cache_key and pm is not None:
                                        self._preview_cache[cache_key] = pm
                                        self._preview_cache_order.append(cache_key)
                                        while len(self._preview_cache_order) > 40:
                                            old = self._preview_cache_order.pop(0)
                                            self._preview_cache.pop(old, None)
                                except Exception:
                                    pass
                            finally:
                                self._preview_busy = False

                        self.after(0, apply_img2)
                        return

                def apply_txt():
                    try:
                        self._fps = float(fps or 0.0)
                        self.fps_info.setText(f"FPS: {fps:.2f}" if fps else "FPS: ?")
                        self.preview_label.setPixmap(QPixmap())
                        self.preview_label.setText(path.name)
                    finally:
                        self._preview_busy = False

                self.after(0, apply_txt)
            except Exception:
                def clear_busy():
                    self._preview_busy = False

                self.after(0, clear_busy)
                try:
                    self.after(0, lambda: (self.preview_label.setPixmap(QPixmap()), self.preview_label.setText(path.name)))
                except Exception:
                    pass

        threading.Thread(target=work, args=(Path(p), t_seek), daemon=True).start()

    def _preview_source_at_time(self, timeline_t: float) -> tuple[Path, float] | None:
        """
        Returns (path, local_seek_seconds).
        If the timeline has clips, resolve the clip under the playhead and map timeline seconds -> source seconds.
        Otherwise, falls back to the currently selected file (legacy single-file preview).
        """
        timeline_t = max(0.0, float(timeline_t or 0.0))
        if self._timeline:
            t = 0.0
            for c in self._timeline:
                p = Path(c.path)
                is_img = (getattr(c, "kind", "video") or "").lower() == "image" or _is_image_suffix(p)
                if is_img:
                    dur = float(getattr(c, "duration_seconds", 0.0) or 0.0) or 3.0
                    if t <= timeline_t < t + dur:
                        return p, 0.0
                    t += dur
                    continue

                # video clip
                dur_total = float(self._probe_duration_cached(p) or 0.0)
                s0 = float(getattr(c, "start_seconds", 0.0) or 0.0)
                e0 = getattr(c, "end_seconds", None)
                if e0 is None and dur_total > 0:
                    e0 = dur_total
                if e0 is None:
                    e0 = s0 + 5.0
                clip_dur = max(0.05, float(e0) - float(s0))
                if t <= timeline_t < t + clip_dur:
                    local = s0 + (timeline_t - t)
                    local = max(0.0, min(float(e0), float(local)))
                    return p, float(local)
                t += clip_dur
            return None

        p = self._selected
        if not p:
            return None
        dur = float(getattr(self, "_duration", 0.0) or 0.0)
        if dur <= 0:
            return p, 0.0
        local = max(0.0, min(dur, timeline_t))
        return p, float(local)

    def _load_preview_frame(self):
        # Backward-compat (older callers)
        self._load_preview_frame_async()

    def _timeline_refresh(self):
        layout = self.timeline_list.layout
        if self._timeline_transitions:
            max_idx = len(self._timeline) - 1
            if max_idx < 1:
                self._timeline_transitions.clear()
            else:
                self._timeline_transitions = {
                    k: v for k, v in self._timeline_transitions.items() if 1 <= int(k) <= max_idx
                }
        _clear_layout(layout)
        row_idx = 0

        def add_section(title: str):
            nonlocal row_idx
            lbl = QLabel(title)
            lbl.setStyleSheet(f"color:{THEME['text_muted']};")
            layout.addWidget(lbl, row_idx, 0, 1, 1)
            row_idx += 1

        def add_row(name: str, info: str, selected: bool, on_select):
            nonlocal row_idx
            row = QFrame(self.timeline_list.content)
            row.setObjectName("panel")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 6, 8, 6)
            row_layout.setSpacing(8)
            sel_btn = QPushButton("▶" if selected else " ")
            sel_btn.setFixedWidth(32)
            sel_btn.clicked.connect(on_select)
            name_lbl = QLabel(name)
            name_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            info_lbl = QLabel(info)
            info_lbl.setStyleSheet(f"color:{THEME['text_muted']};")
            row_layout.addWidget(sel_btn)
            row_layout.addWidget(name_lbl, 1)
            if info:
                row_layout.addWidget(info_lbl)
            layout.addWidget(row, row_idx, 0, 1, 1)
            row_idx += 1

        add_section("Video Track")
        for idx, c in enumerate(self._timeline):
            selected = (self._timeline_selected == idx and self._audio_selected is None)
            is_img = (getattr(c, "kind", "video") or "").lower() == "image" or _is_image_suffix(Path(c.path))
            if is_img:
                d = float(getattr(c, "duration_seconds", 0.0) or 0.0) or 3.0
                info = f"duration: {d:.2f}s"
            else:
                s = _fmt_time(float(c.start_seconds or 0.0)) if c.start_seconds is not None else "start"
                e = _fmt_time(float(c.end_seconds)) if c.end_seconds is not None else "end"
                info = f"{s} -> {e}"
            add_row(Path(c.path).name, info, selected, lambda _c=False, i=idx: self._timeline_select(i))

        spacer = QWidget(self.timeline_list.content)
        spacer.setFixedHeight(6)
        layout.addWidget(spacer, row_idx, 0, 1, 1)
        row_idx += 1

        add_section("Audio Track")
        for idx, c in enumerate(self._audio_track):
            selected = (self._audio_selected == idx)
            pos = float(getattr(c, "timeline_start_seconds", 0.0) or 0.0)
            info = f"pos: {pos:.2f}s"
            add_row(Path(c.path).name, info, selected, lambda _c=False, i=idx: self._audio_select(i))

        self._redraw_timeline()
        self._update_output_preview()
        try:
            self.timeline_list.content.adjustSize()
        except Exception:
            pass

    def _timeline_select(self, idx: int, *, stop_playback: bool = True):
        if idx < 0 or idx >= len(self._timeline):
            return
        self._timeline_selected = idx
        self._audio_selected = None
        clip = self._timeline[idx]
        self._selected = Path(clip.path)
        if stop_playback:
            self._stop_preview_playback()
        is_img = (getattr(clip, "kind", "video") or "").lower() == "image" or Path(clip.path).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
        if is_img:
            self._duration = 0.0
            d = float(getattr(clip, "duration_seconds", 0.0) or 0.0) or 3.0
            self.start_var.set("")
            self.end_var.set(f"{d:.2f}")
        else:
            try:
                self._duration = float(self._probe_duration_cached(Path(self._selected)) or 0.0)
            except Exception:
                self._duration = 0.0
            self.start_var.set("" if clip.start_seconds is None else _fmt_time(float(clip.start_seconds)))
            self.end_var.set("" if clip.end_seconds is None else _fmt_time(float(clip.end_seconds)))
        self._sync_audio_fields_from_selected()
        self._refresh_media_list()
        self._load_preview_frame_async()
        self._timeline_refresh()

    def _timeline_add_selected(self):
        if not self._selected:
            return
        p = Path(self._selected)
        is_img = _is_image_suffix(p)
        s = _parse_time(self.start_var.get())
        e = _parse_time(self.end_var.get())
        img_dur = None
        if is_img:
            try:
                img_dur = float((self.image_dur_var.get() or "3").strip())
            except Exception:
                img_dur = 3.0
            if not img_dur or img_dur <= 0:
                img_dur = 3.0
        self._timeline.append(TimelineClip(path=p, kind="image" if is_img else "video", start_seconds=s if not is_img else None, end_seconds=e if not is_img else None, duration_seconds=img_dur))
        self._timeline_selected = len(self._timeline) - 1
        self._audio_selected = None
        self._timeline_refresh()
        try:
            self._load_preview_frame_async()
        except Exception:
            pass

    def _timeline_apply_trim_to_selected(self):
        if self._timeline_selected is None or self._timeline_selected < 0 or self._timeline_selected >= len(self._timeline):
            return
        s = _parse_time(self.start_var.get())
        e = _parse_time(self.end_var.get())
        old = self._timeline[self._timeline_selected]
        if (old.kind or "").lower() == "image" or _is_image_suffix(Path(old.path)):
            # For images, trim controls adjust duration (end-start).
            d = None
            if s is not None and e is not None and e > s:
                d = float(e) - float(s)
            elif e is not None and e > 0:
                d = float(e)
            elif s is not None and s > 0:
                d = float(s)
            if d is not None and d <= 0:
                d = None
            self._timeline[self._timeline_selected] = TimelineClip(path=Path(old.path), kind="image", duration_seconds=d or old.duration_seconds or 3.0)
        else:
            self._timeline[self._timeline_selected] = TimelineClip(path=Path(old.path), kind="video", start_seconds=s, end_seconds=e)
        self._timeline_refresh()

    def _timeline_split_selected(self):
        if self._timeline_selected is None or self._timeline_selected < 0 or self._timeline_selected >= len(self._timeline):
            self._set_toast("Select a clip to split.", ms=2000)
            return
        clip = self._timeline[self._timeline_selected]
        p = Path(clip.path)
        is_img = (getattr(clip, "kind", "video") or "").lower() == "image" or p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
        if is_img:
            # Split image duration in half.
            d = float(getattr(clip, "duration_seconds", 0.0) or 0.0) or 3.0
            if d <= 0.2:
                self._set_toast("Clip too short to split.", ms=2000)
                return
            a = max(0.1, d / 2.0)
            b = max(0.1, d - a)
            self._timeline[self._timeline_selected] = TimelineClip(path=p, kind="image", duration_seconds=a)
            self._timeline.insert(self._timeline_selected + 1, TimelineClip(path=p, kind="image", duration_seconds=b))
            self._timeline_selected += 1
            self._timeline_refresh()
            return

        # Split at playhead within the selected clip.
        timeline_t = float(self._scrub_time_seconds() or 0.0)
        t0 = self._video_clip_t0(int(self._timeline_selected))
        t = timeline_t - float(t0)
        start = float(clip.start_seconds or 0.0)
        dur_total = float(self._probe_duration_cached(p) or 0.0)
        end = float(clip.end_seconds) if clip.end_seconds is not None else (dur_total if dur_total > 0 else start + 9999.0)
        split_at = float(start) + max(0.0, float(t))
        if split_at <= start + 0.05 or split_at >= end - 0.05:
            self._set_toast("Move playhead inside the clip to split.", ms=2200)
            return
        left = TimelineClip(path=p, kind="video", start_seconds=start, end_seconds=split_at)
        right = TimelineClip(path=p, kind="video", start_seconds=split_at, end_seconds=end if clip.end_seconds is not None else None)
        self._timeline[self._timeline_selected] = left
        self._timeline.insert(self._timeline_selected + 1, right)
        self._timeline_selected += 1
        self._timeline_refresh()

    def _timeline_cut_out_range(self):
        r = self._range_seconds()
        if not r:
            QMessageBox.information(self, "Cut Out", "Shift+drag on the timeline to select a range first.")
            return
        a, b = r
        total = float(self._timeline_total_seconds() or 0.0)
        if total <= 0:
            return
        a = max(0.0, min(total, float(a)))
        b = max(0.0, min(total, float(b)))
        if b <= a + 0.01:
            return
        delta = float(b - a)

        # Cut video lane (sequential)
        new_tl: list[TimelineClip] = []
        t_cursor = 0.0
        for c in self._timeline:
            p = Path(c.path)
            is_img = (getattr(c, "kind", "video") or "").lower() == "image" or _is_image_suffix(p)
            if is_img:
                dur = float(getattr(c, "duration_seconds", 0.0) or 0.0) or 3.0
                dur = max(0.05, dur)
                t0 = t_cursor
                t1 = t_cursor + dur
                t_cursor = t1
                if t1 <= a or t0 >= b:
                    new_tl.append(c)
                    continue
                left_len = max(0.0, a - t0)
                right_len = max(0.0, t1 - b)
                if left_len > 0.02:
                    new_tl.append(TimelineClip(path=p, kind="image", duration_seconds=left_len))
                if right_len > 0.02:
                    new_tl.append(TimelineClip(path=p, kind="image", duration_seconds=right_len))
                continue

            # video clip
            s0 = float(getattr(c, "start_seconds", 0.0) or 0.0)
            e0 = getattr(c, "end_seconds", None)
            dur_total = float(self._probe_duration_cached(p) or 0.0)
            if e0 is None and dur_total > 0:
                e0 = dur_total
            if e0 is None:
                e0 = s0 + 5.0
            clip_dur = max(0.05, float(e0) - float(s0))
            t0 = t_cursor
            t1 = t_cursor + clip_dur
            t_cursor = t1
            if t1 <= a or t0 >= b:
                new_tl.append(c)
                continue
            left_len = max(0.0, a - t0)
            right_len = max(0.0, t1 - b)
            if left_len > 0.02:
                new_tl.append(TimelineClip(path=p, kind="video", start_seconds=s0, end_seconds=s0 + left_len))
            if right_len > 0.02:
                # skip over the removed region
                new_start = s0 + (b - t0)
                new_tl.append(TimelineClip(path=p, kind="video", start_seconds=new_start, end_seconds=float(e0)))

        self._timeline = new_tl
        if not self._timeline:
            self._timeline_selected = None
        else:
            self._timeline_selected = max(0, min(int(self._timeline_selected or 0), len(self._timeline) - 1))

        # Cut audio lane (positioned)
        new_audio: list[TimelineClip] = []
        for c in self._audio_track:
            p = Path(c.path)
            pos = float(getattr(c, "timeline_start_seconds", 0.0) or 0.0)
            dur_total = float(self._probe_duration_cached(p) or 0.0)
            s0 = float(getattr(c, "start_seconds", 0.0) or 0.0)
            e0 = getattr(c, "end_seconds", None)
            if e0 is None and dur_total > 0:
                e0 = dur_total
            if e0 is None:
                e0 = s0 + 5.0
            d = max(0.05, float(e0) - float(s0))
            t0 = pos
            t1 = pos + d
            if t1 <= a:
                new_audio.append(c)
                continue
            if t0 >= b:
                new_audio.append(
                    TimelineClip(
                        path=p,
                        kind="audio",
                        start_seconds=s0,
                        end_seconds=float(e0),
                        timeline_start_seconds=max(0.0, t0 - delta),
                        volume_db=getattr(c, "volume_db", None),
                        fade_in_seconds=getattr(c, "fade_in_seconds", None),
                        fade_out_seconds=getattr(c, "fade_out_seconds", None),
                    )
                )
                continue
            # overlap
            left_len = max(0.0, a - t0)
            right_len = max(0.0, t1 - b)
            if left_len > 0.02:
                new_audio.append(
                    TimelineClip(
                        path=p,
                        kind="audio",
                        start_seconds=s0,
                        end_seconds=s0 + left_len,
                        timeline_start_seconds=t0,
                        volume_db=getattr(c, "volume_db", None),
                        fade_in_seconds=getattr(c, "fade_in_seconds", None),
                        fade_out_seconds=getattr(c, "fade_out_seconds", None),
                    )
                )
            if right_len > 0.02:
                new_audio.append(
                    TimelineClip(
                        path=p,
                        kind="audio",
                        start_seconds=s0 + (b - t0),
                        end_seconds=float(e0),
                        timeline_start_seconds=a,
                        volume_db=getattr(c, "volume_db", None),
                        fade_in_seconds=getattr(c, "fade_in_seconds", None),
                        fade_out_seconds=getattr(c, "fade_out_seconds", None),
                    )
                )

        self._audio_track = sorted(new_audio, key=lambda x: float(getattr(x, "timeline_start_seconds", 0.0) or 0.0))
        if self._audio_selected is not None and self._audio_selected >= len(self._audio_track):
            self._audio_selected = len(self._audio_track) - 1 if self._audio_track else None

        # Reset playhead to the cut start and clear selection.
        self._stop_preview_playback()
        self._clear_range()
        self._timeline_refresh()
        self._set_scrub_time_seconds(min(a, float(self._preview_total_seconds() or 0.0)))

    def _audio_add_clip(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Add audio clip",
            "",
            "Audio files (*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus);;All files (*.*)",
        )
        if not path:
            return
        p = Path(path)
        clip = TimelineClip(path=p, kind="audio", start_seconds=0.0, end_seconds=None, timeline_start_seconds=0.0, volume_db=0.0)
        try:
            setattr(clip, "lane", 0)
        except Exception:
            pass
        self._audio_track.append(clip)
        self._audio_selected = len(self._audio_track) - 1
        self._timeline_selected = None
        self._sync_audio_fields_from_selected()
        self._timeline_refresh()

    def _audio_select(self, idx: int, *, stop_playback: bool = True):
        if idx < 0 or idx >= len(self._audio_track):
            return
        self._audio_selected = idx
        self._timeline_selected = None
        if stop_playback:
            self._stop_preview_playback()
        self._sync_audio_fields_from_selected()
        self._timeline_refresh()

    def _sync_audio_fields_from_selected(self):
        try:
            if self._audio_selected is None:
                self.audio_pos_var.set("0")
                self.audio_in_var.set("0")
                self.audio_out_var.set("")
                self.audio_vol_var.set("0")
                self.audio_fade_in_var.set("")
                self.audio_fade_out_var.set("")
                if hasattr(self, "audio_lane_var"):
                    self.audio_lane_var.set("1")
                return
            c = self._audio_track[self._audio_selected]
            lane = int(getattr(c, "lane", 0) or 0)
            if hasattr(self, "audio_lane_var"):
                self._sync_audio_lane_menu()
                self.audio_lane_var.set(str(lane + 1))
            self.audio_pos_var.set(f"{float(getattr(c, 'timeline_start_seconds', 0.0) or 0.0):.2f}")
            self.audio_in_var.set(f"{float(getattr(c, 'start_seconds', 0.0) or 0.0):.2f}")
            eo = getattr(c, "end_seconds", None)
            self.audio_out_var.set("" if eo is None else f"{float(eo):.2f}")
            self.audio_vol_var.set(f"{float(getattr(c, 'volume_db', 0.0) or 0.0):.1f}")
            fi = getattr(c, "fade_in_seconds", None)
            fo = getattr(c, "fade_out_seconds", None)
            self.audio_fade_in_var.set("" if fi is None else f"{float(fi):.2f}")
            self.audio_fade_out_var.set("" if fo is None else f"{float(fo):.2f}")
        except Exception:
            pass

    def _apply_selected_properties(self):
        # Applies to selected video/image clip.
        if self._timeline_selected is None:
            return
        self._timeline_apply_trim_to_selected()

    def _apply_audio_properties(self):
        if self._audio_selected is None:
            return
        c = self._audio_track[self._audio_selected]
        try:
            pos = float((self.audio_pos_var.get() or "0").strip())
        except Exception:
            pos = 0.0
        try:
            ain = float((self.audio_in_var.get() or "0").strip())
        except Exception:
            ain = 0.0
        aout = _parse_time(self.audio_out_var.get())
        try:
            vol = float((self.audio_vol_var.get() or "0").strip())
        except Exception:
            vol = 0.0
        fi = _parse_time(self.audio_fade_in_var.get())
        fo = _parse_time(self.audio_fade_out_var.get())
        lane = 0
        try:
            lane = max(0, int((self.audio_lane_var.get() or "1").strip()) - 1)
        except Exception:
            lane = int(getattr(c, "lane", 0) or 0)
        self._audio_track[self._audio_selected] = TimelineClip(
            path=Path(c.path),
            kind="audio",
            start_seconds=max(0.0, ain),
            end_seconds=aout if (aout is None or aout > ain) else None,
            timeline_start_seconds=max(0.0, pos),
            volume_db=vol,
            fade_in_seconds=fi,
            fade_out_seconds=fo,
        )
        try:
            setattr(self._audio_track[self._audio_selected], "lane", lane)
        except Exception:
            pass
        self._timeline_refresh()

    def _sync_audio_lane_menu(self):
        if not hasattr(self, "audio_lane_menu"):
            return
        n = max(1, int(getattr(self, "_audio_lane_count", 1) or 1))
        try:
            self.audio_lane_menu.clear()
            self.audio_lane_menu.addItems([str(i) for i in range(1, n + 1)])
        except Exception:
            pass

    def _add_audio_track(self):
        self._audio_lane_count = int(getattr(self, "_audio_lane_count", 1) or 1) + 1
        self._sync_audio_lane_menu()
        try:
            self._timeline_refresh()
        except Exception:
            pass
        self._set_toast(f"Added audio track A{self._audio_lane_count}.", ms=1800)

    def _on_more_action(self, value: str):
        v = (value or "").strip().lower()
        try:
            self.more_action_var.set("More v")
        except Exception:
            pass
        if not v or v.startswith("more"):
            return
        if "track" in v:
            self._add_audio_track()
            return
        if "clear range" in v:
            self._clear_range()
            self._set_toast("Cleared range selection.", ms=1600)
            return
        if "clear all" in v:
            self._timeline_clear()
            self._set_toast("Cleared timeline.", ms=1800)
            return

    def _toggle_maximize(self):
        try:
            st = str(self.state())
        except Exception:
            st = "normal"
        try:
            if st == "zoomed":
                self.state("normal")
            else:
                self.state("zoomed")
        except Exception:
            pass

    def _toggle_view_controls(self):
        vis = bool(self.view_controls_visible.get())
        vis = not vis
        self.view_controls_visible.set(vis)
        try:
            self.view_controls_frame.setVisible(vis)
            self.view_toggle_btn.setText("View ^" if vis else "View v")
        except Exception:
            pass

    def _sidebar_help_text(self) -> str:
        return (
            "Project Media\n"
            "- Double-click a card (or press +) to add to timeline\n"
            "- Drag onto timeline to place at exact time\n"
            "- Audio drops onto A1/A2\n"
            "- Shift+drag on timeline selects a range (Cut Out)\n"
            "- Shortcuts: R rotate, Shift+R rotate left, Del remove"
        )

    def _show_tooltip(self, widget, text: str):
        try:
            if not widget or not text:
                return
            pos = widget.mapToGlobal(QPoint(10, widget.height() + 8))
            QToolTip.showText(pos, text, widget)
            self._tooltip_win = True
        except Exception:
            self._tooltip_win = None

    def _bind_tooltip(self, widget, text: str):
        try:
            widget.enterEvent = lambda _e, w=widget: self._show_tooltip(w, text)
            widget.leaveEvent = lambda _e: self._hide_tooltip()
        except Exception:
            pass

    def _hide_tooltip(self):
        self._tooltip_win = None
        try:
            QToolTip.hideText()
        except Exception:
            pass

    def _slideshow_add_images(self):
        """
        Quick workflow: select images -> append as image clips using Img s duration.
        Optionally the user can add an audio bed via "Audio..." in the timeline list (or + Audio clips).
        """
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select images for slideshow",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff);;All files (*.*)",
        )
        if not files:
            return
        try:
            d = float((self.image_dur_var.get() or "3").strip())
        except Exception:
            d = 3.0
        if not d or d <= 0:
            d = 3.0
        for f in files:
            p = Path(f)
            if not p.exists() or not p.is_file():
                continue
            if p not in self._files:
                self._files.append(p)
            self._timeline.append(TimelineClip(path=p, kind="image", duration_seconds=float(d)))
        self._files.sort(key=lambda x: str(x).lower())
        self._timeline_selected = len(self._timeline) - 1 if self._timeline else None
        self._audio_selected = None
        self._refresh_media_list()
        self._timeline_refresh()

    def _set_toast(self, message: str, *, ms: int = 2500):
        try:
            if self._toast_after_id:
                self.after_cancel(self._toast_after_id)
        except Exception:
            pass
        try:
            self.range_label.setText(message)
        except Exception:
            return

        def restore():
            self._toast_after_id = None
            try:
                self._update_range_label()
            except Exception:
                pass

        try:
            self._toast_after_id = self.after(max(500, int(ms)), restore)
        except Exception:
            self._toast_after_id = None

    def _start_qt_drag(self, path: Path, pixmap: QPixmap | None):
        try:
            drag = QDrag(self)
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(path))])
            drag.setMimeData(mime)
            if pixmap is not None and not pixmap.isNull():
                pm = pixmap.scaled(200, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                drag.setPixmap(pm)
                drag.setHotSpot(QPoint(pm.width() // 2, pm.height() // 2))
            drag.exec(Qt.CopyAction)
        except Exception:
            pass

    def _widget_is_in_timeline_canvas(self, w) -> bool:
        try:
            cv = self.timeline_canvas
        except Exception:
            return False
        while w is not None:
            if w == cv:
                return True
            try:
                w = w.parent()
            except Exception:
                w = None
        return False

    def _widget_is_in_timeline_drop_zone(self, w) -> bool:
        try:
            cv = self.timeline_canvas
        except Exception:
            cv = None
        try:
            tl = self.timeline_list
        except Exception:
            tl = None
        while w is not None:
            if cv is not None and w == cv:
                return True
            if tl is not None and w == tl:
                return True
            try:
                w = w.parent()
            except Exception:
                w = None
        return False

    def _extract_paths_from_mime(self, event, *, validate: bool = True) -> list[Path]:
        paths: list[Path] = []
        try:
            md = event.mimeData()
        except Exception:
            return paths
        try:
            if md is not None and md.hasUrls():
                for url in md.urls():
                    try:
                        if url.isLocalFile():
                            local = url.toLocalFile()
                            if local:
                                paths.append(Path(local))
                        else:
                            local = url.toLocalFile()
                            if local:
                                paths.append(Path(local))
                    except Exception:
                        continue
        except Exception:
            pass
        if not paths:
            try:
                if md is not None and md.hasText():
                    txt = (md.text() or "").strip()
                    for raw in txt.splitlines():
                        raw = raw.strip().strip("\"")
                        if not raw:
                            continue
                        if raw.lower().startswith("file://"):
                            try:
                                local = QUrl(raw).toLocalFile()
                            except Exception:
                                local = ""
                            if local:
                                paths.append(Path(local))
                                continue
                        paths.append(Path(raw))
            except Exception:
                pass
        if not validate:
            return paths
        seen: set[str] = set()
        out: list[Path] = []
        for p in paths:
            try:
                key = str(p).lower()
            except Exception:
                key = str(p)
            if key in seen:
                continue
            seen.add(key)
            if p.exists() and p.is_file():
                out.append(p)
        return out

    def _extract_drag_payload(self, event, mime_type: str) -> str | None:
        try:
            md = event.mimeData()
        except Exception:
            return None
        try:
            if md is not None and md.hasFormat(mime_type):
                raw = md.data(mime_type)
                if raw is None:
                    return None
                try:
                    return bytes(raw).decode("utf-8").strip()
                except Exception:
                    return str(raw)
        except Exception:
            return None
        return None

    def _timeline_transition_boundaries(self) -> list[tuple[int, float]]:
        boundaries: list[tuple[int, float]] = []
        t = 0.0
        for idx, c in enumerate(self._timeline):
            if idx > 0:
                boundaries.append((idx, float(t)))
            dur = float(self._clip_duration_seconds(c) or 0.0) or 0.0
            t += max(0.05, dur)
        return boundaries

    def _nearest_transition_boundary(self, t: float) -> tuple[int, float] | None:
        boundaries = self._timeline_transition_boundaries()
        if not boundaries:
            return None
        return min(boundaries, key=lambda b: abs(b[1] - float(t)))

    def _apply_transition_drop(self, name: str, drop_time: float | None) -> bool:
        if len(self._timeline) < 2:
            self._set_toast("Add at least two clips to use transitions.", ms=2200)
            return False
        if drop_time is None:
            drop_time = float(self._scrub_time_seconds() or 0.0)
        nearest = self._nearest_transition_boundary(float(drop_time))
        if not nearest:
            return False
        idx, _t = nearest
        key = str(name or "").strip().lower()
        if key in {"", "none", "clear"}:
            if idx in self._timeline_transitions:
                self._timeline_transitions.pop(idx, None)
                self._set_toast("Cleared transition.", ms=1800)
        else:
            try:
                d = float(self.transition_dur_var.get() or 0.0)
            except Exception:
                d = 0.0
            d = max(0.0, min(2.0, d))
            self._timeline_transitions[idx] = {"name": str(name), "duration": float(d)}
            self._set_toast(f"Transition set at cut {idx}.", ms=2000)
        self._redraw_timeline()
        return True

    def _timeline_drag_indicator_at(self, x_local: float):
        try:
            cv = self.timeline_canvas
        except Exception:
            return
        try:
            total = float(self._timeline_total_seconds() or 1.0)
            t = float(self._timeline_x_to_time(float(x_local), total))
        except Exception:
            return
        self._drag_indicator_time = t
        try:
            if self._drag_indicator_id is not None:
                cv.delete(self._drag_indicator_id)
        except Exception:
            self._drag_indicator_id = None
        try:
            x = self._timeline_time_to_x(t, float(self._timeline_total_seconds() or 1.0))
            self._drag_indicator_id = cv.create_line(x, 0, x, int(cv.winfo_height() or 1), fill="#2fa4ff", width=2)
        except Exception:
            self._drag_indicator_id = None

    def _timeline_drag_indicator_clear(self):
        try:
            cv = self.timeline_canvas
        except Exception:
            return
        if self._drag_indicator_id is not None:
            try:
                cv.delete(self._drag_indicator_id)
            except Exception:
                pass
        self._drag_indicator_id = None
        self._drag_indicator_time = None

    def _on_timeline_drag_enter(self, event) -> bool:
        paths = self._extract_paths_from_mime(event, validate=False)
        transition = self._extract_drag_payload(event, "application/x-fylorra-transition")
        effect = self._extract_drag_payload(event, "application/x-fylorra-effect")
        if not (paths or transition or effect):
            return False
        x = int(event.position().x()) if hasattr(event, "position") else int(event.x())
        self._timeline_drag_indicator_at(x)
        return True
    def _on_timeline_drag_move(self, event) -> bool:
        paths = self._extract_paths_from_mime(event, validate=False)
        transition = self._extract_drag_payload(event, "application/x-fylorra-transition")
        effect = self._extract_drag_payload(event, "application/x-fylorra-effect")
        if not (paths or transition or effect):
            return False
        x = int(event.position().x()) if hasattr(event, "position") else int(event.x())
        self._timeline_drag_indicator_at(x)
        return True
    def _on_timeline_drag_leave(self, _event):
        self._timeline_drag_indicator_clear()

    def _on_timeline_drop(self, event) -> bool:
        transition = self._extract_drag_payload(event, "application/x-fylorra-transition")
        effect = self._extract_drag_payload(event, "application/x-fylorra-effect")
        drop_time = self._drag_indicator_time
        self._timeline_drag_indicator_clear()
        if transition:
            return self._apply_transition_drop(transition, drop_time)
        if effect:
            if drop_time is not None:
                info = self._timeline_clip_at_time(float(drop_time))
                if info:
                    try:
                        self._timeline_select(int(info.get("idx") or 0))
                    except Exception:
                        pass
            self._apply_effect_preset(effect)
            self._set_toast(f"Applied {effect} preset.", ms=2000)
            return True
        paths = self._extract_paths_from_mime(event, validate=True)
        if not paths:
            return False
        first = True
        for p in paths:
            self._toggle_selected(p)
            self._add_media_to_timeline(p, drop_time=drop_time if first else None)
            first = False
        return True
    def _update_drag_indicator(self, x_root: int, y_root: int):
        try:
            cv = self.timeline_canvas
        except Exception:
            return
        w = self.winfo_containing(x_root, y_root)
        if not self._widget_is_in_timeline_canvas(w):
            if self._drag_indicator_id is not None:
                try:
                    cv.delete(self._drag_indicator_id)
                except Exception:
                    pass
                self._drag_indicator_id = None
                self._drag_indicator_time = None
            return

        try:
            x_local = float(x_root - cv.winfo_rootx())
            total = float(self._timeline_total_seconds() or 1.0)
            t = float(self._timeline_x_to_time(x_local, total))
        except Exception:
            return
        self._drag_indicator_time = t
        try:
            if self._drag_indicator_id is not None:
                cv.delete(self._drag_indicator_id)
        except Exception:
            self._drag_indicator_id = None
        try:
            x = self._timeline_time_to_x(t, float(self._timeline_total_seconds() or 1.0))
            self._drag_indicator_id = cv.create_line(x, 0, x, int(cv.winfo_height() or 1), fill="#2fa4ff", width=2)
        except Exception:
            self._drag_indicator_id = None

    def _finalize_drag_drop(self, x_root: int, y_root: int):
        p = self._drag_media_path
        self._drag_media_path = None
        try:
            cv = self.timeline_canvas
        except Exception:
            cv = None
        t = self._drag_indicator_time
        self._drag_indicator_time = None
        if cv is not None and self._drag_indicator_id is not None:
            try:
                cv.delete(self._drag_indicator_id)
            except Exception:
                pass
        self._drag_indicator_id = None

        if not p:
            return
        w = self.winfo_containing(x_root, y_root)
        if not self._widget_is_in_timeline_drop_zone(w):
            return
        self._toggle_selected(p)
        # If the drop happened outside the time ruler/canvas, just append.
        self._add_media_to_timeline(p, drop_time=t if (t is not None and self._widget_is_in_timeline_canvas(w)) else None)

    def _timeline_insert_index_for_time(self, t: float) -> int:
        t = float(t or 0.0)
        cur = 0.0
        for idx, c in enumerate(self._timeline):
            d = float(self._clip_duration_seconds(c) or 0.0) or 0.0
            d = max(0.05, d)
            if t <= cur + d * 0.5:
                return idx
            cur += d
        return len(self._timeline)

    def _add_media_to_timeline(self, path: Path, *, drop_time: float | None = None):
        p = Path(path)
        if not p.exists():
            self._set_toast("File not found.", ms=1800)
            return

        is_img = _is_image_suffix(p)
        is_audio = _is_audio_suffix(p)
        if is_audio:
            # For audio, "append" would often be confusing; default to playhead when no drop_time provided.
            try:
                t = float(self._scrub_time_seconds() or 0.0) if drop_time is None else float(drop_time or 0.0)
            except Exception:
                t = 0.0
            clip = TimelineClip(path=p, kind="audio", start_seconds=0.0, end_seconds=None, timeline_start_seconds=max(0.0, t), volume_db=0.0)
            try:
                setattr(clip, "lane", 0)
            except Exception:
                pass
            self._audio_track.append(clip)
            self._audio_selected = len(self._audio_track) - 1
            self._timeline_selected = None
            self._sync_audio_fields_from_selected()
            self._timeline_refresh()
            self._set_toast(f"Added audio to timeline at { _fmt_time(max(0.0, t)) }.", ms=2200)
            return

        if is_img:
            try:
                img_dur = float((self.image_dur_var.get() or "3").strip())
            except Exception:
                img_dur = 3.0
            img_dur = 3.0 if img_dur <= 0 else img_dur
            clip = TimelineClip(path=p, kind="image", duration_seconds=float(img_dur))
        else:
            clip = TimelineClip(path=p, kind="video", start_seconds=0.0, end_seconds=None)
            try:
                self._preprocess_media_async(p)
            except Exception:
                pass

        if drop_time is None or not self._timeline:
            self._timeline.append(clip)
            idx = len(self._timeline) - 1
        else:
            idx = self._timeline_insert_index_for_time(float(drop_time or 0.0))
            self._timeline.insert(idx, clip)

        self._timeline_selected = idx
        self._audio_selected = None
        if p not in self._files:
            self._files.append(p)
            self._files.sort(key=lambda x: str(x).lower())
        self._refresh_media_list()
        self._timeline_refresh()
        if is_img:
            self._set_toast("Added image clip to timeline. Drag-drop lets you place it at an exact time.", ms=2600)
        else:
            self._set_toast("Added video clip to timeline. Drag-drop lets you place it at an exact time.", ms=2600)
        try:
            self._load_preview_frame_async()
        except Exception:
            pass

    def _preprocess_media_async(self, path: Path):
        """
        Background pre-processing: gather duration/fps once per media file.
        This avoids repeated ffprobe/ffmpeg calls during timeline redraw/zoom and prevents the '1 second' bug.
        """
        p = Path(path)
        key = str(p)
        with self._meta_lock:
            if key in self._media_meta:
                return
            if key in self._meta_inflight:
                return
            self._meta_inflight.add(key)

        def worker():
            try:
                dur = None
                fps = None
                try:
                    dur = float(self._probe_duration_cached(p) or 0.0) or None
                except Exception:
                    dur = None
                try:
                    fps = float(self._probe_video_fps(p) or 0.0) or None
                except Exception:
                    fps = None

                meta = {"duration": dur, "fps": fps}

                def apply():
                    with self._meta_lock:
                        self._media_meta[key] = meta
                        self._meta_inflight.discard(key)
                    # If we have a duration, "finalize" full-length clips by setting end_seconds.
                    if dur and dur > 0.1:
                        try:
                            updated = False
                            new_tl: list[TimelineClip] = []
                            for c in self._timeline:
                                if Path(c.path) != p or (getattr(c, "kind", "video") or "").lower() != "video":
                                    new_tl.append(c)
                                    continue
                                s0 = float(getattr(c, "start_seconds", 0.0) or 0.0)
                                e0 = getattr(c, "end_seconds", None)
                                if e0 is None or float(e0 or 0.0) <= 0:
                                    new_tl.append(TimelineClip(path=p, kind="video", start_seconds=s0, end_seconds=float(dur)))
                                    updated = True
                                else:
                                    new_tl.append(c)
                            if updated:
                                self._timeline = new_tl
                                self._timeline_refresh()
                                # Keep scrub/preview duration correct after metadata arrives.
                                try:
                                    self._set_scrub_time_seconds(min(self._scrub_time_seconds(), float(self._preview_total_seconds() or 0.0)))
                                except Exception:
                                    pass
                        except Exception:
                            pass

                self.after(0, apply)
            except Exception:
                with self._meta_lock:
                    self._meta_inflight.discard(key)

        threading.Thread(target=worker, daemon=True).start()

    def _timeline_remove_selected(self):
        if self._audio_selected is not None:
            idx = int(self._audio_selected)
            if 0 <= idx < len(self._audio_track):
                del self._audio_track[idx]
                self._audio_selected = None if not self._audio_track else max(0, min(idx, len(self._audio_track) - 1))
            self._timeline_refresh()
            return
        if self._timeline_selected is None:
            return
        idx = int(self._timeline_selected)
        if idx < 0 or idx >= len(self._timeline):
            return
        del self._timeline[idx]
        if not self._timeline:
            self._timeline_selected = None
        else:
            self._timeline_selected = max(0, min(idx, len(self._timeline) - 1))
        self._timeline_refresh()

    def _timeline_move(self, delta: int):
        if self._timeline_selected is None:
            return
        idx = int(self._timeline_selected)
        j = idx + int(delta)
        if j < 0 or j >= len(self._timeline):
            return
        self._timeline[idx], self._timeline[j] = self._timeline[j], self._timeline[idx]
        self._timeline_selected = j
        self._timeline_refresh()

    def _timeline_clear(self):
        self._timeline.clear()
        self._timeline_selected = None
        self._audio_track.clear()
        self._audio_selected = None
        self._audio_bed_path = None
        self._clear_range()
        self._set_scrub_time_seconds(0.0)
        self._timeline_refresh()

    def _timeline_shuffle_images(self):
        # Shuffle only image clips (keeps videos in place).
        img_idxs = [i for i, c in enumerate(self._timeline) if (getattr(c, "kind", "video") or "").lower() == "image" or Path(c.path).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}]
        if len(img_idxs) < 2:
            return
        imgs = [self._timeline[i] for i in img_idxs]
        random.shuffle(imgs)
        for i, clip in zip(img_idxs, imgs, strict=False):
            self._timeline[i] = clip
        self._timeline_selected = img_idxs[0]
        self._timeline_refresh()

    def _pick_audio_bed(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select audio bed (optional)",
            "",
            "Audio files (*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus);;All files (*.*)",
        )
        if not path:
            return
        self._audio_bed_path = Path(path)
        self._update_output_preview()

    def _timeline_total_seconds(self) -> float:
        total = 0.0
        for c in self._timeline:
            try:
                total += float(self._clip_duration_seconds(c) or 0.0)
            except Exception:
                pass
        # Extend to show audio track that starts later or runs longer.
        audio_extent = 0.0
        for a in self._audio_track:
            pos = float(getattr(a, "timeline_start_seconds", 0.0) or 0.0)
            dur_total = self._probe_duration_cached(Path(a.path)) or 0.0
            s = float(getattr(a, "start_seconds", 0.0) or 0.0)
            e = getattr(a, "end_seconds", None)
            if e is None and dur_total > 0:
                e = dur_total
            if e is None:
                e = s + 5.0
            d = max(0.1, float(e) - s)
            audio_extent = max(audio_extent, pos + d)
        total = max(total, audio_extent)
        if total > 0:
            return total
        return 1.0

    def _timeline_view_window(self, total: float) -> tuple[float, float]:
        total = max(0.0, float(total or 0.0))
        if total <= 0:
            return 0.0, 0.0
        try:
            z = float(self.tl_zoom_var.get())
        except Exception:
            z = float(self._tl_zoom or 1.0)
        z = max(1.0, min(10.0, z))
        self._tl_zoom = z

        win = total / z
        win = max(0.25, min(total, win))
        max_start = max(0.0, total - win)
        try:
            p = float(self.tl_pan_var.get())
        except Exception:
            p = float(self._tl_pan or 0.0)
        p = max(0.0, min(1.0, p))
        self._tl_pan = p
        start = max_start * p if max_start > 0 else 0.0
        end = min(total, start + win)
        return float(start), float(end)

    def _timeline_x_to_time(self, x: float, total: float) -> float:
        cv = self.timeline_canvas
        w = float(cv.winfo_width() or 1)
        gutter = 84
        pad_left = float(gutter)
        pad_right = 10.0
        usable = max(1.0, w - pad_left - pad_right)
        start, end = self._timeline_view_window(total)
        span = max(1e-6, float(end - start))
        xf = (float(x) - pad_left) / usable
        xf = max(0.0, min(1.0, xf))
        return float(start) + xf * span

    def _timeline_time_to_x(self, t: float, total: float) -> int:
        cv = self.timeline_canvas
        w = float(cv.winfo_width() or 1)
        gutter = 84
        pad_left = float(gutter)
        pad_right = 10.0
        usable = max(1.0, w - pad_left - pad_right)
        start, end = self._timeline_view_window(total)
        span = max(1e-6, float(end - start))
        xf = (float(t) - float(start)) / span
        xf = max(0.0, min(1.0, xf))
        return int(pad_left + xf * usable)

    def _range_seconds(self) -> tuple[float, float] | None:
        a = self._range_start_s
        b = self._range_end_s
        if a is None or b is None:
            return None
        a = float(a)
        b = float(b)
        if b < a:
            a, b = b, a
        if abs(b - a) < 0.01:
            return None
        return a, b

    def _update_range_label(self):
        try:
            r = self._range_seconds()
            if self._timeline_selected is not None or self._audio_selected is not None:
                tip = "Drag near clip edges to trim | drag audio clip to move | Shift+drag selects a range (Cut Out)."
            else:
                tip = "Shift+drag on timeline to select a range (then Cut Out)."
            self._tip_text = tip
            if not r:
                self.range_label.setText("")
                return
            a, b = r
            self.range_label.setText(f"Range: {_fmt_time(a)} -> {_fmt_time(b)} ({_fmt_time(b - a)})")
        except Exception:
            pass

    def _clear_range(self):
        self._range_start_s = None
        self._range_end_s = None
        self._range_selecting = False
        self._update_range_label()
        try:
            self._redraw_timeline()
        except Exception:
            pass

    def _on_tl_zoom(self, _v=None):
        try:
            z = float(self.tl_zoom_var.get())
        except Exception:
            z = 1.0
        z = max(1.0, min(10.0, z))
        self._tl_zoom = z
        try:
            self.tl_zoom_label.setText(f"{z:.1f}x")
        except Exception:
            pass
        try:
            if z <= 1.0001:
                self.tl_pan_var.set(0.0)
                self._tl_pan = 0.0
                self.tl_pan_slider.setEnabled(False)
            else:
                self.tl_pan_slider.setEnabled(True)
        except Exception:
            pass
        self._redraw_timeline()

    def _on_tl_pan(self, _v=None):
        try:
            p = float(self.tl_pan_var.get())
        except Exception:
            p = 0.0
        p = max(0.0, min(1.0, p))
        self._tl_pan = p
        try:
            self.tl_pan_label.setText(f"{int(p * 100):d}%")
        except Exception:
            pass
        self._redraw_timeline()

    def _redraw_timeline(self):
        try:
            cv = self.timeline_canvas
        except Exception:
            return
        # Keep a small set of PhotoImage references alive for this draw.
        try:
            self._tk_keep = []  # type: ignore[attr-defined]
        except Exception:
            pass
        cv.delete("all")
        w = int(cv.winfo_width() or 1)
        h = int(cv.winfo_height() or 1)
        gutter = 84
        pad_left = gutter
        pad_right = 10
        lane_gap = 8
        audio_lanes = max(1, int(getattr(self, "_audio_lane_count", 1) or 1))
        lanes = 1 + audio_lanes  # video + audio lanes
        ruler_top = 8
        ruler_h = 18
        lane_h = 30
        header_h = 12
        y_video = ruler_top + ruler_h + 10
        y_audio0 = y_video + lane_h + lane_gap

        empty = (not self._timeline and not self._audio_track)
        total = float(self._timeline_total_seconds() or 1.0)
        start_win, end_win = self._timeline_view_window(total)
        usable = max(1, w - pad_left - pad_right)
        click_map: list[dict] = []
        clip_spans: list[dict] = []
        transition_seq: list[tuple[str | None, float]] = []
        show_transitions = False
        try:
            transition_seq = self._transition_sequence()
            show_transitions = any((nm and float(dur) > 0.01) for nm, dur in transition_seq)
        except Exception:
            transition_seq = []

        lanes_bottom = y_audio0 + (audio_lanes * (lane_h + lane_gap)) - lane_gap
        lanes_bottom = max(y_video + lane_h, min(h - 6, lanes_bottom))
        if empty:
            cv.create_rectangle(0, 0, w, h, fill="#1b1f25", outline="")
            cv.create_text(10, y_video + lane_h // 2, text="V1", anchor="w", fill="#8cc2ff")
            for li in range(audio_lanes):
                y_lane = y_audio0 + li * (lane_h + lane_gap)
                cv.create_text(10, y_lane + lane_h // 2, text=f"A{li+1}", anchor="w", fill="#b6efcb")
            cv.create_text(
                gutter + 36,
                (y_video + lanes_bottom) // 2,
                text="Drop media here (drag from Project Media) or use + Clip / + Audio / Slideshow.",
                fill="#8a8f98",
                anchor="w",
            )
            return

        # Track header gutter + ruler background
        ruler_bg_h = ruler_top + ruler_h + 8
        cv.create_rectangle(0, 0, gutter, h, fill="#191d23", outline="")
        cv.create_rectangle(0, 0, gutter, ruler_bg_h, fill="#161a1f", outline="")
        cv.create_rectangle(gutter, 0, w, ruler_bg_h, fill="#1a1e24", outline="")
        cv.create_line(gutter, 0, gutter, h, fill="#2a2f36")
        cv.create_line(gutter, ruler_bg_h, w, ruler_bg_h, fill="#2a2f36")
        cv.create_rectangle(0, y_video, gutter, lanes_bottom, fill="#181d23", outline="")
        cv.create_line(gutter, y_video, gutter, lanes_bottom, fill="#2a2f36")
        cv.create_line(6, y_video + 6, 6, y_video + lane_h - 6, fill="#2fa4ff", width=3)
        cv.create_text(12, y_video + lane_h // 2, text="V1", anchor="w", fill="#8cc2ff")
        for li in range(audio_lanes):
            y_lane = y_audio0 + li * (lane_h + lane_gap)
            cv.create_line(6, y_lane + 6, 6, y_lane + lane_h - 6, fill="#4fd486", width=3)
            cv.create_text(12, y_lane + lane_h // 2, text=f"A{li+1}", anchor="w", fill="#b6efcb")

        # Lane backgrounds
        cv.create_rectangle(gutter, y_video, w, y_video + lane_h, fill="#1b1f25", outline="")
        line_start_x = gutter + 10
        for li in range(audio_lanes):
            y_lane = y_audio0 + li * (lane_h + lane_gap)
            shade = "#181c22" if (li % 2 == 0) else "#161a1f"
            cv.create_rectangle(gutter, y_lane, w, y_lane + lane_h, fill=shade, outline="")
        cv.create_line(line_start_x, y_video, w, y_video, fill="#2a2f36")
        for li in range(audio_lanes):
            y_lane = y_audio0 + li * (lane_h + lane_gap)
            cv.create_line(line_start_x, y_lane + lane_h, w, y_lane + lane_h, fill="#2a2f36")

        # Time ruler (ticks) just above the lanes
        tick_positions: list[tuple[int, float, int]] = []
        tick_step = None
        try:
            ruler_y = ruler_top
            cv.create_line(gutter, ruler_y + 10, w, ruler_y + 10, fill="#2a2f36")
            span = max(0.25, end_win - start_win)
            tick_candidates = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300]
            target = max(0.5, span / 10.0)
            step = min(tick_candidates, key=lambda v: abs(v - target))
            tick_step = step
            t = (int(start_win // step)) * step
            if t < start_win:
                t += step
            tick_idx = 0
            while t <= end_win + 1e-6:
                x = self._timeline_time_to_x(t, total)
                tick_positions.append((int(x), float(t), int(tick_idx)))
                cv.create_line(x, ruler_y + 10, x, ruler_y + 16, fill="#3a3f46")
                if step >= 1:
                    cv.create_text(x + 2, ruler_y + 2, anchor="nw", fill="#8a8f98", text=_fmt_time(t))
                t += step
                tick_idx += 1
        except Exception:
            pass

        # Vertical grid lines (subtle)
        if tick_positions:
            lanes_bottom = y_audio0 + (audio_lanes * (lane_h + lane_gap)) - lane_gap
            lanes_bottom = max(y_video + lane_h, min(h - 6, lanes_bottom))
            for x, _t, idx in tick_positions:
                if x <= pad_left + 6 or x > w - pad_right:
                    continue
                major = bool(tick_step and (tick_step >= 5 or idx % 5 == 0))
                col = "#242931" if major else "#1f242b"
                cv.create_line(x, y_video, x, lanes_bottom, fill=col)
        # Range overlay (Shift+drag selection)
        r = self._range_seconds()
        if r:
            a, b = r
            a = max(start_win, min(end_win, a))
            b = max(start_win, min(end_win, b))
            if b > a:
                x1 = self._timeline_time_to_x(a, total)
                x2 = self._timeline_time_to_x(b, total)
                cv.create_rectangle(x1, ruler_top, x2, h - 6, fill="#2b6cb0", stipple="gray25", outline="", tags="range")

        # Video lane: time-linear (supports zoom/pan) + filmstrip thumbnails
        t_cursor = 0.0
        for idx, c in enumerate(self._timeline):
            dur = 1.0
            if getattr(c, "duration_seconds", None) and float(getattr(c, "duration_seconds") or 0.0) > 0:
                dur = float(getattr(c, "duration_seconds") or 0.0)
            if c.start_seconds is not None and c.end_seconds is not None and c.end_seconds > c.start_seconds:
                dur = float(c.end_seconds) - float(c.start_seconds)
            dur = max(0.05, float(dur))
            t0 = float(t_cursor)
            t1 = float(t_cursor) + float(dur)
            t_cursor = t1
            if t1 < start_win or t0 > end_win:
                continue
            x1 = self._timeline_time_to_x(max(t0, start_win), total)
            x2 = self._timeline_time_to_x(min(t1, end_win), total)
            if x2 <= x1:
                x2 = x1 + 2
            is_selected = idx == self._timeline_selected
            fill = "#2b6cb0" if is_selected else "#232830"
            outline = "#4a5568" if is_selected else "#3a3f46"
            shadow = 2
            clip_top = y_video + 2
            clip_bottom = y_video + lane_h - 2
            clip_h = max(10, clip_bottom - clip_top)
            clip_header_h = min(header_h, max(10, int(clip_h * 0.35)))
            cv.create_rectangle(x1 + shadow, clip_top + shadow, x2 + shadow, clip_bottom + shadow, fill="#121417", outline="")
            cv.create_rectangle(x1, clip_top, x2, clip_bottom, fill=fill, outline=outline, width=1)
            header_fill = "#2f79c4" if is_selected else "#262c35"
            cv.create_rectangle(x1, clip_top, x2, clip_top + clip_header_h, fill=header_fill, outline="")
            cv.create_line(x1, clip_top + clip_header_h, x2, clip_top + clip_header_h, fill="#3a3f46")
            # Filmstrip thumbnails inside the clip
            # Keep filmstrip sampling lightweight (avoids freezes) and stable across zoom.
            try:
                clip_dur = float(self._clip_duration_seconds(c) or 0.0)
            except Exception:
                clip_dur = 0.0
            thumbs_cap = 10
            if clip_dur >= 600:
                thumbs_cap = 4
            elif clip_dur >= 180:
                thumbs_cap = 6
            thumbs_n = max(2, min(thumbs_cap, int(max(0, (x2 - x1)) // 140) + 3))
            self._ensure_filmstrip_cached(c, thumbs=thumbs_n)
            try:
                p = Path(c.path)
                is_img = (getattr(c, "kind", "video") or "").lower() == "image" or _is_image_suffix(p)
                s0 = float(getattr(c, "start_seconds", 0.0) or 0.0)
                e0 = getattr(c, "end_seconds", None)
                prefix = f"film::{p}::{int(s0*10)}::{int((float(e0) if e0 is not None else -1)*10)}::"
                dkey = f"{prefix}{int(thumbs_n)}"
                thumbs = self._filmstrip_cache.get(dkey)
                if not thumbs:
                    # Fallback: reuse any cached strip for this clip (keeps frames visible across zoom levels).
                    for kk, vv in self._filmstrip_cache.items():
                        if kk.startswith(prefix):
                            thumbs = vv
                            break
                if thumbs:
                    pad_in = 4
                    film_y = clip_top + clip_header_h + 2
                    span = max(1, (x2 - x1) - 2 * pad_in)
                    n = len(thumbs)
                    # Fill the whole clip width with repeated thumbs (more like a filmstrip).
                    tile_w = 90
                    tiles = int(max(1, min(16, (span // tile_w) + 1)))
                    if tiles <= 1:
                        tiles = min(6, max(1, n))
                    keep_refs = []
                    avail_h = max(6, int(clip_bottom - (clip_top + clip_header_h) - 4))
                    for i in range(tiles):
                        xx = x1 + pad_in + int((i / max(1, tiles - 1)) * span) if tiles > 1 else (x1 + pad_in)
                        ti = int((i / max(1, tiles - 1)) * (n - 1)) if n > 1 else 0
                        im = thumbs[max(0, min(n - 1, ti))]
                        im_draw = im
                        try:
                            if isinstance(im, QPixmap) and avail_h > 0 and im.height() > avail_h:
                                im_draw = im.scaledToHeight(avail_h, Qt.SmoothTransformation)
                                keep_refs.append(im_draw)
                        except Exception:
                            im_draw = im
                        if xx + 2 >= x2:
                            break
                        cv.create_image(xx, film_y, anchor="nw", image=im_draw)
                    # keep refs alive
                    setattr(self, "_tk_keep", getattr(self, "_tk_keep", []) + thumbs + keep_refs)  # type: ignore[attr-defined]
            except Exception:
                pass

            try:
                label = Path(c.path).stem
                label = re.sub(r"\\s+", " ", label).strip()
                if len(label) > 18:
                    label = label[:16] + "..."
                tag = "IMG" if (getattr(c, "kind", "video") or "").lower() == "image" or _is_image_suffix(Path(c.path)) else "VID"
                cv.create_text(x1 + 8, clip_top + clip_header_h // 2 + 1, text=f"{tag}  {label}", anchor="w", fill="#e6e6e6")
            except Exception:
                cv.create_text((x1 + x2) // 2, y_video + lane_h // 2, text=str(idx + 1), fill="#e6e6e6")
            if is_selected:
                cv.create_line(x1, clip_top, x1, clip_bottom, fill="#63b3ed", width=3)
                cv.create_line(x2, clip_top, x2, clip_bottom, fill="#63b3ed", width=3)
            clip_spans.append({"t0": t0, "t1": t1, "dur": dur, "x1": x1, "x2": x2})
            click_map.append(
                {
                    "x1": x1,
                    "x2": x2,
                    "idx": idx,
                    "track": "video",
                    "t0": t0,
                    "dur": dur,
                    "can_trim_in": t0 >= start_win + 1e-6,
                    "can_trim_out": t1 <= end_win - 1e-6,
                }
            )

        # Transition markers (visual only)
        if show_transitions and len(clip_spans) > 1:
            for i in range(1, len(clip_spans)):
                if (i - 1) >= len(transition_seq):
                    continue
                name, td = transition_seq[i - 1]
                if not name or float(td or 0.0) <= 0.01:
                    continue
                prev = clip_spans[i - 1]
                cur = clip_spans[i]
                try:
                    pair_td = min(float(td), float(prev["dur"]) * 0.5, float(cur["dur"]) * 0.5)
                except Exception:
                    pair_td = 0.0
                if pair_td < 0.05:
                    continue
                boundary = float(prev["t1"])
                if boundary < start_win or boundary > end_win:
                    continue
                x_left = self._timeline_time_to_x(max(start_win, boundary - pair_td), total)
                x_right = self._timeline_time_to_x(min(end_win, boundary + pair_td), total)
                if x_right <= x_left:
                    continue
                y0 = y_video + 1
                y1 = y_video + header_h - 1
                cv.create_rectangle(x_left, y0, x_right, y1, fill="#27425e", outline="", stipple="gray25")
                x_mid = int((x_left + x_right) / 2)
                box = 10
                x0 = x_mid - box // 2
                yb0 = y_video + 2
                yb1 = yb0 + box
                cv.create_rectangle(x0, yb0, x0 + box, yb1, fill="#233244", outline="#4a5568")
                cv.create_line(x0 + 2, yb0 + 2, x0 + box - 2, yb1 - 2, fill="#7fb6ff")
                cv.create_line(x0 + 2, yb1 - 2, x0 + box - 2, yb0 + 2, fill="#7fb6ff")
                # Flag marker to indicate an active transition at this cut.
                abbrev = {"fade": "XD", "fadeblack": "DB", "slideleft": "SL", "wipeleft": "WP"}.get(str(name), "T")
                flag_w = 22
                flag_h = 10
                fx0 = x_mid - flag_w // 2
                fy0 = ruler_top + 2
                if 0 <= fx0 <= w - flag_w:
                    cv.create_rectangle(fx0, fy0, fx0 + flag_w, fy0 + flag_h, fill="#2f79c4", outline="#4a5568")
                    cv.create_text(fx0 + flag_w // 2, fy0 + 2, text=abbrev, anchor="n", fill="#e6eef7")

        # Audio lanes (positioned, grouped by lane)
        for idx, c in enumerate(self._audio_track):
            pos = float(getattr(c, "timeline_start_seconds", 0.0) or 0.0)
            dur_total = self._probe_duration_cached(Path(c.path)) or 0.0
            s_in = float(getattr(c, "start_seconds", 0.0) or 0.0)
            e_out = getattr(c, "end_seconds", None)
            if e_out is None and dur_total > 0:
                e_out = dur_total
            if e_out is None:
                e_out = s_in + 5.0
            dur = max(0.1, float(e_out) - s_in)
            t0 = float(pos)
            t1 = float(pos) + float(dur)
            if t1 < start_win or t0 > end_win:
                continue
            x1 = self._timeline_time_to_x(max(t0, start_win), total)
            x2 = self._timeline_time_to_x(min(t1, end_win), total)
            x1 = max(pad_left, min(w - pad_right, x1))
            x2 = max(pad_left + 10, min(w - pad_right, x2))
            lane = int(getattr(c, "lane", 0) or 0)
            lane = max(0, min(audio_lanes - 1, lane))
            y_audio = y_audio0 + lane * (lane_h + lane_gap)
            is_a_selected = idx == self._audio_selected
            clip_top = y_audio + 2
            clip_bottom = y_audio + lane_h - 2
            clip_h = max(10, clip_bottom - clip_top)
            if is_a_selected:
                fill = "#1e3b2a"
                outline = "#4ade80"
                wave_top = "#88f7a4"
                wave_bot = "#5de394"
            else:
                fill = "#1b2621"
                outline = "#2f3a33"
                wave_top = "#74e39a"
                wave_bot = "#4fd486"
            cv.create_rectangle(x1, clip_top, x2, clip_bottom, fill=fill, outline=outline, width=1)
            cv.create_line(x1, clip_top, x2, clip_top, fill="#2b3430")
            # Waveform thumbnail (async cached)
            self._ensure_audio_wave_cached(Path(c.path))
            key = str(Path(c.path))
            amps = self._audio_wave_cache.get(key)
            if amps:
                pad_wave = 6
                span_px = max(1, x2 - x1 - (pad_wave * 2))
                n = len(amps)
                step = max(1, n // max(1, span_px))
                px = x1 + pad_wave
                top_mid = clip_top + int(clip_h * 0.32)
                bot_mid = clip_top + int(clip_h * 0.68)
                amp_max = max(4, int(clip_h * 0.30))
                for j in range(0, n, step):
                    a = max(0.0, min(1.0, float(amps[j])))
                    y = int(a * amp_max)
                    cv.create_line(px, top_mid - y, px, top_mid + y, fill=wave_top, width=2)
                    cv.create_line(px, bot_mid - y, px, bot_mid + y, fill=wave_bot, width=2)
                    px += 1
                    if px >= x2 - pad_wave:
                        break
                cv.create_line(x1 + 2, clip_top + clip_h // 2, x2 - 2, clip_top + clip_h // 2, fill="#2b3a32")
            else:
                cv.create_text((x1 + x2) // 2, clip_top + clip_h // 2, text="A", fill="#e6e6e6")
            if is_a_selected:
                cv.create_line(x1, clip_top, x1, clip_bottom, fill="#b794f4", width=3)
                cv.create_line(x2, clip_top, x2, clip_bottom, fill="#b794f4", width=3)
                fi = float(getattr(c, "fade_in_seconds", 0.0) or 0.0)
                fo = float(getattr(c, "fade_out_seconds", 0.0) or 0.0)
                # Fade handle markers (always visible)
                try:
                    cv.create_polygon(x1 + 12, clip_top + 2, x1 + 4, clip_top + clip_h // 2, x1 + 12, clip_bottom - 2, fill="#d6bcfa", outline="")
                    cv.create_polygon(x2 - 12, clip_top + 2, x2 - 4, clip_top + clip_h // 2, x2 - 12, clip_bottom - 2, fill="#d6bcfa", outline="")
                except Exception:
                    pass
                if fi > 0:
                    fx = x1 + int((fi / dur) * max(1, x2 - x1))
                    cv.create_line(fx, clip_top, fx, clip_bottom, fill="#d6bcfa", width=2)
                if fo > 0:
                    fx = x2 - int((fo / dur) * max(1, x2 - x1))
                    cv.create_line(fx, clip_top, fx, clip_bottom, fill="#d6bcfa", width=2)
            click_map.append(
                {
                    "x1": x1,
                    "x2": x2,
                    "idx": idx,
                    "track": "audio",
                    "t0": pos,
                    "dur": dur,
                    "can_trim_in": t0 >= start_win + 1e-6,
                    "can_trim_out": t1 <= end_win - 1e-6,
                    "lane": lane,
                }
            )

        # Playhead (preview time maps to timeline time if timeline is non-empty)
        t = float(self._scrub_time_seconds() or 0.0)
        t = max(0.0, min(total, t))
        px = self._timeline_time_to_x(t, total)
        px = max(pad_left, min(w - pad_right, px))
        cv.create_line(px, ruler_top, px, h - 6, fill="#63b3ed", width=2)
        try:
            tri_top = max(0, ruler_top - 2)
            tri_base = ruler_top + 6
            cv.create_polygon(px - 6, tri_base, px + 6, tri_base, px, tri_top, fill="#63b3ed", outline="")
        except Exception:
            pass
        self._timeline_click_map = click_map  # type: ignore[attr-defined]

    def _on_timeline_click(self, event):
        click_map = getattr(self, "_timeline_click_map", None)
        if not click_map:
            return
        x = int(getattr(event, "x", 0))
        total = float(self._timeline_total_seconds() or 1.0)
        t_click = self._timeline_x_to_time(float(x), total)

        # Shift+drag selects a range (for Cut Out).
        try:
            shift_down = bool(int(getattr(event, "state", 0)) & 0x0001)
        except Exception:
            shift_down = False
        if shift_down:
            self._drag_state = None
            self._range_selecting = True
            self._range_start_s = float(t_click)
            self._range_end_s = float(t_click)
            self._update_range_label()
            self._redraw_timeline()
            return
        self._range_selecting = False
        for item in click_map:
            if item["x1"] <= x <= item["x2"]:
                track = item.get("track")
                idx = int(item.get("idx", 0))
                if track == "video":
                    if (
                        self._timeline_selected == idx
                        and (
                            (bool(item.get("can_trim_in", True)) and abs(x - item["x1"]) <= 6)
                            or (bool(item.get("can_trim_out", True)) and abs(x - item["x2"]) <= 6)
                        )
                    ):
                        mode = "in" if abs(x - item["x1"]) <= 6 else "out"
                        self._drag_state = {"track": "video", "idx": idx, "mode": mode, "x0": x, "orig": self._timeline[idx]}
                        return
                    # Clicking inside a clip should move playhead and update preview.
                    self._set_scrub_time_seconds(t_click)
                    self._timeline_select(idx, stop_playback=False)
                    self._restart_qt_playback_if_playing()
                    return
                if track == "audio":
                    self._set_scrub_time_seconds(t_click)
                    self._audio_select(idx, stop_playback=False)
                    self._restart_qt_playback_if_playing()
                    # Dragging audio: handles (trim), fade markers, or move
                    x1 = float(item["x1"])
                    x2 = float(item["x2"])
                    if bool(item.get("can_trim_in", True)) and abs(x - x1) <= 6:
                        self._drag_state = {"track": "audio", "idx": idx, "mode": "trim_in", "x0": x, "orig": self._audio_track[idx], "item": item}
                        return
                    if bool(item.get("can_trim_out", True)) and abs(x - x2) <= 6:
                        self._drag_state = {"track": "audio", "idx": idx, "mode": "trim_out", "x0": x, "orig": self._audio_track[idx], "item": item}
                        return
                    # Fade marker drag (always available on selected clip)
                    if abs(x - (x1 + 12)) <= 7:
                        self._drag_state = {"track": "audio", "idx": idx, "mode": "fade_in", "x0": x, "orig": self._audio_track[idx], "item": item}
                        return
                    if abs(x - (x2 - 12)) <= 7:
                        self._drag_state = {"track": "audio", "idx": idx, "mode": "fade_out", "x0": x, "orig": self._audio_track[idx], "item": item}
                        return

                    # Fade marker drag if close to current fade lines
                    c = self._audio_track[idx]
                    dur = float(item.get("dur", 1.0) or 1.0)
                    width = max(1.0, x2 - x1)
                    fi = float(getattr(c, "fade_in_seconds", 0.0) or 0.0)
                    fo = float(getattr(c, "fade_out_seconds", 0.0) or 0.0)
                    if fi > 0:
                        fx = x1 + (fi / dur) * width
                        if abs(x - fx) <= 6:
                            self._drag_state = {"track": "audio", "idx": idx, "mode": "fade_in", "x0": x, "orig": c, "item": item}
                            return
                    if fo > 0:
                        fx = x2 - (fo / dur) * width
                        if abs(x - fx) <= 6:
                            self._drag_state = {"track": "audio", "idx": idx, "mode": "fade_out", "x0": x, "orig": c, "item": item}
                            return
                    self._drag_state = {"track": "audio", "idx": idx, "mode": "move", "x0": x, "orig": self._audio_track[idx], "item": item}
                    return
        # Clicked empty space: jump playhead
        self._set_scrub_time_seconds(self._timeline_x_to_time(float(x), total))
        self._restart_qt_playback_if_playing()

    def _on_timeline_double_click(self, event):
        try:
            x = int(getattr(event, "x", 0))
        except Exception:
            x = 0
        total = float(self._timeline_total_seconds() or 1.0)
        self._set_scrub_time_seconds(self._timeline_x_to_time(float(x), total))
        self._restart_qt_playback_if_playing()

    def _restart_qt_playback_if_playing(self):
        if not self._is_playing:
            return
        if bool(getattr(self, "_use_qt_player", False)):
            if self._seek_qt_player_to_time(float(self._scrub_time_seconds() or 0.0), autoplay=True):
                return
            self._stop_qt_playback()
            if not self._start_qt_playback():
                self._play_last_ts = time.time()
                self._play_tick()

    def _seek_qt_player_to_time(self, timeline_t: float, *, autoplay: bool = False) -> bool:
        if not self._has_qt_player() or not self._media_player:
            return False
        self._live_transition_preview = bool(self._has_active_transitions())
        in_trans = self._transition_preview_info(timeline_t) is not None if self._live_transition_preview else False
        timeline_t = max(0.0, float(timeline_t or 0.0))
        info = self._timeline_clip_at_time(timeline_t) if self._timeline else None
        if info and info.get("is_image"):
            self._stop_qt_playback()
            return False
        if info:
            clip = info.get("clip")
            p = Path(clip.path)
            local_start = float(info.get("local_start", 0.0) or 0.0)
            local_end = float(info.get("local_end", 0.0) or 0.0)
            clip_start_t = float(info.get("t0") or 0.0)
            offset = max(0.0, float(timeline_t) - clip_start_t)
            start_local = float(local_start) + float(offset)
            if local_end > 0:
                start_local = min(start_local, max(0.0, float(local_end) - 0.02))
            self._player_mode = "timeline"
            self._player_clip_idx = int(info.get("idx") or 0)
            self._player_clip_start_t = float(timeline_t)
            self._player_clip_start_ms = int(start_local * 1000.0)
            self._player_clip_end_ms = int(local_end * 1000.0) if local_end > 0 else None
        else:
            src = self._preview_source_at_time(timeline_t)
            if not src:
                return False
            p, local_start = src
            p = Path(p)
            if _is_image_suffix(p):
                self._stop_qt_playback()
                return False
            self._player_mode = "single"
            self._player_clip_idx = None
            self._player_clip_start_t = 0.0
            self._player_clip_start_ms = int(float(local_start or 0.0) * 1000.0)
            self._player_clip_end_ms = None
        if not p.exists():
            return False
        try:
            cur = getattr(self, "_player_src_path", None)
            if cur is None or Path(cur) != p:
                self._media_player.stop()
                self._media_player.setSource(QUrl.fromLocalFile(str(p)))
            self._media_player.setPosition(int(self._player_clip_start_ms or 0))
            self._apply_realtime_fx()
            if in_trans:
                self._show_preview_label()
            else:
                self._show_preview_video()
            self._use_qt_player = True
            self._player_src_path = str(p)
            if autoplay or self._is_playing:
                self._media_player.play()
            return True
        except Exception:
            return False

    def _on_timeline_drag(self, event):
        if self._range_selecting:
            total = float(self._timeline_total_seconds() or 1.0)
            x = int(getattr(event, "x", 0))
            t = self._timeline_x_to_time(float(x), total)
            self._range_end_s = float(t)
            self._update_range_label()
            self._redraw_timeline()
            return
        st = self._drag_state
        if not st:
            total = float(self._timeline_total_seconds() or 1.0)
            x = int(getattr(event, "x", 0))
            self._set_scrub_time_seconds(self._timeline_x_to_time(float(x), total))
            return
        x = int(getattr(event, "x", 0))
        click_map = getattr(self, "_timeline_click_map", None) or []
        item = None
        for it in click_map:
            if it.get("track") == st.get("track") and int(it.get("idx", -1)) == int(st.get("idx", -2)):
                item = it
                break
        if not item:
            return
        total = float(self._timeline_total_seconds() or 1.0)
        start_win, end_win = self._timeline_view_window(total)
        view_span = max(1e-6, float(end_win - start_win))
        w = int(self.timeline_canvas.winfo_width() or 1)
        gutter = 84
        pad_left = gutter + 10
        pad_right = 10
        usable = max(1, w - pad_left - pad_right)

        if st.get("track") == "audio":
            orig: TimelineClip = st.get("orig")
            mode = st.get("mode")
            x1 = float(item["x1"])
            x2 = float(item["x2"])
            width = max(1.0, x2 - x1)
            dur = float(item.get("dur", 1.0) or 1.0)
            if mode == "move":
                dx = x - int(st.get("x0", x))
                dt = (dx / usable) * view_span
                pos0 = float(getattr(orig, "timeline_start_seconds", 0.0) or 0.0)
                pos = max(0.0, self._snap_seconds(pos0 + dt))
                self._audio_track[int(st["idx"])] = TimelineClip(
                    path=Path(orig.path),
                    kind="audio",
                    start_seconds=orig.start_seconds,
                    end_seconds=orig.end_seconds,
                    timeline_start_seconds=pos,
                    volume_db=getattr(orig, "volume_db", None),
                    fade_in_seconds=getattr(orig, "fade_in_seconds", None),
                    fade_out_seconds=getattr(orig, "fade_out_seconds", None),
                )
                self._sync_audio_fields_from_selected()
                self._redraw_timeline()
                return
            if mode in {"trim_in", "trim_out"}:
                dx = x - int(st.get("x0", x))
                dsec = (dx / width) * dur
                dur_total = self._probe_duration_cached(Path(orig.path)) or 0.0
                s0 = float(getattr(orig, "start_seconds", 0.0) or 0.0)
                e0 = getattr(orig, "end_seconds", None)
                if e0 is None and dur_total > 0:
                    e0 = dur_total
                if e0 is None:
                    e0 = s0 + dur
                if mode == "trim_in":
                    s1 = max(0.0, self._snap_seconds(s0 + dsec))
                    if s1 >= float(e0) - 0.05:
                        s1 = float(e0) - 0.05
                    self._audio_track[int(st["idx"])] = TimelineClip(
                        path=Path(orig.path),
                        kind="audio",
                        start_seconds=s1,
                        end_seconds=float(e0),
                        timeline_start_seconds=getattr(orig, "timeline_start_seconds", 0.0),
                        volume_db=getattr(orig, "volume_db", None),
                        fade_in_seconds=getattr(orig, "fade_in_seconds", None),
                        fade_out_seconds=getattr(orig, "fade_out_seconds", None),
                    )
                else:
                    e1 = max(s0 + 0.05, self._snap_seconds(float(e0) + dsec))
                    if dur_total > 0:
                        e1 = min(e1, dur_total)
                    self._audio_track[int(st["idx"])] = TimelineClip(
                        path=Path(orig.path),
                        kind="audio",
                        start_seconds=s0,
                        end_seconds=e1,
                        timeline_start_seconds=getattr(orig, "timeline_start_seconds", 0.0),
                        volume_db=getattr(orig, "volume_db", None),
                        fade_in_seconds=getattr(orig, "fade_in_seconds", None),
                        fade_out_seconds=getattr(orig, "fade_out_seconds", None),
                    )
                self._sync_audio_fields_from_selected()
                self._redraw_timeline()
                return
            if mode in {"fade_in", "fade_out"}:
                # Fade markers: compute seconds from edge.
                if mode == "fade_in":
                    fi = max(0.0, min(dur, ((x - x1) / width) * dur))
                    fi = self._snap_seconds(fi)
                    self._audio_track[int(st["idx"])] = TimelineClip(
                        path=Path(orig.path),
                        kind="audio",
                        start_seconds=orig.start_seconds,
                        end_seconds=orig.end_seconds,
                        timeline_start_seconds=getattr(orig, "timeline_start_seconds", 0.0),
                        volume_db=getattr(orig, "volume_db", None),
                        fade_in_seconds=fi,
                        fade_out_seconds=getattr(orig, "fade_out_seconds", None),
                    )
                else:
                    fo = max(0.0, min(dur, ((x2 - x) / width) * dur))
                    fo = self._snap_seconds(fo)
                    self._audio_track[int(st["idx"])] = TimelineClip(
                        path=Path(orig.path),
                        kind="audio",
                        start_seconds=orig.start_seconds,
                        end_seconds=orig.end_seconds,
                        timeline_start_seconds=getattr(orig, "timeline_start_seconds", 0.0),
                        volume_db=getattr(orig, "volume_db", None),
                        fade_in_seconds=getattr(orig, "fade_in_seconds", None),
                        fade_out_seconds=fo,
                    )
                self._sync_audio_fields_from_selected()
                self._redraw_timeline()
                return

        if st.get("track") == "video":
            orig: TimelineClip = st.get("orig")
            mode = st.get("mode")
            span = float(item.get("dur", 1.0) or 1.0)
            px_span = max(1.0, float(item["x2"] - item["x1"]))
            dx = x - int(st.get("x0", x))
            dsec = (dx / px_span) * span
            s0 = float(orig.start_seconds or 0.0)
            e0 = float(orig.end_seconds) if orig.end_seconds is not None else None
            if mode == "in":
                s1 = max(0.0, self._snap_seconds(s0 + dsec))
                if e0 is not None and s1 >= e0 - 0.05:
                    s1 = e0 - 0.05
                # ripple shift audio after old clip end
                if bool(self.ripple_var.get()):
                    idx = int(st["idx"])
                    t0 = self._video_clip_t0(idx)
                    old_dur = float(item.get("dur", 0.0) or 0.0)
                    new_dur = max(0.1, (e0 - s1) if e0 is not None else old_dur)
                    self._ripple_shift_audio(t0 + old_dur, new_dur - old_dur)
                self._timeline[int(st["idx"])] = TimelineClip(path=Path(orig.path), kind=orig.kind, start_seconds=s1, end_seconds=e0, duration_seconds=orig.duration_seconds)
                self.start_var.set(_fmt_time(s1))
            else:
                if e0 is None:
                    e0 = s0 + span
                e1 = max(s0 + 0.05, self._snap_seconds(e0 + dsec))
                if bool(self.ripple_var.get()):
                    idx = int(st["idx"])
                    t0 = self._video_clip_t0(idx)
                    old_dur = float(item.get("dur", 0.0) or 0.0)
                    new_dur = max(0.1, float(e1) - float(s0))
                    self._ripple_shift_audio(t0 + old_dur, new_dur - old_dur)
                self._timeline[int(st["idx"])] = TimelineClip(path=Path(orig.path), kind=orig.kind, start_seconds=s0, end_seconds=e1, duration_seconds=orig.duration_seconds)
                self.end_var.set(_fmt_time(e1))
            self._redraw_timeline()
            return

    def _ensure_audio_wave_cached(self, path: Path):
        key = str(path)
        if key in self._audio_wave_cache or key in self._audio_wave_inflight:
            return
        self._audio_wave_inflight.add(key)

        def worker(p: Path, k: str):
            ffmpeg = get_ffmpeg_exe()
            if not ffmpeg:
                self._audio_wave_inflight.discard(k)
                return
            import subprocess
            try:
                # Decode a short preview for waveform (20s max) to keep it fast.
                cmd = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-i", str(p), "-vn", "-ac", "1", "-ar", "8000", "-t", "20", "-f", "s16le", "pipe:1"]
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    **_subprocess_kwargs(),
                )
                data = bytearray()
                max_bytes = 2 * 8000 * 20
                while proc.stdout and len(data) < max_bytes:
                    chunk = proc.stdout.read(8192)
                    if not chunk:
                        break
                    data.extend(chunk)
                try:
                    proc.terminate()
                except Exception:
                    pass
                if len(data) < 4:
                    return
                samples = len(data) // 2
                buckets = 320
                step = max(1, samples // buckets)
                amps: list[float] = []
                mv = memoryview(data)
                for i in range(0, samples, step):
                    peak = 0
                    for j in range(i, min(samples, i + step)):
                        lo = mv[j * 2]
                        hi = mv[j * 2 + 1]
                        v = int.from_bytes(bytes([lo, hi]), byteorder="little", signed=True)
                        peak = max(peak, abs(v))
                    amps.append(min(1.0, float(peak) / 32768.0))
                # light smoothing
                sm: list[float] = []
                for i, a in enumerate(amps):
                    a0 = amps[i - 1] if i > 0 else a
                    a1 = amps[i + 1] if i + 1 < len(amps) else a
                    sm.append((a0 + a + a1) / 3.0)

                def apply():
                    self._audio_wave_cache[k] = sm
                    self._audio_wave_inflight.discard(k)
                    try:
                        self._redraw_timeline()
                    except Exception:
                        pass

                self.after(0, apply)
            except Exception:
                self._audio_wave_inflight.discard(k)

        threading.Thread(target=worker, args=(Path(path), key), daemon=True).start()

    def _ensure_filmstrip_cached(self, clip: TimelineClip, *, thumbs: int = 5):
        """
        Cache a small list of QPixmap thumbnails for a clip for drawing inside the timeline segment.
        """
        if Image is None:
            return
        p = Path(clip.path)
        is_img = (getattr(clip, "kind", "video") or "").lower() == "image" or _is_image_suffix(p)
        s0 = float(getattr(clip, "start_seconds", 0.0) or 0.0)
        e0 = getattr(clip, "end_seconds", None)
        base_prefix = f"film::{p}::{int(s0*10)}::{int((float(e0) if e0 is not None else -1)*10)}::"
        try:
            max_cached = 0
            for k in self._filmstrip_cache.keys():
                if not k.startswith(base_prefix):
                    continue
                try:
                    cached_count = int(k.split("::")[-1])
                except Exception:
                    cached_count = 0
                max_cached = max(max_cached, cached_count)
            if max_cached >= int(thumbs):
                return
        except Exception:
            pass
        dkey = f"film::{p}::{int(s0*10)}::{int((float(e0) if e0 is not None else -1)*10)}::{int(thumbs)}"
        if dkey in self._filmstrip_cache or dkey in self._filmstrip_inflight:
            return
        self._filmstrip_inflight.add(dkey)

        def worker():
            try:
                if is_img:
                    im = self._open_pil_image(p)
                    if im is None:
                        return
                    try:
                        im = im.convert("RGB")
                    except Exception:
                        pass
                    im.thumbnail((140, 80))
                    imgs = [im.copy()]
                else:
                    ffmpeg = get_ffmpeg_exe()
                    if not ffmpeg:
                        return
                    dur_total = float(self._probe_duration_cached(p) or 0.0)
                    if e0 is None and dur_total > 0:
                        end_s = dur_total
                    elif e0 is not None:
                        end_s = float(e0)
                    else:
                        end_s = s0 + 5.0
                    span = max(0.2, end_s - s0)
                    # sample positions across the clip
                    times = [s0 + (span * (i / max(1, thumbs - 1))) for i in range(thumbs)]
                    import subprocess, tempfile
                    imgs = []
                    with tempfile.TemporaryDirectory(prefix="fylorra_film_") as td:
                        for i, t in enumerate(times):
                            outp = Path(td) / f"t{i}.jpg"
                            # Use fast seek first for big files.
                            cmds = [
                                [
                                    str(ffmpeg),
                                    "-hide_banner",
                                    "-loglevel",
                                    "error",
                                    "-ss",
                                    f"{t:.3f}",
                                    "-noaccurate_seek",
                                    "-skip_frame",
                                    "nokey",
                                    "-i",
                                    str(p),
                                    "-an",
                                    "-sn",
                                    "-dn",
                                    "-vf",
                                    "scale=280:-2:force_original_aspect_ratio=decrease",
                                    "-frames:v",
                                    "1",
                                    "-q:v",
                                    "6",
                                    str(outp),
                                ],
                                [
                                    str(ffmpeg),
                                    "-hide_banner",
                                    "-loglevel",
                                    "error",
                                    "-ss",
                                    f"{t:.3f}",
                                    "-i",
                                    str(p),
                                    "-an",
                                    "-sn",
                                    "-dn",
                                    "-vf",
                                    "scale=280:-2:force_original_aspect_ratio=decrease",
                                    "-frames:v",
                                    "1",
                                    "-q:v",
                                    "6",
                                    str(outp),
                                ],
                            ]
                            ok = False
                            for cmd in cmds:
                                try:
                                    if outp.exists():
                                        outp.unlink()
                                except Exception:
                                    pass
                                subprocess.run(
                                    cmd,
                                    check=False,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                    timeout=20,
                                    **_subprocess_kwargs(),
                                )
                                if not outp.exists():
                                    continue
                                try:
                                    im = Image.open(outp).convert("RGB")
                                    im.thumbnail((140, 80))
                                    imgs.append(im.copy())
                                    ok = True
                                    break
                                except Exception:
                                    ok = False
                                    continue

                if not imgs:
                    return

                def apply():
                    photos = []
                    for im in imgs:
                        try:
                            pm = _pil_to_pixmap(im)
                            if pm is not None:
                                photos.append(pm)
                        except Exception:
                            continue
                    if not photos:
                        self._filmstrip_inflight.discard(dkey)
                        return
                    self._filmstrip_cache[dkey] = photos
                    self._filmstrip_inflight.discard(dkey)
                    try:
                        self._redraw_timeline()
                    except Exception:
                        pass

                self.after(0, apply)
            except Exception:
                self._filmstrip_inflight.discard(dkey)

        threading.Thread(target=worker, daemon=True).start()

    def _on_timeline_up(self, event):
        if self._range_selecting:
            self._range_selecting = False
            r = self._range_seconds()
            total = float(self._timeline_total_seconds() or 1.0)
            if not r:
                x = int(getattr(event, "x", 0))
                self._clear_range()
                self._set_scrub_time_seconds(self._timeline_x_to_time(float(x), total))
                return
            self._update_range_label()
            self._redraw_timeline()
            return
        self._drag_state = None

    def _build_request(self) -> MediaEditRequest | None:
        if not self._selected:
            QMessageBox.warning(self, "No file", "Import and select a video file first.")
            return None
        ext = "." + self.format_var.get().strip().lower().lstrip(".")
        name = (self.out_name.get() or "Edited_Video").strip()
        safe = re.sub(r"[<>:\"/\\\\|?*]+", "_", name).strip(" ._")
        outp = self.out_folder / f"{safe}{ext}"

        start_s = _parse_time(self.start_var.get())
        end_s = _parse_time(self.end_var.get())
        scale = self.res_var.get()
        scale_h = None
        if scale == "360p":
            scale_h = 360
        elif scale == "480p":
            scale_h = 480
        elif scale == "720p":
            scale_h = 720
        elif scale == "1080p":
            scale_h = 1080
        elif scale == "4k":
            scale_h = 2160

        fps = None
        if self.fps_var.get().isdigit():
            fps = int(self.fps_var.get())

        crf = (self.crf_var.get() or "").strip()
        crf = crf if crf else None

        vfilters = self._build_video_filters()
        return MediaEditRequest(
            input_path=self._selected,
            output_path=outp,
            overwrite=True,
            start_seconds=start_s,
            end_seconds=end_s,
            video_codec=self.codec_var.get(),
            video_crf=crf,
            scale_height=scale_h,
            fps=fps,
            use_gpu=bool(self.use_gpu_var.get()),
            video_filters=vfilters or None,
        )

    def _start_render(self):
        if self._render_thread and self._render_thread.is_alive():
            return

        self._cancel.clear()
        self.progress.setValue(0)
        self.progress_label.setText("Starting...")
        self._stop_preview_playback()

        def set_progress(frac: float, msg: str):
            try:
                pct = int(max(0.0, min(1.0, float(frac))) * 100)
                self.progress.setValue(pct)
            except Exception:
                pass
            try:
                self.progress_label.setText(f"{pct}%  {msg}")
            except Exception:
                pass

        def done(ok: bool, msg: str, out_path: str | None = None):
            if ok:
                self.progress.setValue(100)
                self.progress_label.setText("100%  Done.")
                if out_path:
                    QMessageBox.information(self, "Render", f"Saved:\n{out_path}")
            else:
                self.progress_label.setText("Failed.")
                QMessageBox.critical(self, "Render failed", msg or "Render failed.")

        # Prefer timeline render if user added clips; otherwise single-file render.
        if self._timeline:
            ext = "." + self.format_var.get().strip().lower().lstrip(".")
            name = (self.out_name.get() or "Edited_Video").strip()
            safe = re.sub(r"[<>:\"/\\\\|?*]+", "_", name).strip(" ._")
            outp = self.out_folder / f"{safe}{ext}"

            scale_h = None
            if self.res_var.get() == "360p":
                scale_h = 360
            elif self.res_var.get() == "480p":
                scale_h = 480
            elif self.res_var.get() == "720p":
                scale_h = 720
            elif self.res_var.get() == "1080p":
                scale_h = 1080
            elif self.res_var.get() == "4k":
                scale_h = 2160

            fps = int(self.fps_var.get()) if (self.fps_var.get() or "").isdigit() else None
            crf = (self.crf_var.get() or "").strip() or None

            def run_tl():
                transition_kind = self._transition_ffmpeg_name()
                _kind, transition_dur = self._transition_settings()
                vfilters = self._build_video_filters()
                res = render_video_timeline(
                    list(self._timeline),
                    output_path=Path(outp),
                    overwrite=True,
                    output_format=self.format_var.get(),
                    video_codec=self.codec_var.get(),
                    video_crf=crf,
                    scale_height=scale_h,
                    fps=fps,
                    use_gpu=bool(self.use_gpu_var.get()),
                    include_audio=bool(self.include_audio_var.get()),
                    include_video_audio=bool(self.use_clip_audio_var.get()),
                    audio_clips=list(self._audio_track),
                    audio_bed_path=self._audio_bed_path,
                    transitions=self._transition_sequence(),
                    transition=transition_kind,
                    transition_duration=transition_dur,
                    video_filters=vfilters or None,
                    image_rotations=dict(self._media_rotations),
                    cancel_event=self._cancel,
                    progress_cb=lambda f, m: self.after(0, lambda: set_progress(f, m)),
                )
                self.after(0, lambda: done(res.ok, res.message, res.output_path))

            self._render_thread = threading.Thread(target=run_tl, daemon=True)
            self._render_thread.start()
            return

        req = self._build_request()
        if not req:
            return

        def run_single():
            res = edit_media(req, cancel_event=self._cancel, progress_cb=lambda f, m: self.after(0, lambda: set_progress(f, m)))
            self.after(0, lambda: done(res.ok, res.message, res.output_path))

        self._render_thread = threading.Thread(target=run_single, daemon=True)
        self._render_thread.start()

    def _cancel_render(self):
        self._cancel.set()
