"""解析 OneBot v11 字符串消息，按 CQ 码规则处理转义。"""

from typing import Any, Dict, List

import re


CQ_PATTERN = re.compile(r"\[CQ:([A-Za-z0-9_]+)((?:,[^\[\]]*)?)\]")


def _unescape(value: str, *, parameter: bool = False) -> str:
    """最后还原 &amp;，避免对已转义的 CQ 字面文本二次解码。"""
    value = value.replace("&#91;", "[").replace("&#93;", "]")
    if parameter:
        value = value.replace("&#44;", ",")
    return value.replace("&amp;", "&")


def parse_cq_message(message: str) -> List[Dict[str, Any]]:
    """保留文本顺序和空白，将 CQ 码转换为结构化消息段。"""
    segments: List[Dict[str, Any]] = []
    offset = 0
    for match in CQ_PATTERN.finditer(message):
        if match.start() > offset:
            segments.append({"type": "text", "data": {"text": _unescape(message[offset:match.start()])}})
        data: Dict[str, str] = {}
        parameters = match.group(2)
        if parameters:
            for entry in parameters[1:].split(","):
                key, separator, value = entry.partition("=")
                if not separator or not key or key in data:
                    raise ValueError(f"无效 CQ 码参数: {entry}")
                data[key] = _unescape(value, parameter=True)
        segments.append({"type": match.group(1), "data": data})
        offset = match.end()
    if offset < len(message):
        segments.append({"type": "text", "data": {"text": _unescape(message[offset:])}})
    return segments
