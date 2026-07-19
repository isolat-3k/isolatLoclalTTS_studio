"""全局样式表：现代浅色风格（圆角卡片、徽章配色、按钮 hover/pressed、滚动条美化）。"""

STYLE_SHEET = """
/* ---------- 基础 ---------- */
QMainWindow, QDialog {
    background: #f5f6fa;
}
QWidget {
    color: #2b2f36;
    font-size: 13px;
}
QLabel {
    background: transparent;
}

/* ---------- 分段卡片 ---------- */
QFrame#segmentCard {
    background: #ffffff;
    border: 1px solid #e2e5ec;
    border-radius: 10px;
}
QFrame#segmentCard[playing="true"] {
    border: 2px solid #4a7dff;
}
QLabel#cardOrderLabel {
    font-weight: 600;
}
QLabel#cardPreviewLabel {
    background: #f7f8fb;
    border-radius: 6px;
    padding: 4px;
    color: #3a3f4a;
}
QLabel#cardInfoLabel, QLabel#charCountLabel {
    color: #7a8090;
    font-size: 12px;
}
QLabel#cardOverrideLabel {
    color: #2b5cd7;
    font-size: 12px;
}

/* ---------- 状态徽章 ---------- */
QLabel#badgeNotGenerated {
    background: #e8eaef; color: #5a5f6a;
    border-radius: 9px; padding: 2px 10px;
}
QLabel#badgeQueued {
    background: #fdeec9; color: #8f6b1d;
    border-radius: 9px; padding: 2px 10px;
}
QLabel#badgeGenerating {
    background: #dbe7ff; color: #2b5cd7;
    border-radius: 9px; padding: 2px 10px;
}
QLabel#badgeReady {
    background: #d9f2e3; color: #1f7a46;
    border-radius: 9px; padding: 2px 10px;
}
QLabel#badgeError {
    background: #fbdedd; color: #b3261e;
    border-radius: 9px; padding: 2px 10px;
}

/* ---------- 按钮 ---------- */
QPushButton {
    background: #ffffff;
    border: 1px solid #d4d9e2;
    border-radius: 6px;
    padding: 6px 14px;
}
QPushButton:hover {
    background: #eef2ff;
    border-color: #b9c7f5;
}
QPushButton:pressed {
    background: #dbe4ff;
}
QPushButton:disabled {
    color: #a0a6b3;
    background: #f0f1f5;
    border-color: #e2e5ec;
}
QPushButton#primaryButton {
    background: #4a7dff;
    color: #ffffff;
    border: none;
}
QPushButton#primaryButton:hover { background: #3b6df0; }
QPushButton#primaryButton:pressed { background: #2b5cd7; }
QPushButton#primaryButton:disabled { background: #b9c7f5; }
QPushButton#dangerButton { color: #b3261e; }
QPushButton#dangerButton:hover {
    background: #fbdedd;
    border-color: #e5a39d;
}

/* ---------- 输入控件 ---------- */
QPlainTextEdit, QLineEdit, QComboBox {
    background: #ffffff;
    border: 1px solid #d4d9e2;
    border-radius: 6px;
    padding: 4px 6px;
    selection-background-color: #dbe7ff;
}
QPlainTextEdit:focus, QLineEdit:focus, QComboBox:focus {
    border: 1px solid #4a7dff;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #d4d9e2;
    selection-background-color: #dbe7ff;
    outline: none;
}

/* ---------- 分组框 ---------- */
QGroupBox {
    background: #fbfbfd;
    border: 1px solid #e2e5ec;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #5a5f6a;
}

/* ---------- 列表与分割条 ---------- */
QListWidget#segmentList {
    background: transparent;
    border: none;
}
QListWidget#segmentList::item {
    border: none;
    background: transparent;
}
QSplitter::handle {
    background: #e2e5ec;
}
QSplitter::handle:horizontal { width: 2px; }
QSplitter::handle:vertical { height: 2px; }

/* ---------- 滚动条 ---------- */
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #c9cedb;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #aab1c2; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: #c9cedb;
    border-radius: 5px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover { background: #aab1c2; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }

/* ---------- 提示 ---------- */
QToolTip {
    background: #ffffff;
    color: #2b2f36;
    border: 1px solid #d4d9e2;
    padding: 4px 6px;
}
"""
