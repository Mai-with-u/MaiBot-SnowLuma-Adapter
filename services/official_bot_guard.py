"""官方机器人消息拦截服务。

查询版（NapCat）：通过 ``get_group_member_info`` 的 ``is_robot`` 字段判断。
启发式兜底（移植自 SnowLuma 适配器）：当查询不可用或返回中缺少
``is_robot`` 字段时，按 payload / sender 的角色关键词尽力识别。
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

from .query_service import QQQueryService


class QQOfficialBotGuard:
    """根据群成员资料判断是否应拦截 QQ 官方机器人消息。"""

    def __init__(self, logger: Any, query_service: QQQueryService) -> None:
        """初始化官方机器人拦截服务。

        Args:
            logger: 插件日志对象。
            query_service: QQ 查询服务。
        """
        self._logger = logger
        self._query_service = query_service
        self._cache: Dict[str, bool] = {}

    def clear_cache(self) -> None:
        """清空机器人识别缓存。"""
        self._cache.clear()

    async def should_reject(
        self,
        sender_user_id: str,
        group_id: str,
        ban_qq_bot: bool,
        payload: Mapping[str, Any] | None = None,
        sender: Mapping[str, Any] | None = None,
    ) -> bool:
        """判断是否应拦截当前消息。

        Args:
            sender_user_id: 发送者用户号。
            group_id: 群号。
            ban_qq_bot: 是否启用官方机器人拦截。
            payload: 原始入站消息事件（启发式兜底时使用）。
            sender: 发送者信息字典（启发式兜底时使用）。

        Returns:
            bool: 若应拦截，则返回 ``True``。
        """
        if not ban_qq_bot or not group_id:
            return False

        cache_key = f"{group_id}:{sender_user_id}"
        cached_result = self._cache.get(cache_key)
        if cached_result is not None:
            if cached_result:
                self._logger.warning("QQ 官方机器人消息拦截已启用，消息被丢弃")
            return cached_result

        member_info = await self._query_service.get_group_member_info(group_id, sender_user_id, no_cache=True)
        if member_info is not None and "is_robot" in member_info:
            should_reject = bool(member_info.get("is_robot"))
            self._cache[cache_key] = should_reject
            if should_reject:
                self._logger.warning("QQ 官方机器人消息拦截已启用，消息被丢弃")
            return should_reject

        # 查询不可用或对端未返回 is_robot 字段时，退回 SnowLuma 适配器的 payload 启发式。
        if self._is_official_bot_payload(payload or {}, sender or {}):
            self._logger.warning("无法查询 is_robot 字段，已按 payload 启发式判定为官方机器人，消息被丢弃")
            self._cache[cache_key] = True
            return True

        self._logger.warning("无法获取用户是否为机器人，默认放行当前消息")
        self._cache[cache_key] = False
        return False

    @staticmethod
    def _is_official_bot_payload(payload: Mapping[str, Any], sender: Mapping[str, Any]) -> bool:
        """尽力识别 QQ 官方机器人或频道机器人消息（移植自 SnowLuma 适配器）。

        Args:
            payload: 原始入站消息事件。
            sender: 发送者信息字典。

        Returns:
            bool: 命中任一机器人特征时返回 ``True``。
        """
        role_values = {
            str(payload.get("sub_type") or "").lower(),
            str(payload.get("message_sub_type") or "").lower(),
            str(sender.get("role") or "").lower(),
            str(sender.get("user_type") or "").lower(),
        }
        if role_values & {"qq_bot", "official_bot", "bot", "guild"}:
            return True

        sender_title = str(sender.get("title") or sender.get("card") or sender.get("nickname") or "").lower()
        return "官方机器人" in sender_title or "qq bot" in sender_title
