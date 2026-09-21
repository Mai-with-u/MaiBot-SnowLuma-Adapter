"""元事件日志处理器。"""

from __future__ import annotations

from typing import Any, Mapping


class QQMetaEventObserver:
    """处理 元事件的日志输出。"""

    def __init__(self, logger: Any) -> None:
        """初始化元事件观察器。

        Args:
            logger: 插件日志对象。
        """
        self._logger = logger

    async def handle_meta_event(self, payload: Mapping[str, Any]) -> None:
        """处理 ``meta_event`` 事件的日志与状态观测。

        Args:
            payload: 对端推送的原始元事件。
        """
        meta_event_type = str(payload.get("meta_event_type") or "").strip()
        self_id = str(payload.get("self_id") or "").strip() or "unknown"

        if meta_event_type == "lifecycle":
            sub_type = str(payload.get("sub_type") or "").strip()
            if sub_type == "connect":
                self._logger.info(f"元事件：Bot {self_id} 已建立连接")
            else:
                self._logger.debug(f"对端生命周期事件: self_id={self_id} sub_type={sub_type}")
            return

        if meta_event_type == "heartbeat":
            status = payload.get("status", {})
            if not isinstance(status, Mapping):
                status = {}
            is_online = bool(status.get("online", False))
            is_good = bool(status.get("good", False))
            interval_ms = payload.get("interval")
            self._logger.debug(
                f"对端心跳事件: self_id={self_id} online={is_online} good={is_good} interval={interval_ms}"
            )
            if not is_online:
                self._logger.warning(f"对端心跳显示 Bot {self_id} 已离线")
            elif not is_good:
                self._logger.warning(f"对端心跳显示 Bot {self_id} 状态异常")
