"""QQ 消息工具扩展。"""

from __future__ import annotations

from typing import Any, Dict

from maibot_sdk import Tool
from maibot_sdk.types import ToolParameterInfo, ToolParamType

from .message import QQMessageApiMixin


def _tool_param(name: str, param_type: ToolParamType, description: str, required: bool) -> ToolParameterInfo:
    """构造工具参数声明。"""

    return ToolParameterInfo(name=name, param_type=param_type, description=description, required=required)


@Tool(
    "find_user_qq_id",
    description="根据指定消息的 msg_id 查询该条消息发送者的 QQ 号信息",
    parameters=[
        _tool_param("msg_id", ToolParamType.STRING, "要查询的消息 ID", True),
    ],
)
async def handle_find_user_qq_id(self: QQMessageApiMixin, msg_id: str = "", **kwargs: Any) -> Dict[str, Any]:
    """根据消息 ID 查询发送者的 QQ 号信息。"""

    del kwargs

    normalized_msg_id = str(self._normalize_positive_int(msg_id, "msg_id"))
    message_detail = await self._require_query_service().get_message_detail(normalized_msg_id)
    if not isinstance(message_detail, dict):
        return {
            "success": False,
            "content": f"未找到 msg_id={normalized_msg_id} 对应的消息记录",
            "msg_id": normalized_msg_id,
        }

    sender = message_detail.get("sender", {})
    if not isinstance(sender, dict):
        sender = {}

    user_id = str(message_detail.get("user_id") or sender.get("user_id") or sender.get("uin") or "").strip()
    if not user_id:
        return {
            "success": False,
            "content": f"已获取消息详情，但未解析出 msg_id={normalized_msg_id} 的发送者 QQ 号",
            "msg_id": normalized_msg_id,
            "message_detail": message_detail,
        }

    nickname = str(sender.get("nickname") or sender.get("name") or "").strip()
    cardname = str(sender.get("card") or "").strip()
    sender_info = {
        "user_id": user_id,
        "nickname": nickname or None,
        "cardname": cardname or None,
    }
    display_name = cardname or nickname or user_id
    return {
        "success": True,
        "content": f"msg_id={normalized_msg_id} 的发送者 QQ 号是 {user_id}（显示名：{display_name}）",
        "msg_id": normalized_msg_id,
        "sender": sender_info,
    }


QQMessageApiMixin.handle_find_user_qq_id = handle_find_user_qq_id
