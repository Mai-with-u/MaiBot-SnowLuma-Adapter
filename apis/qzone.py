"""SnowLuma 专属 QZone API 端点。

仅 SnowLuma 客户端实现了 QZone 系列动作；画像能力位
``supports_qzone`` 不满足时，这些 API 显式报错而不是静默降级，
调用方（如 ai_draw 等插件）能准确感知当前连接的能力边界。
"""

from __future__ import annotations

from typing import Any, Dict

from maibot_sdk import API

from .support import QQApiParamsInput, QQApiSupportMixin


class QQQzoneApiMixin(QQApiSupportMixin):
    """QZone 相关 API（SnowLuma 画像限定）。"""

    def _ensure_qzone_supported(self) -> None:
        """校验当前连接画像支持 QZone API。

        Raises:
            RuntimeError: 当当前 client_type 不支持 QZone 时抛出。
        """
        runtime_bundle = self._require_runtime_bundle()
        if not runtime_bundle.profile.supports_qzone:
            raise RuntimeError(
                f"当前 client_type={runtime_bundle.profile.client_type} 不支持 QZone API；"
                "该能力仅在连接 SnowLuma 客户端时可用"
            )

    @API("adapter.napcat.qzone.get_qzone_msg_list", description="获取 QQ 空间说说列表", version="1", public=True)
    async def api_get_qzone_msg_list(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_qzone_msg_list`` 动作。

        Args:
            params: 传递给对端的动作参数字典；具体字段请参考对端文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        self._ensure_qzone_supported()
        return await self._call_napcat_action("get_qzone_msg_list", params)

    @API("adapter.napcat.qzone.get_qzone_feeds", description="获取 QQ 空间好友动态", version="1", public=True)
    async def api_get_qzone_feeds(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_qzone_feeds`` 动作。

        Args:
            params: 传递给对端的动作参数字典；具体字段请参考对端文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        self._ensure_qzone_supported()
        return await self._call_napcat_action("get_qzone_feeds", params)

    @API("adapter.napcat.qzone.send_qzone_msg", description="发表 QQ 空间说说", version="1", public=True)
    async def api_send_qzone_msg(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``send_qzone_msg`` 动作。

        Args:
            params: 传递给对端的动作参数字典；具体字段请参考对端文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        self._ensure_qzone_supported()
        return await self._call_napcat_action("send_qzone_msg", params)

    @API("adapter.napcat.qzone.delete_qzone_msg", description="删除 QQ 空间说说", version="1", public=True)
    async def api_delete_qzone_msg(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``delete_qzone_msg`` 动作。

        Args:
            params: 传递给对端的动作参数字典；具体字段请参考对端文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        self._ensure_qzone_supported()
        return await self._call_napcat_action("delete_qzone_msg", params)

    @API("adapter.napcat.qzone.like_qzone", description="点赞 QQ 空间说说", version="1", public=True)
    async def api_like_qzone(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``like_qzone`` 动作。

        Args:
            params: 传递给对端的动作参数字典；具体字段请参考对端文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        self._ensure_qzone_supported()
        return await self._call_napcat_action("like_qzone", params)

    @API("adapter.napcat.qzone.unlike_qzone", description="取消点赞 QQ 空间说说", version="1", public=True)
    async def api_unlike_qzone(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``unlike_qzone`` 动作。

        Args:
            params: 传递给对端的动作参数字典；具体字段请参考对端文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        self._ensure_qzone_supported()
        return await self._call_napcat_action("unlike_qzone", params)

    @API("adapter.napcat.qzone.comment_qzone", description="评论 QQ 空间说说", version="1", public=True)
    async def api_comment_qzone(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``comment_qzone`` 动作。

        Args:
            params: 传递给对端的动作参数字典；具体字段请参考对端文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        self._ensure_qzone_supported()
        return await self._call_napcat_action("comment_qzone", params)
