"""分段音轨的数据结构（Qt-free，可被任意层使用）。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class SegmentStatus(Enum):
    NOT_GENERATED = "not_generated"
    QUEUED = "queued"
    GENERATING = "generating"
    READY = "ready"
    ERROR = "error"


@dataclass
class SpeechSegment:
    """一个待配音片段。

    language / speaker / instruct 为可选覆盖项：None 表示跟随全局默认设置，
    非 None 时该片段生成时使用自己的值（见 TTSService.generate_segment）。
    """

    segment_id: str
    order: int
    text: str
    audio_path: Path | None = None
    status: SegmentStatus = SegmentStatus.NOT_GENERATED
    error_message: str | None = None
    language: str | None = None
    speaker: str | None = None
    instruct: str | None = None


def create_segments(texts: list[str]) -> list[SpeechSegment]:
    """把拆分后的文本列表转成带稳定 id 和顺序号的片段列表。"""
    return [
        SpeechSegment(segment_id=uuid.uuid4().hex[:8], order=i + 1, text=text)
        for i, text in enumerate(texts)
    ]
