"""对端心跳监测。"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Mapping, Optional

import asyncio
import time


class QQHeartbeatMonitor:
    """对端心跳状态监测器。"""

    def __init__(
        self,
        logger: Any,
        on_timeout: Callable[[str], Awaitable[None]],
    ) -> None:
        """初始化心跳监测器。

        Args:
            logger: 插件日志对象。
            on_timeout: 当心跳长时间未更新时触发的异步回调。
        """
        self._logger = logger
        self._on_timeout = on_timeout
        self._last_heartbeat_at: float = 0.0
        self._interval_sec: float = 30.0
        self._self_id: str = ""
        self._check_task: Optional[asyncio.Task[None]] = None
        self._timeout_reported: bool = False

    async def start(self, self_id: str, default_interval_sec: float) -> None:
        """启动或刷新心跳监测。

        Args:
            self_id: 当前机器人账号 ID。
            default_interval_sec: 默认心跳间隔秒数。
        """
        normalized_self_id = str(self_id or "").strip()
        if normalized_self_id:
            self._self_id = normalized_self_id
        self._interval_sec = max(float(default_interval_sec or 30.0), 1.0)
        self._touch()
        if self._check_task is None or self._check_task.done():
            self._check_task = asyncio.create_task(
                self._check_loop(),
                name="napcat_adapter.heartbeat_monitor",
            )

    async def stop(self) -> None:
        """停止当前心跳监测循环。"""
        check_task = self._check_task
        self._check_task = None
        self._timeout_reported = False
        self._last_heartbeat_at = 0.0
        if check_task is not None:
            check_task.cancel()
            try:
                await check_task
            except asyncio.CancelledError:
                pass

    async def observe_meta_event(
        self,
        payload: Mapping[str, Any],
        default_interval_sec: float,
    ) -> None:
        """根据 对端 ``meta_event`` 更新心跳监测状态。

        Args:
            payload: 对端推送的元事件载荷。
            default_interval_sec: 当前配置中的默认心跳间隔秒数。
        """
        meta_event_type = str(payload.get("meta_event_type") or "").strip()
        if meta_event_type == "lifecycle":
            sub_type = str(payload.get("sub_type") or "").strip()
            if sub_type == "connect":
                await self.start(str(payload.get("self_id") or "").strip(), default_interval_sec)
            return

        if meta_event_type != "heartbeat":
            return

        self_id = str(payload.get("self_id") or "").strip()
        interval_sec = self._resolve_interval_sec(payload, default_interval_sec)
        status = payload.get("status", {})
        if not isinstance(status, Mapping):
            status = {}

        is_online = bool(status.get("online", False))
        is_good = bool(status.get("good", False))

        await self.start(self_id, interval_sec)
        self._interval_sec = interval_sec

        if is_online and is_good:
            self._touch()
            return

        if not is_online:
            self._logger.error(f"对端心跳显示 Bot {self._self_id or self_id or 'unknown'} 已离线")
        elif not is_good:
            self._logger.warning(f"对端心跳显示 Bot {self._self_id or self_id or 'unknown'} 状态异常")

    @staticmethod
    def _resolve_interval_sec(payload: Mapping[str, Any], default_interval_sec: float) -> float:
        """解析心跳间隔秒数。

        Args:
            payload: 对端推送的元事件载荷。
            default_interval_sec: 配置中的默认心跳间隔秒数。

        Returns:
            float: 规范化后的心跳间隔秒数。
        """
        interval_ms = payload.get("interval")
        if isinstance(interval_ms, (int, float)) and interval_ms > 0:
            return max(float(interval_ms) / 1000.0, 1.0)
        return max(float(default_interval_sec or 30.0), 1.0)

    def _touch(self) -> None:
        """刷新最近一次心跳时间戳。"""
        self._last_heartbeat_at = time.time()
        self._timeout_reported = False

    async def _check_loop(self) -> None:
        """持续检查心跳是否超时。"""
        while True:
            await asyncio.sleep(max(self._interval_sec, 1.0))
            if self._last_heartbeat_at <= 0:
                continue

            elapsed_sec = time.time() - self._last_heartbeat_at
            if elapsed_sec <= self._interval_sec * 2:
                continue

            if self._timeout_reported:
                continue

            self._timeout_reported = True
            self._logger.error(f"Bot {self._self_id or 'unknown'} 可能发生了连接断开、被下线，或者 对端心跳卡死")
            try:
                await self._on_timeout(self._self_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._logger.warning(f"对端心跳超时回调执行失败: {exc}")
