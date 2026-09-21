"""运行时组件构建器。"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Coroutine

from ..codecs.inbound import QQInboundCodec
from ..codecs.notice import QQNoticeCodec
from ..codecs.outbound import QQOutboundCodec
from ..config import QQPluginSettings
from ..filters import QQChatFilter, QQNoticeFilter, QQRegexFilter
from ..heartbeat_monitor import QQHeartbeatMonitor
from ..profile import ProfileState
from ..runtime_state import QQRuntimeStateManager
from ..services import (
    QQActionService,
    QQBanStateStore,
    QQBanTracker,
    QQOfficialBotGuard,
    QQQueryService,
)
from ..transport import QQTransportClient
from .bundle import QQRuntimeBundle


class QQRuntimeBuilder:
    """按固定依赖图构建运行时组件。"""

    def __init__(self, gateway_capability: Any, logger: Any, gateway_name: str) -> None:
        """初始化运行时构建器。

        Args:
            gateway_capability: SDK 提供的消息网关能力对象。
            logger: 插件日志对象。
            gateway_name: 当前消息网关名称。
        """
        self._gateway_capability = gateway_capability
        self._logger = logger
        self._gateway_name = gateway_name

    def build(
        self,
        on_connection_opened: Callable[[], Coroutine[Any, Any, None]],
        on_connection_closed: Callable[[], Coroutine[Any, Any, None]],
        on_payload: Callable[[dict[str, Any]], Coroutine[Any, Any, None]],
        on_natural_lift: Callable[[dict[str, Any]], Awaitable[None]],
        on_heartbeat_timeout: Callable[[str], Awaitable[None]],
        profile_state: ProfileState,
        load_settings: Callable[[], QQPluginSettings],
    ) -> QQRuntimeBundle:
        """创建一套完整的运行时组件。

        Args:
            on_connection_opened: 连接建立回调。
            on_connection_closed: 连接断开回调。
            on_payload: 非 echo 载荷回调。
            on_natural_lift: 自然解除禁言回调。
            on_heartbeat_timeout: 心跳超时回调。
            profile_state: 当前连接的客户端画像容器。
            load_settings: 返回当前生效插件配置的回调。

        Returns:
            QQRuntimeBundle: 已完成依赖注入的运行时组件集合。
        """
        chat_filter = QQChatFilter(self._logger)
        notice_filter = QQNoticeFilter(self._logger)
        regex_filter = QQRegexFilter(self._logger)
        transport = QQTransportClient(
            logger=self._logger,
            on_connection_opened=on_connection_opened,
            on_connection_closed=on_connection_closed,
            on_payload=on_payload,
        )
        action_service = QQActionService(self._logger, transport)
        query_service = QQQueryService(action_service, self._logger)
        ban_state_store = QQBanStateStore(self._logger)
        inbound_codec = QQInboundCodec(self._logger, query_service, profile_state, load_settings)
        notice_codec = QQNoticeCodec(self._logger, query_service)
        runtime_state = QQRuntimeStateManager(
            gateway_capability=self._gateway_capability,
            logger=self._logger,
            gateway_name=self._gateway_name,
        )
        ban_tracker = QQBanTracker(
            logger=self._logger,
            query_service=query_service,
            on_natural_lift=on_natural_lift,
            state_store=ban_state_store,
        )
        heartbeat_monitor = QQHeartbeatMonitor(
            logger=self._logger,
            on_timeout=on_heartbeat_timeout,
        )
        official_bot_guard = QQOfficialBotGuard(self._logger, query_service)
        outbound_codec = QQOutboundCodec(profile_state)

        return QQRuntimeBundle(
            action_service=action_service,
            ban_state_store=ban_state_store,
            ban_tracker=ban_tracker,
            chat_filter=chat_filter,
            heartbeat_monitor=heartbeat_monitor,
            inbound_codec=inbound_codec,
            notice_codec=notice_codec,
            notice_filter=notice_filter,
            official_bot_guard=official_bot_guard,
            outbound_codec=outbound_codec,
            query_service=query_service,
            regex_filter=regex_filter,
            runtime_state=runtime_state,
            transport=transport,
            profile_state=profile_state,
        )
