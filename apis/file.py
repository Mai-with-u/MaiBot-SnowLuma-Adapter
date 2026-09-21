"""QQ 文件与流式 API 端点。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from maibot_sdk import API

from .support import QQApiParamsInput, QQApiSupportMixin


class QQFileApiMixin(QQApiSupportMixin):
    """QQ 文件、媒体与流式相关 API。"""

    @API("adapter.napcat.file.get_record", description="获取语音文件详情", version="1", public=True)
    async def api_get_record(
        self,
        file: object = "",
        file_id: str = "",
        out_format: str = "wav",
    ) -> Optional[Dict[str, Any]]:
        """获取语音文件详情。

        Args:
            file: 语音文件名。
            file_id: 可选文件 ID。
            out_format: 输出格式；默认保持兼容旧行为的 ``wav``。

        Returns:
            Optional[Dict[str, Any]]: 语音文件详情；失败时返回 ``None``。
        """
        normalized_file_name = str(file or "").strip() or None
        normalized_file_id = str(file_id or "").strip() or None
        normalized_out_format = str(out_format or "").strip()

        if normalized_file_name is None and normalized_file_id is None:
            raise ValueError("file 或 file_id 至少提供一个")

        return await self._require_query_service().get_record_detail(
            file_name=normalized_file_name,
            file_id=normalized_file_id,
            out_format=normalized_out_format,
        )

    @API("adapter.napcat.file.cancel_online_file", description="取消在线文件", version="1", public=True)
    async def api_action_cancel_online_file(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``cancel_online_file`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("cancel_online_file", params)

    @API("adapter.napcat.file.clean_stream_temp_file", description="清理流式传输临时文件", version="1", public=True)
    async def api_action_clean_stream_temp_file(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``clean_stream_temp_file`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("clean_stream_temp_file", params)

    @API("adapter.napcat.file.create_flash_task", description="创建闪传任务", version="1", public=True)
    async def api_action_create_flash_task(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``create_flash_task`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("create_flash_task", params)

    @API("adapter.napcat.file.create_group_file_folder", description="创建群文件目录", version="1", public=True)
    async def api_action_create_group_file_folder(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``create_group_file_folder`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("create_group_file_folder", params)

    @API("adapter.napcat.file.del_group_album_media", description="删除群相册媒体", version="1", public=True)
    async def api_action_del_group_album_media(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``del_group_album_media`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("del_group_album_media", params)

    @API("adapter.napcat.file.delete_group_file", description="删除群文件", version="1", public=True)
    async def api_action_delete_group_file(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``delete_group_file`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("delete_group_file", params)

    @API("adapter.napcat.file.delete_group_folder", description="删除群文件目录", version="1", public=True)
    async def api_action_delete_group_folder(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``delete_group_folder`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("delete_group_folder", params)

    @API("adapter.napcat.file.do_group_album_comment", description="发表群相册评论", version="1", public=True)
    async def api_action_do_group_album_comment(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``do_group_album_comment`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("do_group_album_comment", params)

    @API("adapter.napcat.file.download_file", description="下载文件", version="1", public=True)
    async def api_action_download_file(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``download_file`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("download_file", params)

    @API("adapter.napcat.file.download_file_image_stream", description="下载图片文件流", version="1", public=True)
    async def api_action_download_file_image_stream(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``download_file_image_stream`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("download_file_image_stream", params)

    @API("adapter.napcat.file.download_file_record_stream", description="下载语音文件流", version="1", public=True)
    async def api_action_download_file_record_stream(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``download_file_record_stream`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("download_file_record_stream", params)

    @API("adapter.napcat.file.download_file_stream", description="下载文件流", version="1", public=True)
    async def api_action_download_file_stream(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``download_file_stream`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("download_file_stream", params)

    @API("adapter.napcat.file.download_fileset", description="下载文件集", version="1", public=True)
    async def api_action_download_fileset(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``download_fileset`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("download_fileset", params)

    @API("adapter.napcat.file.get_file", description="获取文件", version="1", public=True)
    async def api_action_get_file(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_file`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_file", params)

    @API("adapter.napcat.file.get_fileset_id", description="获取文件集 ID", version="1", public=True)
    async def api_action_get_fileset_id(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_fileset_id`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_fileset_id", params)

    @API("adapter.napcat.file.get_fileset_info", description="获取文件集信息", version="1", public=True)
    async def api_action_get_fileset_info(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_fileset_info`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_fileset_info", params)

    @API("adapter.napcat.file.get_flash_file_list", description="获取闪传文件列表", version="1", public=True)
    async def api_action_get_flash_file_list(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_flash_file_list`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_flash_file_list", params)

    @API("adapter.napcat.file.get_flash_file_url", description="获取闪传文件链接", version="1", public=True)
    async def api_action_get_flash_file_url(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_flash_file_url`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_flash_file_url", params)

    @API("adapter.napcat.file.get_group_album_media_list", description="获取群相册媒体列表", version="1", public=True)
    async def api_action_get_group_album_media_list(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_group_album_media_list`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_group_album_media_list", params)

    @API("adapter.napcat.file.get_group_file_system_info", description="获取群文件系统信息", version="1", public=True)
    async def api_action_get_group_file_system_info(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_group_file_system_info`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_group_file_system_info", params)

    @API("adapter.napcat.file.get_group_file_url", description="获取群文件URL", version="1", public=True)
    async def api_action_get_group_file_url(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_group_file_url`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_group_file_url", params)

    @API("adapter.napcat.file.get_group_files_by_folder", description="获取群文件夹文件列表", version="1", public=True)
    async def api_action_get_group_files_by_folder(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_group_files_by_folder`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_group_files_by_folder", params)

    @API("adapter.napcat.file.get_group_root_files", description="获取群根目录文件列表", version="1", public=True)
    async def api_action_get_group_root_files(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_group_root_files`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_group_root_files", params)

    @API("adapter.napcat.file.get_image", description="获取图片", version="1", public=True)
    async def api_action_get_image(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_image`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_image", params)

    @API("adapter.napcat.file.get_online_file_msg", description="获取在线文件消息", version="1", public=True)
    async def api_action_get_online_file_msg(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_online_file_msg`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_online_file_msg", params)

    @API("adapter.napcat.file.get_private_file_url", description="获取私聊文件URL", version="1", public=True)
    async def api_action_get_private_file_url(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_private_file_url`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_private_file_url", params)

    @API("adapter.napcat.file.get_qun_album_list", description="获取群相册列表", version="1", public=True)
    async def api_action_get_qun_album_list(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_qun_album_list`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_qun_album_list", params)

    @API("adapter.napcat.file.get_share_link", description="获取文件分享链接", version="1", public=True)
    async def api_action_get_share_link(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``get_share_link`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("get_share_link", params)

    @API("adapter.napcat.file.move_group_file", description="移动群文件", version="1", public=True)
    async def api_action_move_group_file(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``move_group_file`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("move_group_file", params)

    @API("adapter.napcat.file.receive_online_file", description="接收在线文件", version="1", public=True)
    async def api_action_receive_online_file(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``receive_online_file`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("receive_online_file", params)

    @API("adapter.napcat.file.refuse_online_file", description="拒绝在线文件", version="1", public=True)
    async def api_action_refuse_online_file(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``refuse_online_file`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("refuse_online_file", params)

    @API("adapter.napcat.file.rename_group_file", description="重命名群文件", version="1", public=True)
    async def api_action_rename_group_file(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``rename_group_file`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("rename_group_file", params)

    @API("adapter.napcat.file.send_flash_msg", description="发送闪传消息", version="1", public=True)
    async def api_action_send_flash_msg(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``send_flash_msg`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("send_flash_msg", params)

    @API("adapter.napcat.file.send_online_file", description="发送在线文件", version="1", public=True)
    async def api_action_send_online_file(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``send_online_file`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("send_online_file", params)

    @API("adapter.napcat.file.send_online_folder", description="发送在线文件夹", version="1", public=True)
    async def api_action_send_online_folder(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``send_online_folder`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("send_online_folder", params)

    @API("adapter.napcat.file.set_group_album_media_like", description="点赞群相册媒体", version="1", public=True)
    async def api_action_set_group_album_media_like(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``set_group_album_media_like`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("set_group_album_media_like", params)

    @API("adapter.napcat.file.trans_group_file", description="传输群文件", version="1", public=True)
    async def api_action_trans_group_file(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``trans_group_file`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("trans_group_file", params)

    @API("adapter.napcat.file.upload_file_stream", description="上传文件流", version="1", public=True)
    async def api_action_upload_file_stream(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``upload_file_stream`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("upload_file_stream", params)

    @API("adapter.napcat.file.upload_group_file", description="上传群文件", version="1", public=True)
    async def api_action_upload_group_file(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``upload_group_file`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("upload_group_file", params)

    @API("adapter.napcat.file.upload_image_to_qun_album", description="上传图片到群相册", version="1", public=True)
    async def api_action_upload_image_to_qun_album(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``upload_image_to_qun_album`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("upload_image_to_qun_album", params)

    @API("adapter.napcat.file.upload_private_file", description="上传私聊文件", version="1", public=True)
    async def api_action_upload_private_file(self, params: QQApiParamsInput = None) -> Dict[str, Any]:
        """调用对端的 ``upload_private_file`` 动作。

        Args:
            params: 传递给 对端的动作参数字典；具体字段请参考对端官方文档。

        Returns:
            Dict[str, Any]: 对端返回的原始响应字典。
        """
        return await self._call_napcat_action("upload_private_file", params)
