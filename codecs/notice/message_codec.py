"""通知事件编解码器。"""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import uuid4

import time

from ...services import QQQueryService
from ...types import QQPayload, QQPayloadDict
from .enricher import QQNoticeEntityResolver
from .helpers import build_payload_digest, resolve_actor_user_id
from .meta_event_logger import QQMetaEventObserver
from .renderer import QQNoticeTextRenderer


class QQNoticeCodec:
    """QQ 通知事件编码器。"""

    def __init__(self, logger: Any, query_service: QQQueryService) -> None:
        """初始化通知事件编码器。

        Args:
            logger: 插件日志对象。
            query_service: QQ 查询服务。
        """
        self._entity_resolver = QQNoticeEntityResolver(query_service)
        self._meta_event_observer = QQMetaEventObserver(logger)
        self._renderer = QQNoticeTextRenderer()

    def clear_cache(self) -> None:
        """清空通知编解码层的短期缓存（断连时调用）。"""
        self._entity_resolver.clear_cache()

    async def build_notice_message_dict(self, payload: QQPayload) -> Optional[QQPayloadDict]:
        """将 ``notice`` 事件转换为 Host 可接受的消息字典。

        Args:
            payload: 对端推送的原始通知事件。

        Returns:
            Optional[QQPayloadDict]: 成功时返回标准 ``MessageDict``；无法识别时返回 ``None``。
        """
        notice_type = str(payload.get("notice_type") or "").strip()
        if not notice_type:
            return None

        group_id = str(payload.get("group_id") or "").strip()
        user_id = resolve_actor_user_id(payload)
        self_id = str(payload.get("self_id") or "").strip()

        user_info = await self._entity_resolver.build_user_info(group_id=group_id, user_id=user_id)
        group_info = await self._entity_resolver.build_group_info(group_id)
        notice_text = await self._renderer.build_notice_text(
            payload,
            self._entity_resolver.resolve_display_name,
            self_id,
        )
        if not notice_text:
            return None

        additional_config: Dict[str, Any] = {
            "self_id": self_id,
            "napcat_notice_type": notice_type,
            "napcat_notice_sub_type": str(payload.get("sub_type") or "").strip(),
            "napcat_notice_payload": dict(payload),
        }
        if group_id:
            additional_config["platform_io_target_group_id"] = group_id
        elif user_id:
            additional_config["platform_io_target_user_id"] = user_id

        message_info: Dict[str, Any] = {"user_info": user_info, "additional_config": additional_config}
        if group_info is not None:
            message_info["group_info"] = group_info

        timestamp_seconds = payload.get("time")
        if not isinstance(timestamp_seconds, (int, float)):
            timestamp_seconds = time.time()

        return {
            "message_id": f"qq-notice-{uuid4().hex}",
            "timestamp": str(float(timestamp_seconds)),
            "platform": "qq",
            "message_info": message_info,
            "raw_message": [{"type": "text", "data": notice_text}],
            "is_mentioned": False,
            "is_at": False,
            "is_emoji": False,
            "is_picture": False,
            "is_command": False,
            "is_notify": True,
            "session_id": "",
            "processed_plain_text": notice_text,
            "display_message": notice_text,
        }

    def build_notice_dedupe_key(self, payload: QQPayload) -> Optional[str]:
        """为 对端 ``notice`` 事件构造稳定的技术性去重键。

        Args:
            payload: 对端推送的原始通知事件。

        Returns:
            Optional[str]: 若可以构造稳定去重键则返回该键，否则返回 ``None``。
        """
        notice_type = str(payload.get("notice_type") or "").strip()
        if not notice_type:
            return None

        # 撤回通知的 message_id 是被撤回消息的 ID，不能与普通消息共用去重键。
        sub_type = str(payload.get("sub_type") or "").strip()
        payload_digest = build_payload_digest(payload)
        suffix = f":{sub_type}" if sub_type else ""
        return f"notice:{notice_type}{suffix}:{payload_digest}"

    async def handle_meta_event(self, payload: QQPayload) -> None:
        """处理 ``meta_event`` 事件的日志与状态观测。

        Args:
            payload: 对端推送的原始元事件。
        """
        await self._meta_event_observer.handle_meta_event(payload)
