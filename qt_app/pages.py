from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


@dataclass(frozen=True)
class PageDef:
    key: str
    title: str
    subtitle: str
    icon: str


def build_placeholder_page(title: str, subtitle: str) -> QWidget:
    host = QFrame()
    host.setObjectName("PageHost")
    layout = QVBoxLayout(host)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(14)

    card = QFrame()
    card.setObjectName("PageCard")
    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(22, 18, 22, 18)
    card_layout.setSpacing(6)

    t = QLabel(title)
    t.setObjectName("PageTitle")
    s = QLabel(subtitle)
    s.setObjectName("PageSubTitle")

    card_layout.addWidget(t)
    card_layout.addWidget(s)

    filler = QLabel("This page is being migrated to Qt.\nThe backend is already available; UI is next.")
    filler.setAlignment(Qt.AlignTop | Qt.AlignLeft)
    filler.setStyleSheet("color:#b7bcc6;")
    card_layout.addSpacing(10)
    card_layout.addWidget(filler)

    layout.addWidget(card)
    layout.addStretch(1)
    return host

