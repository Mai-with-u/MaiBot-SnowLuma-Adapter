"""通知编解码公共辅助函数。"""

from __future__ import annotations

from hashlib import sha1
from typing import Any, Mapping, Optional

import json


def build_payload_digest(payload: Mapping[str, Any]) -> str:
    """对通知载荷生成稳定哈希。

    Args:
        payload: 原始通知载荷。

    Returns:
        str: 基于规范化 JSON 文本生成的 SHA-1 十六进制摘要。
    """
    normalized_payload = normalize_payload_value(payload)
    serialized_payload = json.dumps(
        normalized_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha1(serialized_payload.encode("utf-8")).hexdigest()


def normalize_optional_string(value: Any) -> Optional[str]:
    """将任意值规范化为可选字符串。

    Args:
        value: 待规范化的值。

    Returns:
        Optional[str]: 规范化后的字符串；若值为空则返回 ``None``。
    """
    if value is None:
        return None
    normalized_value = str(value).strip()
    return normalized_value if normalized_value else None


def normalize_payload_value(value: Any) -> Any:
    """将通知载荷递归规范化为稳定 JSON 结构。

    Args:
        value: 待规范化的任意值。

    Returns:
        Any: 仅包含 JSON 基础类型的稳定结构。
    """
    if isinstance(value, Mapping):
        return {
            str(key): normalize_payload_value(child_value)
            for key, child_value in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [normalize_payload_value(item) for item in value]
    if isinstance(value, set):
        normalized_items = [normalize_payload_value(item) for item in value]
        return sorted(normalized_items, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def resolve_actor_user_id(payload: Mapping[str, Any]) -> str:
    """解析通知事件中的操作者用户号。

    Args:
        payload: 原始通知事件。

    Returns:
        str: 规范化后的操作者用户号；无法确定时返回空字符串。
    """
    if bool(payload.get("is_natural_lift", False)):
        return ""
    actor_user_id = str(payload.get("operator_id") or payload.get("user_id") or "").strip()
    if actor_user_id == "0":
        return ""
    return actor_user_id
