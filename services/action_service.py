"""QQ 底层动作调用服务。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Mapping, Optional

import asyncio

try:
    from aiohttp import ClientSession, ClientTimeout

    AIOHTTP_AVAILABLE = True
except ImportError:
    ClientSession = None  # type: ignore[assignment]
    ClientTimeout = None  # type: ignore[assignment]
    AIOHTTP_AVAILABLE = False

if TYPE_CHECKING:
    from ..transport import QQTransportClient


class QQActionService:
    """QQ 底层动作与资源访问服务。"""

    def __init__(self, logger: Any, transport: "QQTransportClient") -> None:
        """初始化底层动作服务。

        Args:
            logger: 插件日志对象。
            transport: 传输层客户端。
        """
        self._logger = logger
        self._transport = transport

    async def call_action(self, action_name: str, params: Mapping[str, Any]) -> Dict[str, Any]:
        """调用 OneBot 动作并要求返回成功结果。

        Args:
            action_name: OneBot 动作名称。
            params: 动作参数。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。

        Raises:
            RuntimeError: 当动作执行失败或平台返回非成功状态时抛出。
        """
        normalized_params = {str(key): value for key, value in params.items()}
        try:
            response = await self._transport.call_action(action_name, normalized_params)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise RuntimeError(f"对端动作执行失败: action={action_name} error={exc}") from exc

        if str(response.get("status") or "").lower() != "ok":
            error_message = str(response.get("wording") or response.get("message") or "unknown")
            raise RuntimeError(f"对端动作返回失败: action={action_name} message={error_message}")
        return response

    async def call_action_data(self, action_name: str, params: Mapping[str, Any]) -> Any:
        """调用 OneBot 动作并返回 ``data`` 字段。

        Args:
            action_name: OneBot 动作名称。
            params: 动作参数。

        Returns:
            Any: 对端响应中的 ``data`` 字段。
        """
        response = await self.call_action(action_name, params)
        return response.get("data")

    async def safe_call_action_data(self, action_name: str, params: Mapping[str, Any]) -> Any:
        """安全调用 OneBot 动作并返回 ``data`` 字段。

        Args:
            action_name: OneBot 动作名称。
            params: 动作参数。

        Returns:
            Any: 响应中的 ``data`` 字段；失败时返回 ``None``。
        """
        try:
            return await self.call_action_data(action_name, params)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._logger.warning(f"查询动作执行失败: action={action_name} error={exc}")
            return None

    async def download_binary(self, url: str) -> Optional[bytes]:
        """下载远程二进制资源。

        Args:
            url: 资源 URL。

        Returns:
            Optional[bytes]: 下载到的二进制内容；失败时返回 ``None``。
        """
        if not url:
            return None
        if not AIOHTTP_AVAILABLE or ClientSession is None or ClientTimeout is None:
            self._logger.warning("查询层缺少 aiohttp，无法下载远程资源")
            return None

        try:
            timeout = ClientTimeout(total=15)
            async with ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        self._logger.warning(f"远程资源下载失败: status={response.status} url={url}")
                        return None
                    return await response.read()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._logger.warning(f"远程资源下载失败: {exc}")
            return None
