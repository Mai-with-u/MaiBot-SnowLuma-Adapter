"""QQ 账号与用户侧 API 端点。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import re

from maibot_sdk import API

from .support import QQApiIdInput, QQApiParamsInput, QQApiSupportMixin


class QQAccountApiMixin(QQApiSupportMixin):
    """QQ 账号、好友与资料相关 API。"""

    @API("adapter.avatar.get", description="获取独立用户或群头像资源", version="1", public=True)
    async def api_get_avatar(
        self, platform: str, target_id: str, target_type: str = "user",
        account_id: str = "", scope: str = "",
    ) -> Dict[str, Any]:
        """统一头像协议：只返回资源 URL，图片由 Host 按有效期独立缓存。"""
        if platform != "qq":
            return {"status": "unsupported"}
        if target_type not in {"user", "group"}:
            raise ValueError("target_type 必须为 user 或 group")
        # 官方机器人 OpenID 无法用于数字 QQ 号头像 URL，属于不支持的目标类型。
        normalized_target_id = target_id.strip()
        if re.fullmatch(r"[0-9A-Fa-f]{32}", normalized_target_id) and not normalized_target_id.isdecimal():
            return {"status": "unsupported"}
        normalized_id = self._normalize_positive_int(target_id, "target_id")
        url = (
            f"https://p.qlogo.cn/gh/{normalized_id}/{normalized_id}/640"
            if target_type == "group"
            else f"https://q1.qlogo.cn/g?b=qq&nk={normalized_id}&s=640"
        )
        return {"status": "available", "url": url, "expires_in": 86400}

    @API("adapter.napcat.account.set_qq_profile", description="设置 QQ 账号资料", version="1", public=True)
    async def api_set_qq_profile(
        self,
        nickname: object,
        personal_note: str = "",
        sex: str = "",
    ) -> Dict[str, Any]:
        """设置 QQ 账号资料。

        Args:
            nickname: 新昵称。
            personal_note: 个性签名。
            sex: 性别，支持 ``male``、``female``、``unknown``。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        normalized_sex = str(sex or "").strip().lower()
        if normalized_sex and normalized_sex not in {"male", "female", "unknown"}:
            raise ValueError("sex 必须为 male、female 或 unknown")
        return await self._require_query_service().set_qq_profile(
            nickname=self._normalize_non_empty_string(nickname, "nickname"),
            personal_note=str(personal_note or "").strip(),
            sex=normalized_sex,
        )

    @API("adapter.napcat.account.get_stranger_info", description="获取陌生人信息", version="1", public=True)
    async def api_get_stranger_info(
        self,
        user_id: QQApiIdInput,
        no_cache: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """获取陌生人信息。

        Args:
            user_id: 用户号。
            no_cache: 是否禁用缓存。

        Returns:
            Optional[Dict[str, Any]]: 陌生人信息字典；失败时返回 ``None``。
        """
        return await self._require_query_service().get_stranger_info(
            str(self._normalize_positive_int(user_id, "user_id")),
            no_cache=bool(no_cache),
        )

    @API("adapter.napcat.account.get_friend_list", description="获取好友列表", version="1", public=True)
    async def api_get_friend_list(self, no_cache: bool = False) -> Optional[List[Dict[str, Any]]]:
        """获取好友列表。

        Args:
            no_cache: 是否禁用缓存。

        Returns:
            Optional[List[Dict[str, Any]]]: 好友信息列表；失败时返回 ``None``。
        """
        return await self._require_query_service().get_friend_list(no_cache=bool(no_cache))

    @API("adapter.napcat.account.create_collection", description="创建收藏", version="1", public=True)
    async def api_action_create_collection(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``create_collection`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("create_collection", params)

    @API("adapter.napcat.account.delete_friend", description="删除好友", version="1", public=True)
    async def api_action_delete_friend(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``delete_friend`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("delete_friend", params)

    @API("adapter.napcat.account.fetch_custom_face", description="获取自定义表情", version="1", public=True)
    async def api_action_fetch_custom_face(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``fetch_custom_face`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("fetch_custom_face", params)

    @API("adapter.napcat.account.get_ai_characters", description="获取AI角色列表", version="1", public=True)
    async def api_action_get_ai_characters(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_ai_characters`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_ai_characters", params)

    @API("adapter.napcat.account.get_clientkey", description="获取ClientKey", version="1", public=True)
    async def api_action_get_clientkey(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_clientkey`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_clientkey", params)

    @API("adapter.napcat.account.get_collection_list", description="获取收藏列表", version="1", public=True)
    async def api_action_get_collection_list(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_collection_list`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_collection_list", params)

    @API("adapter.napcat.account.get_cookies", description="获取 Cookies", version="1", public=True)
    async def api_action_get_cookies(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_cookies`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_cookies", params)

    @API(
        "adapter.napcat.account.get_friends_with_category", description="获取带分组的好友列表", version="1", public=True
    )
    async def api_action_get_friends_with_category(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_friends_with_category`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_friends_with_category", params)

    @API("adapter.napcat.account.get_mini_app_ark", description="获取小程序 Ark", version="1", public=True)
    async def api_action_get_mini_app_ark(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_mini_app_ark`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_mini_app_ark", params)

    @API("adapter.napcat.account.get_profile_like", description="获取资料点赞", version="1", public=True)
    async def api_action_get_profile_like(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_profile_like`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_profile_like", params)

    @API("adapter.napcat.account.get_recent_contact", description="获取最近会话", version="1", public=True)
    async def api_action_get_recent_contact(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_recent_contact`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_recent_contact", params)

    @API("adapter.napcat.account.get_rkey", description="获取扩展 RKey", version="1", public=True)
    async def api_action_get_rkey(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_rkey`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_rkey", params)

    @API("adapter.napcat.account.get_rkey_server", description="获取 RKey 服务器", version="1", public=True)
    async def api_action_get_rkey_server(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_rkey_server`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_rkey_server", params)

    @API(
        "adapter.napcat.account.get_unidirectional_friend_list",
        description="获取单向好友列表",
        version="1",
        public=True,
    )
    async def api_action_get_unidirectional_friend_list(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_unidirectional_friend_list`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_unidirectional_friend_list", params)

    @API("adapter.napcat.account.internal_ocr_image", description="图片 OCR 识别 (内部)", version="1", public=True)
    async def api_action_internal_ocr_image(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``.ocr_image`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action(".ocr_image", params)

    @API("adapter.napcat.account.nc_get_rkey", description="获取 RKey", version="1", public=True)
    async def api_action_nc_get_rkey(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``nc_get_rkey`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("nc_get_rkey", params)

    @API("adapter.napcat.account.ocr_image", description="图片 OCR 识别", version="1", public=True)
    async def api_action_ocr_image(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``ocr_image`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("ocr_image", params)

    @API("adapter.napcat.account.send_like", description="点赞", version="1", public=True)
    async def api_action_send_like(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``send_like`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("send_like", params)

    @API("adapter.napcat.account.set_diy_online_status", description="设置自定义在线状态", version="1", public=True)
    async def api_action_set_diy_online_status(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``set_diy_online_status`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("set_diy_online_status", params)

    @API("adapter.napcat.account.set_friend_add_request", description="处理加好友请求", version="1", public=True)
    async def api_action_set_friend_add_request(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``set_friend_add_request`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("set_friend_add_request", params)

    @API("adapter.napcat.account.set_friend_remark", description="设置好友备注", version="1", public=True)
    async def api_action_set_friend_remark(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``set_friend_remark`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("set_friend_remark", params)

    @API("adapter.napcat.account.set_qq_avatar", description="设置QQ头像", version="1", public=True)
    async def api_action_set_qq_avatar(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``set_qq_avatar`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("set_qq_avatar", params)

    @API("adapter.napcat.account.set_self_longnick", description="设置个性签名", version="1", public=True)
    async def api_action_set_self_longnick(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``set_self_longnick`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("set_self_longnick", params)

    @API("adapter.napcat.account.translate_en2zh", description="英文单词翻译", version="1", public=True)
    async def api_action_translate_en2zh(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``translate_en2zh`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("translate_en2zh", params)
