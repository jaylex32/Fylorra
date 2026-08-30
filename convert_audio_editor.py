"""
Automatic converter: CustomTkinter Audio Editor → PySide6
Converts the entire audio_editor_dialog.py to PySide6 with Fylorra theme
"""

import re
from pathlib import Path

def convert_audio_editor():
    """Convert CustomTkinter audio editor to PySide6"""

    input_file = Path(__file__).parent / "gui" / "audio_editor_dialog.py"
    output_file = Path(__file__).parent / "gui" / "audio_editor_dialog_pyside.py"

    print(f"Reading: {input_file}")
    content = input_file.read_text(encoding='utf-8')

    # Track conversions
    conversions = []

    # 1. Imports
    content = re.sub(
        r'import tkinter as tk\n',
        '',
        content
    )
    content = re.sub(
        r'from tkinter import filedialog, messagebox\n',
        'from PySide6.QtWidgets import QFileDialog, QMessageBox\n',
        content
    )
    content = re.sub(
        r'import customtkinter as ctk\n',
        '''from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QWidget, QPushButton,
    QLineEdit, QLabel, QScrollArea, QFrame, QSplitter, QCheckBox, QComboBox,
    QSlider, QProgressBar, QSpinBox
)
from PySide6.QtCore import Qt, QTimer, Signal, QSize, QRect, QPoint, QThread
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QLinearGradient, QFont,
    QPalette, QIcon, QPixmap, QPainterPath, QImage
)
''',
        content
    )
    conversions.append("Imports converted")

    # 2. Class definition
    content = re.sub(
        r'class AudioEditorDialog\(ctk\.CTkToplevel\):',
        'class AudioEditorDialog(QDialog):',
        content
    )
    conversions.append("Class definition converted")

    # 3. __init__ method - window setup
    content = re.sub(
        r'super\(\).__init__\(parent\)',
        'super().__init__(parent)',
        content
    )
    content = re.sub(
        r'self\.title\("Audio Editor"\)',
        'self.setWindowTitle("Audio Editor - Fylorra")',
        content
    )
    content = re.sub(
        r'self\.geometry\("(\d+)x(\d+)"\)',
        r'self.resize(\1, \2)',
        content
    )
    content = re.sub(
        r'self\.minsize\((\d+), (\d+)\)',
        r'self.setMinimumSize(\1, \2)',
        content
    )

    # Remove tkinter-specific window attributes
    content = re.sub(
        r'self\.attributes\([^)]+\)[^\n]*\n',
        '',
        content
    )
    content = re.sub(
        r'self\.overrideredirect\([^)]+\)[^\n]*\n',
        '',
        content
    )
    conversions.append("Window initialization converted")

    # 4. Grid layout → QLayout
    # This requires more sophisticated parsing, so we'll add layout hints
    content = re.sub(
        r'\.grid_columnconfigure\((\d+), weight=(\d+)\)',
        r'# TODO: Use QHBoxLayout/QVBoxLayout with stretch factor \2 for column \1',
        content
    )
    content = re.sub(
        r'\.grid_rowconfigure\((\d+), weight=(\d+)\)',
        r'# TODO: Use QVBoxLayout with stretch factor \2 for row \1',
        content
    )
    conversions.append("Grid configuration comments added")

    # 5. Widget conversions
    widget_map = {
        r'ctk\.CTkFrame': 'QFrame',
        r'ctk\.CTkButton': 'QPushButton',
        r'ctk\.CTkLabel': 'QLabel',
        r'ctk\.CTkEntry': 'QLineEdit',
        r'ctk\.CTkSlider': 'QSlider',
        r'ctk\.CTkCheckBox': 'QCheckBox',
        r'ctk\.CTkOptionMenu': 'QComboBox',
        r'ctk\.CTkProgressBar': 'QProgressBar',
        r'ctk\.CTkCanvas': 'QWidget  # Custom paint widget',
        r'ctk\.StringVar': 'str  # Use regular string',
        r'ctk\.DoubleVar': 'float  # Use regular float',
        r'ctk\.BooleanVar': 'bool  # Use regular bool',
        r'tk\.Frame': 'QFrame',
        r'tk\.Label': 'QLabel',
        r'tk\.PanedWindow': 'QSplitter',
    }

    for old, new in widget_map.items():
        count = len(re.findall(old, content))
        if count > 0:
            content = re.sub(old, new, content)
            conversions.append(f"Converted {count}x {old} → {new}")

    # 6. Event bindings
    event_map = {
        r'\.bind\("<Button-1>",\s*([^)]+)\)': r'# TODO: Override mousePressEvent for \1',
        r'\.bind\("<B1-Motion>",\s*([^)]+)\)': r'# TODO: Override mouseMoveEvent for \1',
        r'\.bind\("<ButtonRelease-1>",\s*([^)]+)\)': r'# TODO: Override mouseReleaseEvent for \1',
        r'\.bind\("<Double-Button-1>",\s*([^)]+)\)': r'# TODO: Override mouseDoubleClickEvent for \1',
        r'\.bind\("<Configure>",\s*([^)]+)\)': r'# TODO: Override resizeEvent for \1',
        r'\.bind\("<Enter>",\s*([^)]+)\)': r'# TODO: Override enterEvent for \1',
        r'\.bind\("<Leave>",\s*([^)]+)\)': r'# TODO: Override leaveEvent for \1',
    }

    for old, new in event_map.items():
        content = re.sub(old, new, content)
    conversions.append("Event bindings converted to TODO comments")

    # 7. Command callbacks
    content = re.sub(
        r'command=([^\s,)]+)',
        r'clicked.connect(\1)  # TODO: Use .connect()',
        content
    )
    conversions.append("Command callbacks converted")

    # 8. after() → QTimer
    content = re.sub(
        r'self\.after\((\d+),\s*([^)]+)\)',
        r'QTimer.singleShot(\1, \2)',
        content
    )
    conversions.append("after() converted to QTimer.singleShot()")

    # 9. messagebox → QMessageBox
    content = re.sub(
        r'messagebox\.showinfo\(([^,]+),\s*([^,]+)',
        r'QMessageBox.information(self, \1, \2',
        content
    )
    content = re.sub(
        r'messagebox\.showerror\(([^,]+),\s*([^,]+)',
        r'QMessageBox.critical(self, \1, \2',
        content
    )
    content = re.sub(
        r'messagebox\.showwarning\(([^,]+),\s*([^,]+)',
        r'QMessageBox.warning(self, \1, \2',
        content
    )
    conversions.append("messagebox converted to QMessageBox")

    # 10. filedialog → QFileDialog
    content = re.sub(
        r'filedialog\.askopenfilenames\(',
        r'QFileDialog.getOpenFileNames(self, ',
        content
    )
    content = re.sub(
        r'filedialog\.askdirectory\(',
        r'QFileDialog.getExistingDirectory(self, ',
        content
    )
    content = re.sub(
        r'filedialog\.asksaveasfilename\(',
        r'QFileDialog.getSaveFileName(self, ',
        content
    )
    conversions.append("filedialog converted to QFileDialog")

    # 11. Grid/pack → layout comments
    content = re.sub(
        r'\.grid\(([^)]+)\)',
        r'# TODO: Add to layout - was grid(\1)',
        content
    )
    content = re.sub(
        r'\.pack\(([^)]+)\)',
        r'# TODO: Add to layout - was pack(\1)',
        content
    )
    conversions.append("Grid/pack converted to TODO comments")

    # 12. Configure → set methods
    content = re.sub(
        r'\.configure\(text=([^)]+)\)',
        r'.setText(\1)',
        content
    )
    content = re.sub(
        r'\.configure\(([^)]+)\)',
        r'# TODO: Convert configure(\1) to PySide6 setters',
        content
    )
    conversions.append("configure() converted")

    # 13. Add modern theme stylesheet
    theme_code = '''
# Fylorra Modern Theme
FYLORRA_THEME = """
QDialog {
    background-color: #1e1e1e;
    color: #ffffff;
}
QFrame {
    background-color: #252525;
    border-radius: 8px;
    border: 1px solid #3a3f46;
}
QPushButton {
    background-color: #2d2d2d;
    color: #ffffff;
    border: 1px solid #3a3f46;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #3a7fd5;
    border-color: #4a9eff;
}
QPushButton:pressed {
    background-color: #252525;
}
QLineEdit {
    background-color: #2d2d2d;
    color: #ffffff;
    border: 1px solid #3a3f46;
    border-radius: 6px;
    padding: 8px 12px;
}
QLineEdit:focus {
    border-color: #3a7fd5;
}
QLabel {
    color: #ffffff;
    background: transparent;
}
QSlider::groove:horizontal {
    background: #2d2d2d;
    height: 6px;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #3a7fd5;
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}
QSlider::handle:horizontal:hover {
    background: #4a9eff;
}
QComboBox {
    background-color: #2d2d2d;
    color: #ffffff;
    border: 1px solid #3a3f46;
    border-radius: 6px;
    padding: 6px 12px;
}
QCheckBox {
    color: #ffffff;
}
QProgressBar {
    background-color: #2d2d2d;
    border: 1px solid #3a3f46;
    border-radius: 4px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #3a7fd5;
    border-radius: 3px;
}
QScrollArea {
    border: none;
    background-color: transparent;
}
QScrollBar:vertical {
    background-color: #2d2d2d;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background-color: #3a3f46;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background-color: #3a7fd5;
}
"""
'''

    # Insert theme after imports
    content = re.sub(
        r'(from core\.time_parse import parse_timestamp_to_seconds)',
        r'\1\n\n' + theme_code,
        content
    )
    conversions.append("Modern theme stylesheet added")

    # 14. Apply theme in __init__
    content = re.sub(
        r'(def __init__\(self, parent[^)]*\):[^\n]*\n\s+super\(\).__init__\(parent\))',
        r'\1\n        self.setStyleSheet(FYLORRA_THEME)',
        content
    )
    conversions.append("Theme application added to __init__")

    # 15. Add note at top
    header_note = '''"""
AUTOMATICALLY CONVERTED FROM CUSTOMTKINTER TO PYSIDE6
Original: audio_editor_dialog.py (CustomTkinter)
Converted: audio_editor_dialog_pyside.py (PySide6)

NOTE: This is a PARTIAL automatic conversion. Manual work required:
- Layout management (grid → QHBoxLayout/QVBoxLayout/QGridLayout)
- Canvas operations → QPainter custom widgets
- Event handlers → override Qt event methods
- Var() objects → regular Python variables
- Complete testing of all features

Features preserved:
- Waveform rendering logic
- ffmpeg integration
- Audio playback
- All edit operations
- Export functionality
"""

'''

    content = header_note + content
    conversions.append("Header note added")

    # Write output
    output_file.write_text(content, encoding='utf-8')

    print(f"\n[OK] Conversion complete!")
    print(f"[OK] Output: {output_file}")
    print(f"\n[OK] Conversions performed:")
    for conv in conversions:
        print(f"  - {conv}")

    print(f"\n[WARNING] IMPORTANT: This is a PARTIAL conversion.")
    print(f"[WARNING] Manual work required:")
    print(f"  1. Convert all grid() calls to proper QLayout usage")
    print(f"  2. Create custom QWidget subclasses for canvas operations")
    print(f"  3. Implement event handlers (mouse, resize, etc.)")
    print(f"  4. Convert Var() objects to class attributes")
    print(f"  5. Test all features thoroughly")

    return output_file

if __name__ == "__main__":
    output = convert_audio_editor()
    print(f"\n[OK] Done! Check: {output}")
