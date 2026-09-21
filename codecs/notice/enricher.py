"""通知事件资料补全器。"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from ...services import QQQueryService
from .helpers import normalize_optional_string

_DISPLAY_NAME_CACHE_MAX_ENTRIES = 512


class QQNoticeEntityResolver:
    """为通知事件补全用户和群资料。"""

    def __init__(self, query_service: QQQueryService) -> None:
        """初始化实体补全器。

        Args:
            query_service: QQ 查询服务。
        """
        self._query_service = query_service
        self._display_name_cache: Dict[Tuple[str, str], str] = {}

    async def resolve_display_name(self, group_id: str, user_id: str, default: str = "QQ用户") -> str:
        """解析通知文本中展示用的用户名（带缓存，移植自 SnowLuma 适配器）。

        Args:
            group_id: 群号；私聊为空字符串。
            user_id: 目标用户号；空取 ``default``，"0" 表示全体成员。
            default: 无法解析时的默认展示名。

        Returns:
            str: 展示名。
        """
        normalized_user_id = str(user_id or "").strip()
        if not normalized_user_id:
            return default
        if normalized_user_id == "0":
            return "全体成员"

        cache_key = (group_id, normalized_user_id)
        cached_name = self._display_name_cache.get(cache_key)
        if cached_name:
            return cached_name

        user_info = await self.build_user_info(group_id, normalized_user_id)
        display_name = str(user_info.get("user_cardname") or user_info.get("user_nickname") or normalized_user_id)
        if len(self._display_name_cache) >= _DISPLAY_NAME_CACHE_MAX_ENTRIES:
            self._display_name_cache.clear()
        self._display_name_cache[cache_key] = display_name
        return display_name

    def clear_cache(self) -> None:
        """清空展示名缓存（断连时调用，避免跨连接脏数据）。"""
        self._display_name_cache.clear()

    async def build_user_info(self, group_id: str, user_id: str) -> Dict[str, Optional[str]]:
        """构造通知消息的用户信息。

        Args:
            group_id: 群号；私聊或系统通知时为空字符串。
            user_id: 事件关联用户号。

        Returns:
            Dict[str, Optional[str]]: 规范化后的用户信息字典。
        """
        if not user_id:
            return {
                "user_id": "notice",
                "user_nickname": "系统通知",
                "user_cardname": None,
            }

        member_info: Optional[Dict[str, Any]]
        if group_id:
            member_info = await self._query_service.get_group_member_info(group_id, user_id)
        else:
            member_info = await self._query_service.get_stranger_info(user_id)

        if member_info is None:
            return {
                "user_id": user_id,
                "user_nickname": user_id,
                "user_cardname": None,
            }

        return {
            "user_id": user_id,
            "user_nickname": str(member_info.get("nickname") or user_id),
            "user_cardname": normalize_optional_string(member_info.get("card")),
        }

    async def build_group_info(self, group_id: str) -> Optional[Dict[str, str]]:
        """构造通知消息的群信息。

        Args:
            group_id: 群号。

        Returns:
            Optional[Dict[str, str]]: 群信息字典；若不是群通知则返回 ``None``。
        """
        if not group_id:
            return None

        group_info = await self._query_service.get_group_info(group_id)
        group_name = str(group_info.get("group_name") or f"group_{group_id}") if group_info else f"group_{group_id}"
        return {"group_id": group_id, "group_name": group_name}
