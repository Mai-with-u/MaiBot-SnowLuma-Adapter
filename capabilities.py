"""OneBot v11 标准模式的动作和出站消息边界。"""

from typing import Any, Mapping

from .cqcode import parse_cq_message

STANDARD_ACTIONS = frozenset({
    "send_private_msg", "send_group_msg", "send_msg", "delete_msg", "get_msg",
    "get_forward_msg", "send_like", "set_group_kick", "set_group_ban",
    "set_group_anonymous_ban", "set_group_whole_ban", "set_group_admin",
    "set_group_anonymous", "set_group_card", "set_group_name", "set_group_leave",
    "set_group_special_title", "set_friend_add_request", "set_group_add_request",
    "get_login_info", "get_stranger_info", "get_friend_list", "get_group_info",
    "get_group_list", "get_group_member_info", "get_group_member_list",
    "get_group_honor_info", "get_cookies", "get_csrf_token", "get_credentials",
    "get_record", "get_image", "can_send_image", "can_send_record", "get_status",
    "get_version_info", "set_restart", "clean_cache",
})

STANDARD_SEGMENTS = frozenset({
    "text", "face", "image", "record", "video", "at", "rps", "dice", "shake",
    "poke", "anonymous", "share", "contact", "location", "music", "reply",
    "forward", "node", "xml", "json",
})


def require_standard_action(action: str, params: Mapping[str, Any]) -> None:
    """在发送前拒绝厂商扩展；标准模式不试探性调用扩展 API。"""
    if action not in STANDARD_ACTIONS:
        raise NotImplementedError(f"OneBot v11 标准模式不支持扩展动作: {action}")
    if action not in {"send_msg", "send_group_msg", "send_private_msg"}:
        return
    message = params.get("message")
    if isinstance(message, str):
        message = parse_cq_message(message)
    if not isinstance(message, list):
        raise ValueError("发送消息必须是字符串或消息段数组")
    for segment in message:
        if not isinstance(segment, Mapping):
            raise ValueError("消息段必须为对象")
        if segment.get("type") not in STANDARD_SEGMENTS:
            raise NotImplementedError(f"OneBot v11 标准模式不支持消息段: {segment.get('type')}")
