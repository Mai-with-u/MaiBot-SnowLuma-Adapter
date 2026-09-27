"""调试日志工具：原始报文打印与 base64 脱敏。

移植自 SnowLuma 适配器的 Ada 调试能力（core.py 的
``_dump_debug_payload`` / ``_compact_debug_*`` 系列），两端画像通用：
开启后按 info 级别记录入站原始消息段与出站实际发送的 action/params，
媒体类 base64 数据仅保留首尾片段，避免刷屏与日志膨胀。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping

BASE64_FIELD_NAMES = {
    "base64",
    "binary_data_base64",
    "image_base64",
    "emoji_base64",
    "audio_base64",
}

BASE64_HEAD_CHARS = 48
BASE64_TAIL_CHARS = 16


def compact_base64_text(text: str, head_chars: int = BASE64_HEAD_CHARS, tail_chars: int = BASE64_TAIL_CHARS) -> str:
    """压缩超长 base64 文本，仅保留首尾片段。

    Args:
        text: 原始 base64 字符串。
        head_chars: 保留的首部字符数。
        tail_chars: 保留的尾部字符数。

    Returns:
        str: 压缩后的展示文本。
    """
    if len(text) <= head_chars + tail_chars + 16:
        return text
    omitted_chars = len(text) - head_chars - tail_chars
    return f"{text[:head_chars]}...<base64省略 chars={omitted_chars}>...{text[-tail_chars:]}"


def compact_debug_string(value: str) -> str:
    """压缩单个字符串中的内联 base64 数据。

    识别 ``base64://`` 前缀与 ``data:...;base64,`` URL 两种载体。

    Args:
        value: 原始字符串。

    Returns:
        str: 脱敏后的字符串。
    """
    compacted = str(value or "")
    if "base64://" in compacted:
        prefix, _, payload = compacted.partition("base64://")
        compacted = f"{prefix}base64://{compact_base64_text(payload)}"
    if ";base64," in compacted:
        head, _, payload = compacted.rpartition(";base64,")
        compacted = f"{head};base64,{compact_base64_text(payload)}"
    return compacted


def compact_debug_payload(value: Any) -> Any:
    """递归压缩载荷中的 base64 数据。

    Args:
        value: 任意可 JSON 序列化的载荷。

    Returns:
        Any: 压缩后的载荷（新对象，不修改入参）。
    """
    if isinstance(value, Mapping):
        compacted_payload: Dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in BASE64_FIELD_NAMES and isinstance(item, str):
                compacted_payload[key_text] = compact_base64_text(item)
            else:
                compacted_payload[key_text] = compact_debug_payload(item)
        return compacted_payload
    if isinstance(value, List):
        return [compact_debug_payload(item) for item in value]
    if isinstance(value, str):
        return compact_debug_string(value)
    return value


def dump_debug_payload(payload: Mapping[str, Any]) -> str:
    """把载荷序列化为脱敏后的 JSON 文本。

    Args:
        payload: 待打印的载荷。

    Returns:
        str: 脱敏后的 JSON 字符串；序列化失败时退化为 ``str()`` 表示。
    """
    import json

    try:
        return json.dumps(compact_debug_payload(dict(payload)), ensure_ascii=False)
    except Exception:
        return str(compact_debug_payload(dict(payload)))


class AdaDebugLogger:
    """按配置开关打印入站/出站原始报文的调试日志器。"""

    def __init__(self, logger: Any, load_settings: Callable[[], Any]) -> None:
        """初始化调试日志器。

        Args:
            logger: 插件日志对象。
            load_settings: 返回当前生效插件配置的回调（跟随热更新）。
        """
        self._logger = logger
        self._load_settings = load_settings

    @property
    def inbound_enabled(self) -> bool:
        """返回是否启用了入站原始报文日志。"""

        return bool(self._load_settings().debug.enable_ada_debug_raw_message_log)

    @property
    def outbound_enabled(self) -> bool:
        """返回是否启用了出站原始报文日志。"""

        return bool(self._load_settings().debug.enable_ada_debug_raw_outbound_message_log)

    def log_raw_inbound(self, message_id: str, payload: Mapping[str, Any]) -> None:
        """记录一条入站消息的原始报文。

        Args:
            message_id: 平台消息 ID。
            payload: 入站事件原始载荷。
        """
        if not self.inbound_enabled:
            return
        self._logger.info(f"入站原始报文: message_id={message_id!r} payload={dump_debug_payload(payload)}")

    def log_raw_outbound(self, message_id: str, action: str, params: Mapping[str, Any]) -> None:
        """记录一条出站动作的原始参数（媒体已脱敏）。

        Args:
            message_id: Host 侧消息 ID。
            action: 即将发送的 OneBot 动作名。
            params: 动作参数。
        """
        if not self.outbound_enabled:
            return
        self._logger.info(
            f"出站原始发送段（媒体已缩略）: message_id={message_id!r} action={action!r} params={dump_debug_payload(params)}"
        )
