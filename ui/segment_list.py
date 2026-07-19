"""分段卡片列表：QListWidget 承载 SegmentCardWidget，支持拖拽排序（InternalMove）。

拖拽结束后发射 order_changed，由主窗口按视觉顺序重排片段列表并重编号。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListWidget,
    QListWidgetItem,
    QWidget,
)


class SegmentListWidget(QListWidget):
    order_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("segmentList")
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setSpacing(8)

    def add_card(self, segment_id: str, card: QWidget) -> QListWidgetItem:
        """追加一个片段卡片，item 的 UserRole 记录 segment_id 用于顺序同步。"""
        item = QListWidgetItem(self)
        item.setData(Qt.ItemDataRole.UserRole, segment_id)
        item.setSizeHint(card.sizeHint())
        self.addItem(item)
        self.setItemWidget(item, card)
        return item

    def visual_segment_ids(self) -> list[str]:
        """当前视觉顺序下的 segment_id 列表。"""
        return [
            self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())
        ]

    def dropEvent(self, event) -> None:
        super().dropEvent(event)
        self.order_changed.emit()
