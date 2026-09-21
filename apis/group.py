"""QQ 群组与频道 API 端点。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from maibot_sdk import API

from .support import QQApiIdInput, QQApiSupportMixin, QQApiParamsInput


class QQGroupApiMixin(QQApiSupportMixin):
    """QQ 群组、频道与群扩展相关 API。"""

    @API("adapter.napcat.group.set_group_ban", description="设置群成员禁言", version="1", public=True)
    async def api_set_group_ban(
        self,
        group_id: QQApiIdInput,
        user_id: QQApiIdInput,
        duration: QQApiIdInput,
    ) -> Dict[str, Any]:
        """设置群成员禁言。

        Args:
            group_id: 群号。
            user_id: 用户号。
            duration: 禁言秒数。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        normalized_duration = self._normalize_non_negative_int(duration, "duration")
        if normalized_duration > 2592000:
            raise ValueError("duration 不能超过 2592000 秒")
        return await self._require_query_service().set_group_ban(
            group_id=self._normalize_positive_int(group_id, "group_id"),
            user_id=self._normalize_positive_int(user_id, "user_id"),
            duration=normalized_duration,
        )

    @API("adapter.napcat.group.set_group_whole_ban", description="设置群全体禁言", version="1", public=True)
    async def api_set_group_whole_ban(self, group_id: QQApiIdInput, enable: bool) -> Dict[str, Any]:
        """设置群全体禁言。

        Args:
            group_id: 群号。
            enable: 是否开启全体禁言。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._require_query_service().set_group_whole_ban(
            group_id=self._normalize_positive_int(group_id, "group_id"),
            enable=self._normalize_bool(enable, "enable"),
        )

    @API("adapter.napcat.group.set_group_kick", description="踢出单个群成员", version="1", public=True)
    async def api_set_group_kick(
        self,
        group_id: QQApiIdInput,
        user_id: QQApiIdInput,
        reject_add_request: bool = False,
    ) -> Dict[str, Any]:
        """踢出单个群成员。

        Args:
            group_id: 群号。
            user_id: 用户号。
            reject_add_request: 是否拒绝再次加群。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._require_query_service().set_group_kick(
            group_id=self._normalize_positive_int(group_id, "group_id"),
            user_id=self._normalize_positive_int(user_id, "user_id"),
            reject_add_request=bool(reject_add_request),
        )

    @API("adapter.napcat.group.set_group_kick_members", description="批量踢出群成员", version="1", public=True)
    async def api_set_group_kick_members(
        self,
        group_id: QQApiIdInput,
        user_id: object,
        reject_add_request: bool = False,
    ) -> Dict[str, Any]:
        """批量踢出群成员。

        Args:
            group_id: 群号。
            user_id: 用户号数组。
            reject_add_request: 是否拒绝再次加群。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._require_query_service().set_group_kick_members(
            group_id=self._normalize_positive_int(group_id, "group_id"),
            user_ids=self._normalize_user_id_list(user_id, "user_id"),
            reject_add_request=bool(reject_add_request),
        )

    @API("adapter.napcat.group.set_group_name", description="设置群名称", version="1", public=True)
    async def api_set_group_name(self, group_id: QQApiIdInput, group_name: object) -> Dict[str, Any]:
        """设置群名称。

        Args:
            group_id: 群号。
            group_name: 新群名称。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._require_query_service().set_group_name(
            group_id=self._normalize_positive_int(group_id, "group_id"),
            group_name=self._normalize_non_empty_string(group_name, "group_name"),
        )

    @API("adapter.napcat.group.get_group_info", description="获取群信息", version="1", public=True)
    async def api_get_group_info(self, group_id: QQApiIdInput) -> Optional[Dict[str, Any]]:
        """获取群信息。

        Args:
            group_id: 群号。

        Returns:
            Optional[Dict[str, Any]]: 群信息字典；失败时返回 ``None``。
        """
        return await self._require_query_service().get_group_info(
            str(self._normalize_positive_int(group_id, "group_id"))
        )

    @API("adapter.napcat.group.get_group_detail_info", description="获取群详细信息", version="1", public=True)
    async def api_get_group_detail_info(self, group_id: QQApiIdInput) -> Optional[Dict[str, Any]]:
        """获取群详细信息。

        Args:
            group_id: 群号。

        Returns:
            Optional[Dict[str, Any]]: 群详细信息字典；失败时返回 ``None``。
        """
        return await self._require_query_service().get_group_detail_info(
            str(self._normalize_positive_int(group_id, "group_id"))
        )

    @API("adapter.napcat.group.get_group_list", description="获取群列表", version="1", public=True)
    async def api_get_group_list(self, no_cache: bool = False) -> Optional[List[Dict[str, Any]]]:
        """获取群列表。

        Args:
            no_cache: 是否禁用缓存。

        Returns:
            Optional[List[Dict[str, Any]]]: 群信息列表；失败时返回 ``None``。
        """
        return await self._require_query_service().get_group_list(no_cache=bool(no_cache))

    @API("adapter.napcat.group.get_group_at_all_remain", description="获取群 @ 全体剩余次数", version="1", public=True)
    async def api_get_group_at_all_remain(self, group_id: QQApiIdInput) -> Optional[Dict[str, Any]]:
        """获取群 @ 全体剩余次数。

        Args:
            group_id: 群号。

        Returns:
            Optional[Dict[str, Any]]: 剩余次数信息；失败时返回 ``None``。
        """
        return await self._require_query_service().get_group_at_all_remain(
            str(self._normalize_positive_int(group_id, "group_id"))
        )

    @API("adapter.napcat.group.get_group_member_info", description="获取群成员信息", version="1", public=True)
    async def api_get_group_member_info(
        self,
        group_id: QQApiIdInput,
        user_id: QQApiIdInput,
        no_cache: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """获取群成员信息。

        Args:
            group_id: 群号。
            user_id: 用户号。
            no_cache: 是否禁用缓存。

        Returns:
            Optional[Dict[str, Any]]: 群成员信息字典；失败时返回 ``None``。
        """
        return await self._require_query_service().get_group_member_info(
            group_id=str(self._normalize_positive_int(group_id, "group_id")),
            user_id=str(self._normalize_positive_int(user_id, "user_id")),
            no_cache=bool(no_cache),
        )

    @API("adapter.napcat.group.get_group_member_list", description="获取群成员列表", version="1", public=True)
    async def api_get_group_member_list(
        self,
        group_id: QQApiIdInput,
        no_cache: bool = False,
    ) -> Optional[List[Dict[str, Any]]]:
        """获取群成员列表。

        Args:
            group_id: 群号。
            no_cache: 是否禁用缓存。

        Returns:
            Optional[List[Dict[str, Any]]]: 群成员信息列表；失败时返回 ``None``。
        """
        return await self._require_query_service().get_group_member_list(
            group_id=str(self._normalize_positive_int(group_id, "group_id")),
            no_cache=bool(no_cache),
        )

    @API("adapter.napcat.group.delete_essence_msg", description="移出精华消息", version="1", public=True)
    async def api_action_delete_essence_msg(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``delete_essence_msg`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("delete_essence_msg", params)

    @API("adapter.napcat.group.delete_group_notice", description="删除群公告", version="1", public=True)
    async def api_action_delete_group_notice(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``_del_group_notice`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("_del_group_notice", params)

    @API("adapter.napcat.group.get_essence_msg_list", description="获取群精华消息", version="1", public=True)
    async def api_action_get_essence_msg_list(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_essence_msg_list`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_essence_msg_list", params)

    @API("adapter.napcat.group.get_group_honor_info", description="获取群荣誉信息", version="1", public=True)
    async def api_action_get_group_honor_info(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_group_honor_info`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_group_honor_info", params)

    @API(
        "adapter.napcat.group.get_group_ignore_add_request",
        description="获取群被忽略的加群请求",
        version="1",
        public=True,
    )
    async def api_action_get_group_ignore_add_request(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_group_ignore_add_request`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_group_ignore_add_request", params)

    @API("adapter.napcat.group.get_group_ignored_notifies", description="获取群忽略通知", version="1", public=True)
    async def api_action_get_group_ignored_notifies(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_group_ignored_notifies`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_group_ignored_notifies", params)

    @API("adapter.napcat.group.get_group_info_ex", description="获取群详细信息 (扩展)", version="1", public=True)
    async def api_action_get_group_info_ex(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_group_info_ex`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_group_info_ex", params)

    @API("adapter.napcat.group.get_group_notice", description="获取群公告", version="1", public=True)
    async def api_action_get_group_notice(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``_get_group_notice`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("_get_group_notice", params)

    @API("adapter.napcat.group.get_group_shut_list", description="获取群禁言列表", version="1", public=True)
    async def api_action_get_group_shut_list(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_group_shut_list`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_group_shut_list", params)

    @API("adapter.napcat.group.get_group_system_msg", description="获取群系统消息", version="1", public=True)
    async def api_action_get_group_system_msg(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_group_system_msg`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_group_system_msg", params)

    @API("adapter.napcat.group.get_guild_list", description="获取频道列表", version="1", public=True)
    async def api_action_get_guild_list(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_guild_list`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_guild_list", params)

    @API("adapter.napcat.group.get_guild_service_profile", description="获取频道个人信息", version="1", public=True)
    async def api_action_get_guild_service_profile(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_guild_service_profile`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_guild_service_profile", params)

    @API("adapter.napcat.group.group_poke", description="发送戳一戳", version="1", public=True)
    async def api_action_group_poke(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``group_poke`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("group_poke", params)

    @API("adapter.napcat.group.handle_quick_operation_internal", description="处理快速操作", version="1", public=True)
    async def api_action_handle_quick_operation_internal(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``.handle_quick_operation`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action(".handle_quick_operation", params)

    @API("adapter.napcat.group.send_group_msg", description="发送群消息", version="1", public=True)
    async def api_action_send_group_msg(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``send_group_msg`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("send_group_msg", params)

    @API("adapter.napcat.group.send_group_notice", description="发送群公告", version="1", public=True)
    async def api_action_send_group_notice(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``_send_group_notice`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("_send_group_notice", params)

    @API("adapter.napcat.group.send_group_sign", description="群打卡", version="1", public=True)
    async def api_action_send_group_sign(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``send_group_sign`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("send_group_sign", params)

    @API("adapter.napcat.group.set_essence_msg", description="设置精华消息", version="1", public=True)
    async def api_action_set_essence_msg(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``set_essence_msg`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("set_essence_msg", params)

    @API("adapter.napcat.group.set_group_add_option", description="设置群加群选项", version="1", public=True)
    async def api_action_set_group_add_option(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``set_group_add_option`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("set_group_add_option", params)

    @API("adapter.napcat.group.set_group_add_request", description="处理加群请求", version="1", public=True)
    async def api_action_set_group_add_request(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``set_group_add_request`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("set_group_add_request", params)

    @API("adapter.napcat.group.set_group_admin", description="设置群管理员", version="1", public=True)
    async def api_action_set_group_admin(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``set_group_admin`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("set_group_admin", params)

    @API("adapter.napcat.group.set_group_card", description="设置群名片", version="1", public=True)
    async def api_action_set_group_card(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``set_group_card`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("set_group_card", params)

    @API("adapter.napcat.group.set_group_leave", description="退出群组", version="1", public=True)
    async def api_action_set_group_leave(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``set_group_leave`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("set_group_leave", params)

    @API("adapter.napcat.group.set_group_portrait", description="设置群头像", version="1", public=True)
    async def api_action_set_group_portrait(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``set_group_portrait`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("set_group_portrait", params)

    @API("adapter.napcat.group.set_group_remark", description="设置群备注", version="1", public=True)
    async def api_action_set_group_remark(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``set_group_remark`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("set_group_remark", params)

    @API(
        "adapter.napcat.group.set_group_robot_add_option", description="设置群机器人加群选项", version="1", public=True
    )
    async def api_action_set_group_robot_add_option(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``set_group_robot_add_option`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("set_group_robot_add_option", params)

    @API("adapter.napcat.group.set_group_search", description="设置群搜索选项", version="1", public=True)
    async def api_action_set_group_search(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``set_group_search`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("set_group_search", params)

    @API("adapter.napcat.group.set_group_sign", description="群打卡", version="1", public=True)
    async def api_action_set_group_sign(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``set_group_sign`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("set_group_sign", params)

    @API("adapter.napcat.group.set_group_special_title", description="设置专属头衔", version="1", public=True)
    async def api_action_set_group_special_title(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``set_group_special_title`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("set_group_special_title", params)

    @API("adapter.napcat.group.set_group_todo", description="设置群待办", version="1", public=True)
    async def api_action_set_group_todo(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``set_group_todo`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("set_group_todo", params)

    @API("adapter.napcat.file.test_download_stream", description="测试下载流", version="1", public=True)
    async def api_action_test_download_stream(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``test_download_stream`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("test_download_stream", params)
