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

        scope = server_config.connection_id or None
        if (
            self._runtime_state_connected
            and self._reported_account_id == normalized_account_id
            and self._reported_scope == scope
        ):
            return True

        accepted = False
        try:
            accepted = await self._gateway_capability.update_state(
                gateway_name=self._gateway_name,
                ready=True,
                platform="qq",
                account_id=normalized_account_id,
                scope=server_config.connection_id,
                metadata={"ws_url": server_config.build_ws_url()},
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
        self._logger.info(
            f"消息网关已激活路由: platform=qq account_id={normalized_account_id} "
            f"scope={self._reported_scope or '*'}"
        )
        return True

    async def report_disconnected(self) -> None:
        """向 Host 上报当前连接已断开，并撤销消息网关路由。"""

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
