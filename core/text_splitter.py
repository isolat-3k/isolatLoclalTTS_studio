"""长文本拆分：把长文本稳定地拆成接近目标长度的片段。

规则：
1. 按连续换行保留段落边界（段落之间绝不合并）；
2. 按句末标点 。！？!? 拆句；
3. 句子仍超长时用次级断点 ；;：:，, 再拆；
4. 极端长串（无可用断点）最后硬切；
5. 过短片段按顺序合并，使长度接近 max_chars；
6. 不丢失文本内容，片段仅做首尾空白清理，不修改正文。
"""

from __future__ import annotations

import re

MIN_MAX_CHARS = 40
MAX_MAX_CHARS = 500
DEFAULT_MAX_CHARS = 150

_PARAGRAPH_RE = re.compile(r"\n\s*\n+")
_SENTENCE_RE = re.compile(r"(?<=[。！？!?])")
_SECONDARY_RE = re.compile(r"(?<=[；;：:，,])")


def split_long_text(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    """把 text 拆分为长度不超过 max_chars 的片段列表；空文本返回 []。"""
    if not (MIN_MAX_CHARS <= max_chars <= MAX_MAX_CHARS):
        raise ValueError(
            f"max_chars 需在 {MIN_MAX_CHARS}~{MAX_MAX_CHARS} 之间，当前为 {max_chars}"
        )
    text = text.strip()
    if not text:
        return []

    chunks: list[str] = []
    for paragraph in _PARAGRAPH_RE.split(text):
        chunks.extend(_split_paragraph(paragraph, max_chars))
    return chunks


def _split_paragraph(paragraph: str, max_chars: int) -> list[str]:
    pieces: list[str] = []
    for sentence in _SENTENCE_RE.split(paragraph):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) <= max_chars:
            pieces.append(sentence)
            continue
        # 句子超长：先按次级断点拆，仍超长则硬切
        for part in _SECONDARY_RE.split(sentence):
            part = part.strip()
            if not part:
                continue
            if len(part) <= max_chars:
                pieces.append(part)
            else:
                pieces.extend(
                    part[i : i + max_chars] for i in range(0, len(part), max_chars)
                )
    return _merge_short_pieces(pieces, max_chars)


def _merge_short_pieces(pieces: list[str], max_chars: int) -> list[str]:
    merged: list[str] = []
    buf = ""
    for piece in pieces:
        if not buf:
            buf = piece
            continue
        candidate = buf + _join_sep(buf, piece) + piece
        if len(candidate) <= max_chars:
            buf = candidate
        else:
            merged.append(buf)
            buf = piece
    if buf:
        merged.append(buf)
    return merged


def _join_sep(left: str, right: str) -> str:
    """英文片段之间保留一个空格避免粘连；中文（非 ASCII 边界）不需要。"""
    if left[-1:].isascii() and right[:1].isascii():
        return " "
    return ""
