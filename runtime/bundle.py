"""运行时组件容器。"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..codecs.inbound import QQInboundCodec
from ..codecs.notice import QQNoticeCodec
from ..codecs.outbound import QQOutboundCodec
from ..filters import QQNoticeFilter, QQRegexFilter
from ..heartbeat_monitor import QQHeartbeatMonitor
from ..profile import NAPCAT_PROFILE, ClientProfile, ProfileState
from ..runtime_state import QQRuntimeStateManager
from ..services import (
    QQActionService,
    QQBanStateStore,
    QQBanTracker,
    QQOfficialBotGuard,
    QQQueryService,
)
from ..transport import QQTransportClient


@dataclass
class QQRuntimeBundle:
    """运行时依赖集合。"""

    action_service: QQActionService
    ban_state_store: QQBanStateStore
    ban_tracker: QQBanTracker
    heartbeat_monitor: QQHeartbeatMonitor
    inbound_codec: QQInboundCodec
    notice_codec: QQNoticeCodec
    notice_filter: QQNoticeFilter
    official_bot_guard: QQOfficialBotGuard
    outbound_codec: QQOutboundCodec
    query_service: QQQueryService
    runtime_state: QQRuntimeStateManager
    regex_filter: QQRegexFilter
    transport: QQTransportClient
    profile_state: ProfileState = field(default_factory=lambda: ProfileState(NAPCAT_PROFILE))

    @property
    def profile(self) -> ClientProfile:
        """返回当前生效的客户端画像。"""

        return self.profile_state.profile
