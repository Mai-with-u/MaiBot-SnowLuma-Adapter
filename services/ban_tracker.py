"""QQ 群禁言状态跟踪服务。"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Mapping, Optional

import asyncio
import contextlib
import time

from .ban_state_store import QQBanRecord, QQBanStateStore
from .query_service import QQQueryService


class QQBanTracker:
    """QQ 群禁言状态跟踪器。"""

    def __init__(
        self,
        logger: Any,
        query_service: QQQueryService,
        on_natural_lift: Callable[[Dict[str, Any]], Awaitable[None]],
        state_store: QQBanStateStore,
    ) -> None:
        """初始化群禁言状态跟踪器。

        Args:
            logger: 插件日志对象。
            query_service: QQ 查询服务。
            on_natural_lift: 检测到自然解除禁言后的回调。
            state_store: 禁言状态存储仓库。
        """
        self._logger = logger
        self._query_service = query_service
        self._on_natural_lift = on_natural_lift
        self._state_store = state_store
        self._poll_task: Optional[asyncio.Task[None]] = None

    async def start(self) -> None:
        """启动禁言状态跟踪。"""
        await self._state_store.load()
        await self._refresh_records_from_remote()
        if self._poll_task is None or self._poll_task.done():
            self._poll_task = asyncio.create_task(self._poll_loop(), name="napcat_adapter.ban_tracker")

    async def stop(self) -> None:
        """停止禁言状态跟踪并落盘当前记录。"""
        poll_task = self._poll_task
        self._poll_task = None
        if poll_task is not None:
            poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await poll_task
        await self._state_store.persist()

    async def record_notice(self, payload: Mapping[str, Any]) -> None:
        """根据实际 notice 事件更新禁言状态。

        Args:
            payload: 对端推送的原始通知事件。
        """
        notice_type = str(payload.get("notice_type") or "").strip()
        if notice_type != "group_ban":
            return

        sub_type = str(payload.get("sub_type") or "").strip()
        group_id = str(payload.get("group_id") or "").strip()
        user_id = str(payload.get("user_id") or "0").strip() or "0"
        if not group_id:
            return

        if sub_type == "ban":
            duration = self._normalize_int(payload.get("duration"), default=-1)
            lift_time = -1 if user_id == "0" or duration <= 0 else int(time.time()) + duration
            await self._state_store.upsert(QQBanRecord(group_id=group_id, user_id=user_id, lift_time=lift_time))
            return

        if sub_type in {"lift_ban", "whole_lift_ban"}:
            await self._state_store.remove(group_id=group_id, user_id=user_id)

    async def _refresh_records_from_remote(self) -> None:
        """基于当前 QQ 平台状态校正本地禁言记录。"""
        for record in await self._state_store.snapshot():
            if record.user_id == "0":
                await self._refresh_whole_ban_record(record)
                continue
            await self._refresh_member_ban_record(record)

    async def _refresh_whole_ban_record(self, record: QQBanRecord) -> None:
        """刷新全体禁言记录。

        Args:
            record: 待刷新的禁言记录。
        """
        group_info = await self._query_service.get_group_info(record.group_id)
        if group_info is None:
            await self._emit_natural_lift(record)
            return

        group_all_shut = self._normalize_int(group_info.get("group_all_shut"), default=0)
        if group_all_shut == 0:
            await self._emit_natural_lift(record)

    async def _refresh_member_ban_record(self, record: QQBanRecord) -> None:
        """刷新成员禁言记录。

        Args:
            record: 待刷新的禁言记录。
        """
        member_info = await self._query_service.get_group_member_info(record.group_id, record.user_id, no_cache=True)
        if member_info is None:
            await self._emit_natural_lift(record)
            return

        shut_up_timestamp = self._normalize_int(member_info.get("shut_up_timestamp"), default=0)
        if shut_up_timestamp == 0:
            await self._emit_natural_lift(record)
            return

        if shut_up_timestamp != record.lift_time:
            await self._state_store.upsert(
                QQBanRecord(group_id=record.group_id, user_id=record.user_id, lift_time=shut_up_timestamp)
            )

    async def _poll_loop(self) -> None:
        """后台轮询自然解除禁言。"""
        while True:
            await asyncio.sleep(5.0)
            current_timestamp = int(time.time())
            for record in await self._state_store.snapshot():
                if record.user_id == "0":
                    await self._refresh_whole_ban_record(record)
                    continue
                if record.lift_time != -1 and record.lift_time <= current_timestamp:
                    await self._emit_natural_lift(record)

    async def _emit_natural_lift(self, record: QQBanRecord) -> None:
        """上报自然解除禁言事件。

        Args:
            record: 已解除的禁言记录。
        """
        removed_record = await self._state_store.pop(record.record_key)
        if removed_record is None:
            return

        payload: Dict[str, Any] = {
            "post_type": "notice",
            "notice_type": "group_ban",
            "sub_type": "whole_lift_ban" if record.user_id == "0" else "lift_ban",
            "group_id": record.group_id,
            "user_id": record.user_id,
            "operator_id": None,
            "time": time.time(),
            "is_natural_lift": True,
        }
        try:
            await self._on_natural_lift(payload)
        except Exception as exc:
            self._logger.warning(f"合成自然解除禁言回调失败: {exc}")

    @staticmethod
    def _normalize_int(value: Any, default: int) -> int:
        """将任意值规范化为整数。

        Args:
            value: 待规范化的值。
            default: 转换失败时的默认值。

        Returns:
            int: 规范化后的整数结果。
        """
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
