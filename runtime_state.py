"""消息网关运行时状态管理。"""

from typing import Any, Optional, Protocol

from .config import QQServerConfig


class _GatewayCapabilityProtocol(Protocol):
    """消息网关能力代理协议。"""

    async def update_state(
        self,
        gateway_name: str,
        *,
        ready: bool,
        platform: str = "",
        account_id: str = "",
        scope: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """向 Host 上报消息网关运行时状态。"""
        ...


class QQRuntimeStateManager:
    """消息网关路由状态上报器。"""

    def __init__(
        self,
        gateway_capability: _GatewayCapabilityProtocol,
        logger: Any,
        gateway_name: str,
    ) -> None:
        """初始化运行时状态管理器。

        Args:
            gateway_capability: SDK 提供的消息网关能力对象。
            logger: 插件日志对象。
            gateway_name: 当前 消息网关组件名称。
        """

        self._gateway_capability = gateway_capability
        self._gateway_name = gateway_name
        self._logger = logger
        self._runtime_state_connected: bool = False
        self._reported_account_id: Optional[str] = None
        self._reported_scope: Optional[str] = None
        self.detected_protocol: Optional[str] = None
        self._reported_protocol: Optional[str] = None
        self._routing_enabled = True
        self._reported_routing_enabled: Optional[bool] = True

    @property
    def account_id(self) -> Optional[str]:
        """返回底层连接账号；暂停 Host 收发路由时，身份查询仍需使用该账号。"""
        return self._reported_account_id if self._runtime_state_connected else None

    @property
    def scope(self) -> Optional[str]:
        """返回当前已就绪连接的作用域。"""
        return self._reported_scope if self._runtime_state_connected else None

    async def report_connected(self, account_id: str, server_config: QQServerConfig) -> bool:
        """向 Host 上报当前消息网关连接已就绪。

        Args:
            account_id: 当前 当前连接对应的机器人账号 ID。
            server_config: 当前生效的 对端服务端配置。

        Returns:
            bool: 若 Host 接受了运行时状态更新，则返回 ``True``。
        """

        normalized_account_id = str(account_id).strip()
        if not normalized_account_id:
            return False

        # 连接探测完成前不发布就绪状态，避免将配置画像当作实际客户端类型。
        if self.detected_protocol is None:
            return False

        scope = server_config.connection_id or None
        if (
            self._runtime_state_connected
            and self._reported_account_id == normalized_account_id
            and self._reported_scope == scope
            and self._reported_protocol == self.detected_protocol
            and self._reported_routing_enabled == self._routing_enabled
        ):
            return True

        accepted = False
        # 响应丢失时 Host 可能已经切换路由，下一次恢复必须重新上报，不能信任旧确认值。
        self._reported_routing_enabled = None
        try:
            accepted = await self._gateway_capability.update_state(
                gateway_name=self._gateway_name,
                ready=self._routing_enabled,
                platform="qq",
                account_id=normalized_account_id,
                scope=server_config.connection_id,
                metadata={
                    "ws_url": server_config.build_ws_url(),
                    "protocol": self.detected_protocol,
                },
            )
        except Exception as exc:
            self._logger.warning(f"消息网关上报连接就绪状态失败: {exc}")
            return False

        if not accepted:
            self._logger.warning("消息网关连接已建立，但 Host 未接受运行时状态更新")
            return False

        self._runtime_state_connected = True
        self._reported_account_id = normalized_account_id
        self._reported_scope = scope
        self._reported_protocol = self.detected_protocol
        self._reported_routing_enabled = self._routing_enabled
        self._logger.info(
            f"消息网关{'已激活' if self._routing_enabled else '已暂停'}收发路由: platform=qq account_id={normalized_account_id} "
            f"scope={self._reported_scope or '*'}"
        )
        return True

    async def set_routing_enabled(self, enabled: bool, server_config: QQServerConfig) -> None:
        """独立控制 Host 路由，保留底层连接和查询身份；心跳不得意外恢复暂停的路由。"""
        self._routing_enabled = enabled
        account_id = self.account_id
        if account_id is not None and not await self.report_connected(account_id, server_config):
            raise RuntimeError("Host 未接受 QQ 连接器收发路由切换")

    async def report_disconnected(self) -> None:
        """向 Host 上报当前连接已断开，并撤销消息网关路由。"""

        self._routing_enabled = True
        self._reported_routing_enabled = True
        if not self._runtime_state_connected:
            self._reported_account_id = None
            self._reported_scope = None
            return

        try:
            await self._gateway_capability.update_state(
                gateway_name=self._gateway_name,
                ready=False,
                platform="qq",
            )
        except Exception as exc:
            self._logger.warning(f"消息网关上报断开状态失败: {exc}")
        finally:
            self._runtime_state_connected = False
            self._reported_account_id = None
            self._reported_scope = None
