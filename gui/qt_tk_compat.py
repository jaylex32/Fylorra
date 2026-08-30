"""
Minimal Tk/CustomTkinter compatibility layer backed by PySide6.
Used to keep legacy layout code while migrating to Qt.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPolygon, QPixmap, QCursor, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QFileDialog,
)


@dataclass
class TkEvent:
    x: int = 0
    y: int = 0
    x_root: int = 0
    y_root: int = 0
    state: int = 0
    widget: QWidget | None = None


class _TkVar:
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

    def _bind(self, cb):
        if cb not in self._watchers:
            self._watchers.append(cb)


class StringVar(_TkVar):
    def set(self, value):
        super().set("" if value is None else str(value))


class DoubleVar(_TkVar):
    def set(self, value):
        try:
            v = float(value)
        except Exception:
            v = 0.0
        super().set(v)


class BooleanVar(_TkVar):
    def set(self, value):
        super().set(bool(value))


def _pad_to_margins(padx, pady):
    def _pair(p):
        if isinstance(p, (tuple, list)):
            if len(p) == 2:
                return int(p[0]), int(p[1])
            if len(p) == 4:
                return int(p[0]), int(p[2])
        return int(p or 0), int(p or 0)

    def _pair_y(p):
        if isinstance(p, (tuple, list)):
            if len(p) == 2:
                return int(p[0]), int(p[1])
            if len(p) == 4:
                return int(p[1]), int(p[3])
        return int(p or 0), int(p or 0)

    left, right = _pair(padx)
    top, bottom = _pair_y(pady)
    return left, top, right, bottom


def _ensure_grid_layout(parent: QWidget) -> QGridLayout:
    layout = getattr(parent, "_grid_layout", None)
    if isinstance(layout, QGridLayout):
        return layout
    try:
        existing = parent.layout()
        if existing is not None:
            if isinstance(existing, QGridLayout):
                parent._grid_layout = existing
            return existing
    except Exception:
        pass
    layout = QGridLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    parent.setLayout(layout)
    parent._grid_layout = layout
    return layout


def _ensure_pack_layout(parent: QWidget, orientation: Qt.Orientation) -> QBoxLayout:
    layout = getattr(parent, "_pack_layout", None)
    if isinstance(layout, QBoxLayout):
        return layout
    try:
        existing = parent.layout()
        if isinstance(existing, QBoxLayout):
            parent._pack_layout = existing
            return existing
        if existing is not None:
            return existing
    except Exception:
        pass
    if orientation == Qt.Horizontal:
        layout = QHBoxLayout()
    else:
        layout = QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    parent.setLayout(layout)
    parent._pack_layout = layout
    return layout


class _BindMixin:
    def _init_bindings(self):
        self._tk_bindings = {}
        self._tk_bindings_ready = False

    def bind(self, sequence, func):
        if not hasattr(self, "_tk_bindings"):
            self._init_bindings()
        self._tk_bindings.setdefault(sequence, []).append(func)
        if not getattr(self, "_tk_bindings_ready", False):
            try:
                self.installEventFilter(self)
                self._tk_bindings_ready = True
            except Exception:
                pass

    def eventFilter(self, obj, event):
        try:
            handlers = getattr(self, "_tk_bindings", {})
            if not handlers:
                return super().eventFilter(obj, event)

            def fire(seq, ev):
                for cb in handlers.get(seq, []):
                    try:
                        cb(ev)
                    except Exception:
                        pass

            et = event.type()
            if et == event.Enter:
                fire("<Enter>", TkEvent(widget=self))
            elif et == event.Leave:
                fire("<Leave>", TkEvent(widget=self))
            elif et == event.Resize:
                fire("<Configure>", TkEvent(widget=self))
            elif et == event.MouseButtonPress:
                if event.button() == Qt.LeftButton:
                    gp = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
                    ev = TkEvent(
                        x=int(event.position().x()) if hasattr(event, "position") else int(event.x()),
                        y=int(event.position().y()) if hasattr(event, "position") else int(event.y()),
                        x_root=int(gp.x()),
                        y_root=int(gp.y()),
                        state=0x0001 if event.modifiers() & Qt.ShiftModifier else 0,
                        widget=self,
                    )
                    fire("<Button-1>", ev)
                    fire("<ButtonPress-1>", ev)
            elif et == event.MouseMove:
                if event.buttons() & Qt.LeftButton:
                    gp = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
                    ev = TkEvent(
                        x=int(event.position().x()) if hasattr(event, "position") else int(event.x()),
                        y=int(event.position().y()) if hasattr(event, "position") else int(event.y()),
                        x_root=int(gp.x()),
                        y_root=int(gp.y()),
                        state=0x0001 if event.modifiers() & Qt.ShiftModifier else 0,
                        widget=self,
                    )
                    fire("<B1-Motion>", ev)
            elif et == event.MouseButtonRelease:
                if event.button() == Qt.LeftButton:
                    gp = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
                    ev = TkEvent(
                        x=int(event.position().x()) if hasattr(event, "position") else int(event.x()),
                        y=int(event.position().y()) if hasattr(event, "position") else int(event.y()),
                        x_root=int(gp.x()),
                        y_root=int(gp.y()),
                        state=0x0001 if event.modifiers() & Qt.ShiftModifier else 0,
                        widget=self,
                    )
                    fire("<ButtonRelease-1>", ev)
            elif et == event.MouseButtonDblClick:
                if event.button() == Qt.LeftButton:
                    gp = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
                    ev = TkEvent(
                        x=int(event.position().x()) if hasattr(event, "position") else int(event.x()),
                        y=int(event.position().y()) if hasattr(event, "position") else int(event.y()),
                        x_root=int(gp.x()),
                        y_root=int(gp.y()),
                        state=0x0001 if event.modifiers() & Qt.ShiftModifier else 0,
                        widget=self,
                    )
                    fire("<Double-Button-1>", ev)
        except Exception:
            pass
        return super().eventFilter(obj, event)


class _LayoutMixin(_BindMixin):
    @property
    def master(self):
        try:
            return self.parent()
        except Exception:
            return None

    def grid(self, row=0, column=0, rowspan=1, columnspan=1, padx=0, pady=0, sticky=""):
        parent = self.parent()
        if not isinstance(parent, QWidget):
            return
        layout = _ensure_grid_layout(parent)
        target = self
        left, top, right, bottom = _pad_to_margins(padx, pady)
        wrapper = getattr(self, "_tk_wrapper", None)
        if left or top or right or bottom:
            if wrapper is None:
                wrapper = QWidget(parent)
                wlay = QGridLayout(wrapper)
                wlay.setContentsMargins(left, top, right, bottom)
                wlay.setSpacing(0)
                wlay.addWidget(self, 0, 0)
                wrapper._tk_child = self
                self._tk_wrapper = wrapper
            else:
                wlay = wrapper.layout()
                if isinstance(wlay, QGridLayout):
                    wlay.setContentsMargins(left, top, right, bottom)
            target = wrapper
        elif wrapper is not None:
            wlay = wrapper.layout()
            if isinstance(wlay, QGridLayout):
                wlay.setContentsMargins(0, 0, 0, 0)
            target = wrapper

        align = Qt.Alignment()
        if "n" in sticky:
            align |= Qt.AlignTop
        if "s" in sticky:
            align |= Qt.AlignBottom
        if "w" in sticky:
            align |= Qt.AlignLeft
        if "e" in sticky:
            align |= Qt.AlignRight
        if not align:
            align = Qt.AlignLeft | Qt.AlignTop
        if isinstance(layout, QGridLayout):
            layout.addWidget(target, int(row), int(column), int(rowspan), int(columnspan), align)
        elif isinstance(layout, QBoxLayout):
            layout.addWidget(target, 0, align)
        else:
            try:
                layout.addWidget(target)
            except Exception:
                pass
        target.show()

    def grid_configure(self, **kwargs):
        parent = self.parent()
        if not isinstance(parent, QWidget):
            return
        layout = _ensure_grid_layout(parent)
        if not isinstance(layout, QGridLayout):
            return
        target = getattr(self, "_tk_wrapper", None) or self
        idx = layout.indexOf(target)
        if idx < 0:
            try:
                self.grid(**kwargs)
            except Exception:
                pass
            return
        row, column, rowspan, columnspan = layout.getItemPosition(idx)
        row = kwargs.get("row", row)
        column = kwargs.get("column", column)
        rowspan = kwargs.get("rowspan", rowspan)
        columnspan = kwargs.get("columnspan", columnspan)
        padx = kwargs.get("padx", None)
        pady = kwargs.get("pady", None)
        sticky = kwargs.get("sticky", None)
        if padx is not None or pady is not None:
            left, top, right, bottom = _pad_to_margins(padx or 0, pady or 0)
            if getattr(self, "_tk_wrapper", None) is None and (left or top or right or bottom):
                wrapper = QWidget(parent)
                wlay = QGridLayout(wrapper)
                wlay.setContentsMargins(left, top, right, bottom)
                wlay.setSpacing(0)
                wlay.addWidget(self, 0, 0)
                wrapper._tk_child = self
                try:
                    layout.removeWidget(self)
                except Exception:
                    pass
                self._tk_wrapper = wrapper
                target = wrapper
            else:
                wrapper = getattr(self, "_tk_wrapper", None)
                if wrapper is not None:
                    wlay = wrapper.layout()
                    if isinstance(wlay, QGridLayout):
                        wlay.setContentsMargins(left, top, right, bottom)

        align = None
        try:
            item = layout.itemAt(idx)
            if item is not None:
                align = item.alignment()
        except Exception:
            align = None
        if sticky is not None:
            align = Qt.Alignment()
            if "n" in sticky:
                align |= Qt.AlignTop
            if "s" in sticky:
                align |= Qt.AlignBottom
            if "w" in sticky:
                align |= Qt.AlignLeft
            if "e" in sticky:
                align |= Qt.AlignRight
        if not align:
            align = Qt.AlignLeft | Qt.AlignTop
        layout.addWidget(target, int(row), int(column), int(rowspan), int(columnspan), align)
        target.show()

    def grid_remove(self):
        w = getattr(self, "_tk_wrapper", None)
        try:
            if w is not None:
                w.hide()
            else:
                self.hide()
        except Exception:
            pass

    def pack(self, side="top", fill=None, expand=False, padx=0, pady=0, anchor=None):
        parent = self.parent()
        if not isinstance(parent, QWidget):
            return
        orient = Qt.Horizontal if (side in ("left", "right")) else Qt.Vertical
        layout = _ensure_pack_layout(parent, orient)
        target = self
        left, top, right, bottom = _pad_to_margins(padx, pady)
        wrapper = getattr(self, "_tk_wrapper", None)
        if left or top or right or bottom:
            if wrapper is None:
                wrapper = QWidget(parent)
                wlay = QGridLayout(wrapper)
                wlay.setContentsMargins(left, top, right, bottom)
                wlay.setSpacing(0)
                wlay.addWidget(self, 0, 0)
                wrapper._tk_child = self
                self._tk_wrapper = wrapper
            else:
                wlay = wrapper.layout()
                if isinstance(wlay, QGridLayout):
                    wlay.setContentsMargins(left, top, right, bottom)
            target = wrapper
        elif wrapper is not None:
            wlay = wrapper.layout()
            if isinstance(wlay, QGridLayout):
                wlay.setContentsMargins(0, 0, 0, 0)
            target = wrapper
        alignment = Qt.Alignment()
        if anchor == "w":
            alignment = Qt.AlignLeft
        elif anchor == "e":
            alignment = Qt.AlignRight
        elif anchor == "n":
            alignment = Qt.AlignTop
        elif anchor == "s":
            alignment = Qt.AlignBottom
        stretch = 1 if expand else 0
        if isinstance(layout, QBoxLayout):
            layout.addWidget(target, stretch, alignment)
        elif isinstance(layout, QGridLayout):
            try:
                row = layout.rowCount()
                layout.addWidget(target, int(row), 0, alignment)
            except Exception:
                try:
                    layout.addWidget(target)
                except Exception:
                    pass
        else:
            try:
                layout.addWidget(target)
            except Exception:
                pass
        target.show()

    def pack_forget(self):
        w = getattr(self, "_tk_wrapper", None)
        try:
            if w is not None:
                w.hide()
            else:
                self.hide()
        except Exception:
            pass

    def place(self, x=0, y=0):
        try:
            self.move(int(x), int(y))
            self.show()
        except Exception:
            pass

    def winfo_children(self):
        try:
            parent = getattr(self, "_scroll_content", self)
            kids = []
            for c in parent.children():
                try:
                    if hasattr(c, "_tk_child"):
                        kids.append(c._tk_child)
                    elif isinstance(c, QWidget):
                        kids.append(c)
                except Exception:
                    continue
            return kids
        except Exception:
            return []

    def destroy(self):
        wrapper = getattr(self, "_tk_wrapper", None)
        if wrapper is not None:
            try:
                wrapper.setParent(None)
                wrapper.deleteLater()
            except Exception:
                pass
            self._tk_wrapper = None
            return
        try:
            self.setParent(None)
            self.deleteLater()
        except Exception:
            pass

    def lift(self):
        try:
            self.raise_()
        except Exception:
            pass

    def cget(self, key):
        k = str(key or "").lower()
        try:
            if k == "height":
                return int(self.height())
            if k == "width":
                return int(self.width())
            if k == "text" and hasattr(self, "text"):
                return str(self.text())
            if k == "state":
                return "normal" if self.isEnabled() else "disabled"
        except Exception:
            pass
        return None

    def grid_columnconfigure(self, index, weight=0, minsize=None):
        layout = _ensure_grid_layout(self)
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
        layout = _ensure_grid_layout(self)
        try:
            layout.setRowStretch(int(index), int(weight))
        except Exception:
            pass
        if minsize is not None:
            try:
                layout.setRowMinimumHeight(int(index), int(minsize))
            except Exception:
                pass

    def grid_propagate(self, _flag):
        try:
            self.setSizePolicy(self.sizePolicy().horizontalPolicy(), self.sizePolicy().verticalPolicy())
        except Exception:
            pass

    def configure(self, **kwargs):
        if "text" in kwargs:
            try:
                self.setText(kwargs["text"])
            except Exception:
                pass
        if "image" in kwargs:
            im = kwargs["image"]
            if hasattr(im, "pixmap"):
                im = im.pixmap
            if isinstance(im, QPixmap):
                try:
                    if isinstance(self, QPushButton):
                        self.setIcon(QIcon(im))
                        self.setIconSize(im.size())
                    elif isinstance(self, QLabel):
                        self.setPixmap(im)
                except Exception:
                    pass
            else:
                try:
                    if isinstance(self, QLabel):
                        self.clear()
                except Exception:
                    pass
        if "values" in kwargs and isinstance(self, QComboBox):
            vals = kwargs["values"] or []
            self.clear()
            self.addItems([str(v) for v in vals])
        if "state" in kwargs:
            st = str(kwargs["state"]).lower()
            try:
                self.setEnabled(st != "disabled")
            except Exception:
                pass
        if "width" in kwargs:
            try:
                self.setFixedWidth(int(kwargs["width"]))
            except Exception:
                pass
        if "height" in kwargs:
            try:
                self.setFixedHeight(int(kwargs["height"]))
            except Exception:
                pass

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


class CTkFrame(QFrame, _LayoutMixin):
    def __init__(self, parent=None, corner_radius=None, fg_color=None, width=None, height=None, **kwargs):
        parent = getattr(parent, "_scroll_content", parent)
        super().__init__(parent)
        self._init_bindings()
        if width:
            try:
                self.setFixedWidth(int(width))
            except Exception:
                pass
        if height:
            try:
                self.setFixedHeight(int(height))
            except Exception:
                pass
        if fg_color:
            self.setStyleSheet(f"background-color: {fg_color};")


class CTkLabel(QLabel, _LayoutMixin):
    def __init__(self, parent=None, text="", text_color=None, image=None, font=None, **kwargs):
        parent = getattr(parent, "_scroll_content", parent)
        super().__init__(text, parent)
        self._init_bindings()
        if font is not None:
            try:
                self.setFont(font)
            except Exception:
                pass
        if text_color:
            try:
                if isinstance(text_color, (tuple, list)):
                    text_color = text_color[0]
                self.setStyleSheet(f"color: {text_color};")
            except Exception:
                pass
        if image is not None:
            self.configure(image=image)


class CTkButton(QPushButton, _LayoutMixin):
    def __init__(self, parent=None, text="", image=None, width=None, height=None, fg_color=None, hover_color=None, command=None, **kwargs):
        parent = getattr(parent, "_scroll_content", parent)
        super().__init__(text, parent)
        self._init_bindings()
        if width:
            self.setFixedWidth(int(width))
        if height:
            self.setFixedHeight(int(height))
        if image is not None:
            im = image
            if hasattr(im, "pixmap"):
                im = im.pixmap
            if isinstance(im, QPixmap):
                self.setIcon(QIcon(im))
                self.setIconSize(im.size())
        base_style = ""
        if fg_color:
            base_style = f"QPushButton{{background-color:{fg_color};}}"
        if hover_color:
            base_style += f"QPushButton:hover{{background-color:{hover_color};}}"
        if base_style:
            self.setStyleSheet(base_style)
        if command:
            try:
                self.clicked.connect(command)
            except Exception:
                pass


class CTkEntry(QLineEdit, _LayoutMixin):
    def __init__(self, parent=None, textvariable=None, placeholder_text=None, width=None, height=None, **kwargs):
        parent = getattr(parent, "_scroll_content", parent)
        super().__init__(parent)
        self._init_bindings()
        self._var = textvariable
        if placeholder_text:
            self.setPlaceholderText(placeholder_text)
        if width:
            self.setFixedWidth(int(width))
        if height:
            self.setFixedHeight(int(height))
        if textvariable is not None:
            try:
                self.setText(textvariable.get() or "")
            except Exception:
                pass
            try:
                textvariable._bind(lambda v: self.setText("" if v is None else str(v)))
            except Exception:
                pass
        self.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self, text):
        if self._var is not None:
            try:
                self._var.set(text)
            except Exception:
                pass

    def bind(self, sequence, func):
        if sequence == "<Return>":
            try:
                self.returnPressed.connect(lambda: func(TkEvent(widget=self)))
            except Exception:
                pass
            return
        super().bind(sequence, func)


class CTkCheckBox(QCheckBox, _LayoutMixin):
    def __init__(self, parent=None, text="", variable=None, command=None, **kwargs):
        parent = getattr(parent, "_scroll_content", parent)
        super().__init__(text, parent)
        self._init_bindings()
        self._var = variable
        if variable is not None:
            try:
                self.setChecked(bool(variable.get()))
                variable._bind(lambda v: self.setChecked(bool(v)))
            except Exception:
                pass
        if command:
            self.stateChanged.connect(lambda _v: command())
        self.stateChanged.connect(self._on_state_changed)

    def _on_state_changed(self, val):
        if self._var is not None:
            try:
                self._var.set(bool(val))
            except Exception:
                pass


class CTkOptionMenu(QComboBox, _LayoutMixin):
    def __init__(self, parent=None, values=None, variable=None, width=None, command=None, **kwargs):
        parent = getattr(parent, "_scroll_content", parent)
        super().__init__(parent)
        self._init_bindings()
        self._var = variable
        if width:
            self.setFixedWidth(int(width))
        if values:
            self.addItems([str(v) for v in values])
        if variable is not None:
            try:
                current = str(variable.get())
                idx = self.findText(current)
                if idx >= 0:
                    self.setCurrentIndex(idx)
            except Exception:
                pass
        if command:
            self.currentTextChanged.connect(lambda _v: command(_v))
        self.currentTextChanged.connect(self._on_changed)

    def _on_changed(self, value):
        if self._var is not None:
            try:
                self._var.set(value)
            except Exception:
                pass


class CTkSlider(QSlider, _LayoutMixin):
    def __init__(self, parent=None, from_=0.0, to=1.0, number_of_steps=None, variable=None, command=None, width=None, **kwargs):
        parent = getattr(parent, "_scroll_content", parent)
        super().__init__(Qt.Horizontal, parent)
        self._init_bindings()
        self._var = variable
        self._min = float(from_)
        self._max = float(to)
        steps = int(number_of_steps or 100)
        self._steps = max(1, steps)
        self.setMinimum(0)
        self.setMaximum(self._steps)
        if width:
            self.setFixedWidth(int(width))
        if variable is not None:
            try:
                v = float(variable.get() or 0.0)
            except Exception:
                v = 0.0
            self.setValue(self._to_slider(v))
            variable._bind(lambda v: self.setValue(self._to_slider(float(v or 0.0))))
        if command:
            self.valueChanged.connect(lambda _v: command(self._from_slider()))
        self.valueChanged.connect(self._on_changed)

    def _to_slider(self, value: float) -> int:
        if self._max <= self._min:
            return 0
        frac = (float(value) - self._min) / (self._max - self._min)
        return int(round(max(0.0, min(1.0, frac)) * self._steps))

    def _from_slider(self) -> float:
        frac = float(self.value()) / float(self._steps)
        return self._min + frac * (self._max - self._min)

    def _on_changed(self, _v):
        if self._var is not None:
            try:
                self._var.set(self._from_slider())
            except Exception:
                pass


class CTkProgressBar(QProgressBar, _LayoutMixin):
    def __init__(self, parent=None, **kwargs):
        parent = getattr(parent, "_scroll_content", parent)
        super().__init__(parent)
        self._init_bindings()
        self.setRange(0, 100)
        self.setValue(0)

    def set(self, value: float):
        try:
            v = max(0.0, min(1.0, float(value))) * 100.0
        except Exception:
            v = 0.0
        self.setValue(int(round(v)))


class CTkScrollableFrame(QScrollArea, _LayoutMixin):
    def __init__(self, parent=None, corner_radius=None, height=None, **kwargs):
        parent = getattr(parent, "_scroll_content", parent)
        super().__init__(parent)
        self._init_bindings()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self._scroll_content = QWidget()
        self._scroll_layout = QGridLayout(self._scroll_content)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_layout.setSpacing(0)
        self.setWidget(self._scroll_content)
        if height:
            try:
                self.setFixedHeight(int(height))
            except Exception:
                pass

    def grid_columnconfigure(self, index, weight=0, minsize=None):
        try:
            self._scroll_layout.setColumnStretch(int(index), int(weight))
            if minsize is not None:
                self._scroll_layout.setColumnMinimumWidth(int(index), int(minsize))
        except Exception:
            pass

    def grid_rowconfigure(self, index, weight=0, minsize=None):
        try:
            self._scroll_layout.setRowStretch(int(index), int(weight))
            if minsize is not None:
                self._scroll_layout.setRowMinimumHeight(int(index), int(minsize))
        except Exception:
            pass


class CTkSegmentedButton(QWidget, _LayoutMixin):
    def __init__(self, parent=None, values=None, variable=None, command=None, **kwargs):
        parent = getattr(parent, "_scroll_content", parent)
        super().__init__(parent)
        self._init_bindings()
        self._var = variable
        self._command = command
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._buttons = []
        for v in values or []:
            btn = QPushButton(str(v), self)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, vv=v: self._on_select(vv))
            layout.addWidget(btn)
            self._buttons.append((v, btn))
        if variable is not None:
            try:
                self._set_active(variable.get())
            except Exception:
                pass

    def _set_active(self, value):
        for v, btn in self._buttons:
            btn.setChecked(str(v) == str(value))

    def _on_select(self, value):
        self._set_active(value)
        if self._var is not None:
            try:
                self._var.set(value)
            except Exception:
                pass
        if callable(self._command):
            try:
                self._command(value)
            except Exception:
                pass


class CTkImage:
    def __init__(self, light_image=None, dark_image=None, size=None):
        self.pixmap = None
        im = light_image or dark_image
        if im is None:
            return
        if isinstance(im, QPixmap):
            self.pixmap = im
            return
        try:
            if hasattr(im, "size"):
                if size:
                    im = im.resize(size)
                try:
                    if getattr(im, "mode", "") != "RGBA":
                        im = im.convert("RGBA")
                except Exception:
                    pass
                data = im.tobytes("raw", "RGBA")
                w, h = im.size
                from PySide6.QtGui import QImage

                qimg = QPixmap.fromImage(QImage(data, w, h, QImage.Format_RGBA8888))
                self.pixmap = qimg
        except Exception:
            self.pixmap = None


class CTkCanvas(QWidget, _LayoutMixin):
    def __init__(self, parent=None, height=None, highlightthickness=0, bg=None, **kwargs):
        parent = getattr(parent, "_scroll_content", parent)
        super().__init__(parent)
        self._init_bindings()
        if height:
            self.setFixedHeight(int(height))
        if bg:
            self.setStyleSheet(f"background-color: {bg};")
        self._items = []

    def delete(self, _item):
        if _item == "all":
            self._items = []
        else:
            try:
                idx = int(_item) - 1
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

    def paintEvent(self, event):
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
                poly = QPolygon()
                for i in range(0, len(points), 2):
                    try:
                        poly.append(QPoint(int(points[i]), int(points[i + 1])))
                    except Exception:
                        pass
                if fill:
                    painter.setBrush(QBrush(QColor(fill)))
                if outline:
                    painter.setPen(QPen(QColor(outline)))
                painter.drawPolygon(poly)
            elif itype == "image":
                _, x, y, _anchor, image, _kw = item
                pm = image
                if hasattr(pm, "pixmap"):
                    pm = pm.pixmap
                if isinstance(pm, QPixmap):
                    painter.drawPixmap(int(x), int(y), pm)


class TkFrame(QFrame, _LayoutMixin):
    def __init__(self, parent=None, bg=None, cursor=None, width=None, **kwargs):
        parent = getattr(parent, "_scroll_content", parent)
        super().__init__(parent)
        self._init_bindings()
        if bg:
            self.setStyleSheet(f"background-color: {bg};")
        if cursor:
            try:
                self.setCursor(QCursor(Qt.SplitHCursor))
            except Exception:
                pass
        if width:
            try:
                self.setFixedWidth(int(width))
            except Exception:
                pass


class TkPanedWindow(QSplitter, _LayoutMixin):
    def __init__(self, parent=None, orient="vertical", sashwidth=8, **kwargs):
        parent = getattr(parent, "_scroll_content", parent)
        orientation = Qt.Vertical if orient == "vertical" else Qt.Horizontal
        super().__init__(orientation, parent)
        self._init_bindings()
        self.setHandleWidth(int(sashwidth or 6))
        self.setChildrenCollapsible(False)

    def add(self, widget, minsize=None):
        self.addWidget(widget)
        if minsize:
            try:
                if self.orientation() == Qt.Vertical:
                    widget.setMinimumHeight(int(minsize))
                else:
                    widget.setMinimumWidth(int(minsize))
            except Exception:
                pass


class _FileDialog:
    @staticmethod
    def askopenfilename(parent=None, title="", filetypes=None):
        filters = []
        if filetypes:
            for name, patt in filetypes:
                if patt == "*.*":
                    filters.append("All Files (*.*)")
                else:
                    filters.append(f"{name} ({patt})")
        filt = ";;".join(filters) if filters else "All Files (*.*)"
        path, _ = QFileDialog.getOpenFileName(parent, title or "Open File", "", filt)
        return path

    @staticmethod
    def askopenfilenames(parent=None, title="", filetypes=None):
        filters = []
        if filetypes:
            for name, patt in filetypes:
                if patt == "*.*":
                    filters.append("All Files (*.*)")
                else:
                    filters.append(f"{name} ({patt})")
        filt = ";;".join(filters) if filters else "All Files (*.*)"
        paths, _ = QFileDialog.getOpenFileNames(parent, title or "Open Files", "", filt)
        return paths

    @staticmethod
    def asksaveasfilename(parent=None, title="", filetypes=None):
        filters = []
        if filetypes:
            for name, patt in filetypes:
                if patt == "*.*":
                    filters.append("All Files (*.*)")
                else:
                    filters.append(f"{name} ({patt})")
        filt = ";;".join(filters) if filters else "All Files (*.*)"
        path, _ = QFileDialog.getSaveFileName(parent, title or "Save File", "", filt)
        return path

    @staticmethod
    def askdirectory(parent=None, title=""):
        return QFileDialog.getExistingDirectory(parent, title or "Select Folder")


class _MessageBox:
    @staticmethod
    def showinfo(title, message, parent=None):
        QMessageBox.information(parent, title, message)

    @staticmethod
    def showwarning(title, message, parent=None):
        QMessageBox.warning(parent, title, message)

    @staticmethod
    def showerror(title, message, parent=None):
        QMessageBox.critical(parent, title, message)


def CTkFont(*args, **kwargs):
    size = kwargs.pop("size", None)
    weight = kwargs.pop("weight", None)
    family = kwargs.pop("family", None)
    font = QFont()
    if family:
        try:
            font.setFamily(str(family))
        except Exception:
            pass
    if size is not None:
        try:
            font.setPointSize(int(size))
        except Exception:
            pass
    if weight is not None:
        try:
            if isinstance(weight, str):
                w = weight.lower()
                if w == "bold":
                    font.setWeight(QFont.Bold)
                elif w == "black":
                    font.setWeight(QFont.Black)
                else:
                    font.setWeight(QFont.Normal)
            else:
                font.setWeight(int(weight))
        except Exception:
            pass
    return font


class ctk:
    CTkFrame = CTkFrame
    CTkButton = CTkButton
    CTkLabel = CTkLabel
    CTkEntry = CTkEntry
    CTkSlider = CTkSlider
    CTkCheckBox = CTkCheckBox
    CTkOptionMenu = CTkOptionMenu
    CTkScrollableFrame = CTkScrollableFrame
    CTkSegmentedButton = CTkSegmentedButton
    CTkProgressBar = CTkProgressBar
    CTkCanvas = CTkCanvas
    CTkImage = CTkImage
    StringVar = StringVar
    DoubleVar = DoubleVar
    BooleanVar = BooleanVar
    CTkFont = CTkFont


class tk:
    Frame = TkFrame
    PanedWindow = TkPanedWindow


filedialog = _FileDialog
messagebox = _MessageBox
