"""出站消息编解码：把 Host 出站消息构造为有序的 OneBot 动作序列。

统一采用动作列表模型（NapCat 的单动作是长度为 1 的特例）：
- SnowLuma 画像把文件段拆成独立 ``upload_group_file`` / ``upload_private_file``
  动作并保持与文本段的相对顺序；
- 画像的文件段保持内联 ``file`` 段随消息一起发送；
- 合并转发动作的参数键按画像取 ``message``（NapCat）或 ``messages``（SnowLuma）；
- 发送动作按画像取 ``send_group_msg`` / ``send_private_msg``（targeted）
  或通用 ``send_msg`` + ``message_type``（generic，SnowLuma）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Tuple

from ...profile import MSG_ACTION_STYLE_GENERIC
from .segment_encoder import QQOutboundSegmentEncoder

OutboundAction = Tuple[str, Dict[str, Any]]

SYNTHETIC_MESSAGE_ID_PREFIX = "qq-"


class QQOutboundCodec:
    """出站消息编码器。"""

    def __init__(self, profile_state: Any) -> None:
        """初始化出站消息编码器。

        Args:
            profile_state: 当前连接的客户端画像容器。
        """
        self._segment_encoder = QQOutboundSegmentEncoder()
        self._profile_state = profile_state

    def build_outbound_actions(
        self,
        message: Mapping[str, Any],
        route: Mapping[str, Any],
    ) -> List[OutboundAction]:
        """为 Host 出站消息构造有序动作序列。

        Args:
            message: Host 侧标准 ``MessageDict``。
            route: Platform IO 路由信息。

        Returns:
            List[OutboundAction]: 按发送顺序排列的 ``(动作名, 参数)`` 列表。

        Raises:
            ValueError: 当私聊出站缺少目标用户 ID 或消息不含可发送内容时抛出。
        """
        message_info = message.get("message_info", {})
        if not isinstance(message_info, Mapping):
            message_info = {}

        group_info = message_info.get("group_info", {})
        if not isinstance(group_info, Mapping):
            group_info = {}

        additional_config = message_info.get("additional_config", {})
        if not isinstance(additional_config, Mapping):
            additional_config = {}

        raw_message = message.get("raw_message", [])

        target_group_id = str(
            group_info.get("group_id")
            or additional_config.get("platform_io_target_group_id")
            or route.get("group_id")
            or route.get("target_group_id")
            or ""
        ).strip()

        target_user_id = str(
            additional_config.get("platform_io_target_user_id")
            or additional_config.get("target_user_id")
            or route.get("user_id")
            or route.get("target_user_id")
            or ""
        ).strip()

        if self._contains_forward_segment(raw_message):
            return [self._build_forward_action(raw_message, additional_config, target_group_id, target_user_id)]

        return self._build_regular_actions(raw_message, target_group_id, target_user_id)

    def _build_regular_actions(
        self,
        raw_message: Any,
        target_group_id: str,
        target_user_id: str,
    ) -> List[OutboundAction]:
        """构造普通消息的动作序列，文件段按画像决定拆分或内联。

        Args:
            raw_message: Host 侧 ``raw_message`` 字段。
            target_group_id: 目标群号；群聊出站时非空。
            target_user_id: 目标用户号；私聊出站时非空。

        Returns:
            List[OutboundAction]: 动作序列。

        Raises:
            ValueError: 当私聊出站缺少目标用户 ID 或消息不含可发送内容时抛出。
        """
        profile = self._profile_state.profile
        split_file_upload = bool(profile.split_file_upload)

        actions: List[OutboundAction] = []
        pending_segments: List[Mapping[str, Any]] = []

        def flush_pending() -> None:
            """把累积的普通消息段作为一个发送动作落地，保持与文件动作的相对顺序。"""
            if not pending_segments:
                return
            segments = self._segment_encoder.convert_segments(list(pending_segments))
            pending_segments.clear()
            actions.append(self._build_send_action(segments, target_group_id, target_user_id))

        if not isinstance(raw_message, list):
            raw_message = [raw_message]

        for item in raw_message:
            if not isinstance(item, Mapping):
                continue

            if split_file_upload and str(item.get("type") or "") == "file":
                upload_action = self._build_file_upload_action(item, target_group_id, target_user_id)
                if upload_action is not None:
                    flush_pending()
                    actions.append(upload_action)
                    continue

            pending_segments.append(item)

        flush_pending()

        if not actions:
            if not target_group_id and not target_user_id:
                raise ValueError("出站私聊消息缺少 target_user_id")
            raise ValueError("出站消息不包含可发送的内容段")
        return actions

    def _build_send_action(
        self,
        segments: List[Dict[str, Any]],
        target_group_id: str,
        target_user_id: str,
    ) -> OutboundAction:
        """按画像构造单个消息发送动作。

        Args:
            segments: 已转换的 OneBot 消息段列表。
            target_group_id: 目标群号；群聊出站时非空。
            target_user_id: 目标用户号；私聊出站时非空。

        Returns:
            OutboundAction: 发送动作。

        Raises:
            ValueError: 当私聊出站缺少目标用户 ID 时抛出。
        """
        profile = self._profile_state.profile
        if target_group_id:
            if profile.msg_action_style == MSG_ACTION_STYLE_GENERIC:
                return "send_msg", {"message_type": "group", "group_id": target_group_id, "message": segments}
            return "send_group_msg", {"group_id": target_group_id, "message": segments}

        if not target_user_id:
            raise ValueError("出站私聊消息缺少 target_user_id")
        if profile.msg_action_style == MSG_ACTION_STYLE_GENERIC:
            return "send_msg", {"message_type": "private", "user_id": target_user_id, "message": segments}
        return "send_private_msg", {"message": segments, "user_id": target_user_id}

    def _build_file_upload_action(
        self,
        item: Mapping[str, Any],
        target_group_id: str,
        target_user_id: str,
    ) -> OutboundAction | None:
        """把文件段构造为独立上传动作（SnowLuma 画像）。

        Args:
            item: Host 侧文件消息段。
            target_group_id: 目标群号；群聊出站时非空。
            target_user_id: 目标用户号；私聊出站时非空。

        Returns:
            OutboundAction | None: 上传动作；文件引用缺失时返回 ``None``。
        """
        item_data = item.get("data")
        if not isinstance(item_data, Mapping):
            item_data = {}

        file_reference = str(
            item_data.get("file")
            or item_data.get("path")
            or item_data.get("url")
            or ""
        ).strip()
        if not file_reference:
            return None

        file_name = str(item_data.get("name") or "").strip()
        normalized_reference = self._segment_encoder._normalize_file_reference(file_reference)

        if target_group_id:
            params: Dict[str, Any] = {"group_id": target_group_id, "file": normalized_reference}
            if file_name:
                params["name"] = file_name
            return "upload_group_file", params

        if not target_user_id:
            raise ValueError("出站私聊消息缺少 target_user_id")
        params = {"user_id": target_user_id, "file": normalized_reference}
        if file_name:
            params["name"] = file_name
        return "upload_private_file", params

    def _build_forward_action(
        self,
        raw_message: Any,
        additional_config: Mapping[str, Any],
        target_group_id: str,
        target_user_id: str,
    ) -> OutboundAction:
        """构造合并转发动作，参数键按画像取值。

        与单动作实现的语义一致：夹在转发之间的普通段包装成合成节点。

        Args:
            raw_message: Host 侧 ``raw_message`` 字段。
            additional_config: 附加配置（取 self_id 构造合成节点）。
            target_group_id: 目标群号；群聊出站时非空。
            target_user_id: 目标用户号；私聊出站时非空。

        Returns:
            OutboundAction: 合并转发动作。

        Raises:
            ValueError: 当私聊出站缺少目标用户 ID 时抛出。
        """
        profile = self._profile_state.profile
        forward_segments = self._build_forward_message_segments(raw_message, additional_config)
        param_key = profile.forward_param_key
        if target_group_id:
            return "send_group_forward_msg", {"group_id": target_group_id, param_key: forward_segments}
        if not target_user_id:
            raise ValueError("出站私聊消息缺少 target_user_id")
        return "send_private_forward_msg", {param_key: forward_segments, "user_id": target_user_id}

    @staticmethod
    def _contains_forward_segment(raw_message: Any) -> bool:
        """判断 Host 消息中是否包含合并转发组件。"""
        if not isinstance(raw_message, list):
            return False
        return any(isinstance(item, Mapping) and item.get("type") == "forward" for item in raw_message)

    def _build_forward_message_segments(
        self,
        raw_message: Any,
        additional_config: Mapping[str, Any],
    ) -> List[Dict[str, Any]]:
        """构造合并转发动作需要的节点列表。"""
        if not isinstance(raw_message, list):
            return []

        forward_segments: List[Dict[str, Any]] = []
        regular_segments: List[Mapping[str, Any]] = []
        for item in raw_message:
            if not isinstance(item, Mapping):
                continue

            if item.get("type") == "forward":
                if regular_segments:
                    forward_segments.append(self._build_regular_forward_node(regular_segments, additional_config))
                    regular_segments = []
                forward_segments.extend(self._segment_encoder.convert_segments([item]))
                continue

            regular_segments.append(item)

        if regular_segments:
            forward_segments.append(self._build_regular_forward_node(regular_segments, additional_config))

        return forward_segments

    def _build_regular_forward_node(
        self,
        regular_segments: List[Mapping[str, Any]],
        additional_config: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """将合并转发消息中夹带的普通消息段包装成一个转发节点。"""
        self_id = str(additional_config.get("self_id") or "").strip()
        return {
            "type": "node",
            "data": {
                "name": "MaiBot",
                "uin": self_id,
                "content": self._segment_encoder.convert_segments(regular_segments),
            },
        }
