"""QQ 系统与运行时 API 端点。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from maibot_sdk import API

from .support import QQApiParamsInput, QQApiSupportMixin


class QQSystemApiMixin(QQApiSupportMixin):
    """QQ 系统状态、凭证与运行控制相关 API。"""

    @API("adapter.napcat.system.get_login_info", description="获取当前登录账号信息", version="1", public=True)
    async def api_get_login_info(self) -> Optional[Dict[str, Any]]:
        """获取当前登录账号信息。

        Returns:
            Optional[Dict[str, Any]]: 登录信息字典；失败时返回 ``None``。
        """
        return await self._require_query_service().get_login_info()

    @API("adapter.napcat.system.bot_exit", description="退出登录", version="1", public=True)
    async def api_action_bot_exit(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``bot_exit`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("bot_exit", params)

    @API("adapter.napcat.system.can_send_image", description="是否可以发送图片", version="1", public=True)
    async def api_action_can_send_image(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``can_send_image`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("can_send_image", params)

    @API("adapter.napcat.system.can_send_record", description="是否可以发送语音", version="1", public=True)
    async def api_action_can_send_record(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``can_send_record`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("can_send_record", params)

    @API("adapter.napcat.system.check_url_safely", description="检查URL安全性", version="1", public=True)
    async def api_action_check_url_safely(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``check_url_safely`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("check_url_safely", params)

    @API("adapter.napcat.system.clean_cache", description="清理缓存", version="1", public=True)
    async def api_action_clean_cache(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``clean_cache`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("clean_cache", params)

    @API("adapter.napcat.system.get_credentials", description="获取登录凭证", version="1", public=True)
    async def api_action_get_credentials(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_credentials`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_credentials", params)

    @API("adapter.napcat.system.get_csrf_token", description="获取 CSRF Token", version="1", public=True)
    async def api_action_get_csrf_token(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_csrf_token`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_csrf_token", params)

    @API(
        "adapter.napcat.system.get_doubt_friends_add_request", description="获取可疑好友申请", version="1", public=True
    )
    async def api_action_get_doubt_friends_add_request(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_doubt_friends_add_request`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_doubt_friends_add_request", params)

    @API("adapter.napcat.system.get_model_show", description="获取机型显示", version="1", public=True)
    async def api_action_get_model_show(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``_get_model_show`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("_get_model_show", params)

    @API("adapter.napcat.system.get_online_clients", description="获取在线客户端", version="1", public=True)
    async def api_action_get_online_clients(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_online_clients`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_online_clients", params)

    @API("adapter.napcat.system.get_robot_uin_range", description="获取机器人 UIN 范围", version="1", public=True)
    async def api_action_get_robot_uin_range(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_robot_uin_range`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_robot_uin_range", params)

    @API("adapter.napcat.system.get_status", description="获取运行状态", version="1", public=True)
    async def api_action_get_status(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_status`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_status", params)

    @API("adapter.napcat.system.get_version_info", description="获取版本信息", version="1", public=True)
    async def api_action_get_version_info(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_version_info`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_version_info", params)

    @API("adapter.napcat.system.nc_get_packet_status", description="获取Packet状态", version="1", public=True)
    async def api_action_nc_get_packet_status(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``nc_get_packet_status`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("nc_get_packet_status", params)

    @API("adapter.napcat.system.nc_get_user_status", description="获取用户在线状态", version="1", public=True)
    async def api_action_nc_get_user_status(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``nc_get_user_status`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("nc_get_user_status", params)

    @API("adapter.napcat.system.send_packet", description="发送原始数据包", version="1", public=True)
    async def api_action_send_packet(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``send_packet`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("send_packet", params)

    @API(
        "adapter.napcat.system.set_doubt_friends_add_request", description="处理可疑好友申请", version="1", public=True
    )
    async def api_action_set_doubt_friends_add_request(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``set_doubt_friends_add_request`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("set_doubt_friends_add_request", params)

    @API("adapter.napcat.system.set_input_status", description="设置输入状态", version="1", public=True)
    async def api_action_set_input_status(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``set_input_status`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("set_input_status", params)

    @API("adapter.napcat.system.set_model_show", description="设置机型", version="1", public=True)
    async def api_action_set_model_show(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``_set_model_show`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("_set_model_show", params)

    @API("adapter.napcat.system.set_online_status", description="设置在线状态", version="1", public=True)
    async def api_action_set_online_status(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``set_online_status`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("set_online_status", params)

    @API("adapter.napcat.system.set_restart", description="重启服务", version="1", public=True)
    async def api_action_set_restart(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``set_restart`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("set_restart", params)

    @API("adapter.napcat.system.unknown_action", description="unknown", version="1", public=True)
    async def api_action_unknown_action(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``unknown`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("unknown", params)
