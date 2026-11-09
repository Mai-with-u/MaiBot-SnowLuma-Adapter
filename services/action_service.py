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

from ..capabilities import require_standard_action

if TYPE_CHECKING:
    from ..profile import ProfileState
    from ..transport import QQTransportClient


class QQActionService:
    """QQ 底层动作与资源访问服务。"""

    def __init__(self, logger: Any, transport: "QQTransportClient", profile_state: "ProfileState") -> None:
        """初始化底层动作服务。

        Args:
            logger: 插件日志对象。
            transport: 传输层客户端。
            profile_state: 当前连接的客户端画像。
        """
        self._logger = logger
        self._transport = transport
        self._profile_state = profile_state

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
        if self._profile_state.profile.client_type == "onebot_v11":
            require_standard_action(action_name, normalized_params)
            # Host 使用字符串 ID，OneBot v11 标准动作要求数值 ID。
            for key in ("user_id", "group_id", "message_id"):
                if key not in normalized_params:
                    continue
                value = normalized_params[key]
                if isinstance(value, bool) or not isinstance(value, (str, int)):
                    raise ValueError(f"{action_name}.{key} 必须是整数 ID")
                normalized_params[key] = int(value)
        try:
            response = await self._transport.call_action(action_name, normalized_params)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise RuntimeError(f"对端动作执行失败: action={action_name} error={exc}") from exc

        if str(response.get("status") or "").lower() != "ok" or response.get("retcode", 0) != 0:
            error_message = str(response.get("wording") or response.get("message") or "unknown")
            raise RuntimeError(f"对端动作返回失败: action={action_name} message={error_message}")
        await self._confirm_group_delivery(action_name, normalized_params, response)
        return response

    async def _confirm_group_delivery(
        self, action_name: str, params: Mapping[str, Any], response: Mapping[str, Any]
    ) -> None:
        """SnowLuma 群消息必须取得真实群序号，不能将本地合成记录算作发送成功。"""

        if self._profile_state.profile.client_type != "snowluma":
            return
        is_group_send = action_name in {"send_group_msg", "send_group_forward_msg"} or (
            action_name in {"send_msg", "send_forward_msg"} and bool(params.get("group_id"))
        )
        if not is_group_send:
            return

        data = response.get("data")
        message_id = data.get("message_id") if isinstance(data, Mapping) else None
        if (
            isinstance(message_id, bool)
            or not isinstance(message_id, (int, str))
            or not str(message_id).removeprefix("-").isdigit()
            or int(message_id) == 0
        ):
            raise RuntimeError(f"群消息投递未确认: action={action_name} 对端未返回有效消息 ID")

        # get_msg 也会返回本地缓存，因此查询成功本身不是确认；必须检查真实序号及目标群。
        try:
            detail_response = await self._transport.call_action("get_msg", {"message_id": message_id})
        except Exception as exc:
            raise RuntimeError(
                f"群消息投递未确认: action={action_name} message_id={message_id} "
                f"查询回执失败: {type(exc).__name__}: {exc}；消息仍可能迟到，不应自动重发"
            ) from exc
        detail = detail_response.get("data")
        sequence = detail.get("message_seq") if isinstance(detail, Mapping) else None
        if (
            str(detail_response.get("status") or "").lower() != "ok"
            or detail_response.get("retcode", 0) != 0
            or not isinstance(detail, Mapping)
            or detail.get("message_type") != "group"
            or str(detail.get("group_id")) != str(params.get("group_id"))
            or str(detail.get("message_id")) != str(message_id)
            or isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence <= 0
        ):
            raise RuntimeError(
                f"群消息投递未确认: action={action_name} message_id={message_id} "
                "未取得对应群消息的真实序号；消息仍可能迟到，不应自动重发"
            )

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
        except NotImplementedError:
            raise
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
