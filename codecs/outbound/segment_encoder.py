"""出站消息段编码器。"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping

SYNTHETIC_MESSAGE_ID_PREFIX = "qq-"


class QQOutboundSegmentEncoder:
    """将 Host 消息段转换为 OneBot 消息段。"""

    def __init__(self) -> None:
        """初始化出站消息段编码器。"""
        self._segment_builders: Dict[str, Callable[[Mapping[str, Any]], List[Dict[str, Any]]]] = {
            "at": self._build_at_segments,
            "dict": self._build_dict_segments,
            "emoji": self._build_emoji_segments,
            "face": self._build_face_segments,
            "file": self._build_file_segments,
            "forward": self._build_forward_segments,
            "image": self._build_image_segments,
            "imageurl": self._build_imageurl_segments,
            "music": self._build_music_segments,
            "reply": self._build_reply_segments,
            "text": self._build_text_segments,
            "video": self._build_video_segments,
            "videourl": self._build_videourl_segments,
            "voice": self._build_voice_segments,
            "voiceurl": self._build_voiceurl_segments,
        }

    def convert_segments(self, raw_message: Any) -> List[Dict[str, Any]]:
        """将 Host 消息段转换为 OneBot 消息段。

        Args:
            raw_message: Host 侧 ``raw_message`` 字段。

        Returns:
            List[Dict[str, Any]]: OneBot 消息段列表。
        """
        if not isinstance(raw_message, list):
            return [{"type": "text", "data": {"text": ""}}]

        outbound_segments: List[Dict[str, Any]] = []
        for item in raw_message:
            if not isinstance(item, Mapping):
                continue

            item_type = str(item.get("type") or "").strip()
            segment_builder = self._segment_builders.get(item_type)
            if segment_builder is None:
                fallback_text = f"[unsupported:{item_type or 'unknown'}]"
                outbound_segments.append({"type": "text", "data": {"text": fallback_text}})
                continue

            built_segments = segment_builder(item)
            if built_segments:
                outbound_segments.extend(built_segments)
                continue

            fallback_text = self._build_empty_segment_fallback(item_type)
            outbound_segments.append({"type": "text", "data": {"text": fallback_text}})

        if not outbound_segments:
            outbound_segments.append({"type": "text", "data": {"text": ""}})
        return outbound_segments

    @staticmethod
    def _build_empty_segment_fallback(item_type: str) -> str:
        """为缺少有效数据的消息段生成占位文本。

        Args:
            item_type: 原始消息段类型。

        Returns:
            str: 用于降级展示的占位文本。
        """
        normalized_type = item_type or "unknown"
        fallback_map = {
            "emoji": "[emoji]",
            "face": "[face]",
            "file": "[file]",
            "image": "[image]",
            "imageurl": "[image]",
            "music": "[music]",
            "video": "[video]",
            "videourl": "[video]",
            "voice": "[voice]",
            "voiceurl": "[voice]",
        }
        return fallback_map.get(normalized_type, f"[unsupported:{normalized_type}]")

    def _build_text_segments(self, item: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """构造文本消息段。

        Args:
            item: Host 侧文本消息段。

        Returns:
            List[Dict[str, Any]]: 构造后的 OneBot 文本消息段列表。
        """
        text_value = str(item.get("data") or "")
        return [{"type": "text", "data": {"text": text_value}}]

    def _build_at_segments(self, item: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """构造 @ 消息段。

        Args:
            item: Host 侧 @ 消息段。

        Returns:
            List[Dict[str, Any]]: 构造后的 OneBot @ 消息段列表。
        """
        item_data = item.get("data")
        if not isinstance(item_data, Mapping):
            return []
        target_user_id = str(item_data.get("target_user_id") or "").strip()
        if not target_user_id:
            return []
        return [{"type": "at", "data": {"qq": target_user_id}}]

    def _build_reply_segments(self, item: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """构造回复消息段。

        适配器合成的内部消息 ID（``qq-`` 前缀）与空引用（0）无法在平台侧定位，
        统一丢弃引用、保留正文。

        Args:
            item: Host 侧回复消息段。

        Returns:
            List[Dict[str, Any]]: 构造后的 OneBot 回复消息段列表。
        """
        item_data = item.get("data")
        if isinstance(item_data, Mapping):
            target_message_id = str(item_data.get("target_message_id") or "").strip()
        else:
            target_message_id = str(item_data or "").strip()
        target_message_id = self._normalize_outbound_reply_id(target_message_id)
        if not target_message_id:
            return []
        return [{"type": "reply", "data": {"id": target_message_id}}]

    @staticmethod
    def _normalize_outbound_reply_id(value: str) -> str:
        """规范化出站引用消息 ID。

        Args:
            value: Host 侧 ``target_message_id``。

        Returns:
            str: 可用于平台引用的消息 ID；无效时返回空字符串。
        """

        normalized_value = str(value or "").strip()
        if not normalized_value:
            return ""
        if normalized_value.startswith(f"{SYNTHETIC_MESSAGE_ID_PREFIX}"):
            return ""
        try:
            reply_id = int(normalized_value)
        except ValueError:
            return normalized_value
        if reply_id == 0:
            return ""
        return str(reply_id)

    def _build_image_segments(self, item: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """构造图片消息段。

        Args:
            item: Host 侧图片消息段。

        Returns:
            List[Dict[str, Any]]: 构造后的 OneBot 图片消息段列表。
        """
        binary_base64 = str(item.get("binary_data_base64") or "").strip()
        if not binary_base64:
            return []
        return [{"type": "image", "data": {"file": f"base64://{binary_base64}", "sub_type": 0}}]

    def _build_emoji_segments(self, item: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """构造动画表情消息段。

        Args:
            item: Host 侧表情消息段。

        Returns:
            List[Dict[str, Any]]: 构造后的 OneBot 表情消息段列表。
        """
        binary_base64 = str(item.get("binary_data_base64") or "").strip()
        if not binary_base64:
            return []
        return [
            {
                "type": "image",
                "data": {
                    "file": f"base64://{binary_base64}",
                    "sub_type": 1,
                    "summary": "[动画表情]",
                },
            }
        ]

    def _build_voice_segments(self, item: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """构造语音消息段。

        Args:
            item: Host 侧语音消息段。

        Returns:
            List[Dict[str, Any]]: 构造后的 OneBot 语音消息段列表。
        """
        return [self._build_voice_segment(item)]

    def _build_voiceurl_segments(self, item: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """构造基于 URL 的语音消息段。

        Args:
            item: Host 侧语音 URL 消息段。

        Returns:
            List[Dict[str, Any]]: 构造后的 OneBot 语音消息段列表。
        """
        voice_url_segment = self._build_url_media_segment("record", item.get("data"))
        return [voice_url_segment] if voice_url_segment else []

    def _build_face_segments(self, item: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """构造 QQ 原生表情消息段。

        Args:
            item: Host 侧表情消息段。

        Returns:
            List[Dict[str, Any]]: 构造后的 OneBot 表情消息段列表。
        """
        face_segment = self._build_face_segment(item.get("data"))
        return [face_segment] if face_segment else []

    def _build_imageurl_segments(self, item: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """构造基于 URL 的图片消息段。

        Args:
            item: Host 侧图片 URL 消息段。

        Returns:
            List[Dict[str, Any]]: 构造后的 OneBot 图片消息段列表。
        """
        image_segment = self._build_url_media_segment("image", item.get("data"))
        return [image_segment] if image_segment else []

    def _build_videourl_segments(self, item: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """构造基于 URL 的视频消息段。

        Args:
            item: Host 侧视频 URL 消息段。

        Returns:
            List[Dict[str, Any]]: 构造后的 OneBot 视频消息段列表。
        """
        video_segment = self._build_url_media_segment("video", item.get("data"))
        return [video_segment] if video_segment else []

    def _build_video_segments(self, item: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """构造视频消息段。

        Args:
            item: Host 侧视频消息段。

        Returns:
            List[Dict[str, Any]]: 构造后的 OneBot 视频消息段列表。
        """
        video_segment = self._build_video_segment(item)
        return [video_segment] if video_segment else []

    def _build_file_segments(self, item: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """构造文件消息段。

        Args:
            item: Host 侧文件消息段。

        Returns:
            List[Dict[str, Any]]: 构造后的 OneBot 文件消息段列表。
        """
        file_segment = self._build_file_segment(item.get("data"))
        return [file_segment] if file_segment else []

    def _build_music_segments(self, item: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """构造音乐卡片消息段。

        Args:
            item: Host 侧音乐消息段。

        Returns:
            List[Dict[str, Any]]: 构造后的 OneBot 音乐消息段列表。
        """
        music_segment = self._build_music_segment(item.get("data"))
        return [music_segment] if music_segment else []

    def _build_forward_segments(self, item: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """构造合并转发消息段。

        Args:
            item: Host 侧转发消息段。

        Returns:
            List[Dict[str, Any]]: 构造后的 OneBot 转发节点列表。
        """
        item_data = item.get("data")
        if not isinstance(item_data, list):
            return []
        return self._build_forward_nodes(item_data)

    def _build_dict_segments(self, item: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """构造 ``DictComponent`` 消息段。

        Args:
            item: Host 侧 ``DictComponent`` 消息段。

        Returns:
            List[Dict[str, Any]]: 构造后的 OneBot 消息段列表。
        """
        item_data = item.get("data")
        if not isinstance(item_data, Mapping):
            return []
        dict_segment = self._build_dict_component_segment(item_data)
        return [dict_segment] if dict_segment else []

    def _build_voice_segment(self, item: Mapping[str, Any]) -> Dict[str, Any]:
        """构造语音消息段。

        Args:
            item: Host 侧语音消息段。

        Returns:
            Dict[str, Any]: OneBot ``record`` 消息段；缺少有效数据时返回占位文本段。
        """
        binary_base64 = str(item.get("binary_data_base64") or "").strip()
        if binary_base64:
            return {"type": "record", "data": {"file": f"base64://{binary_base64}"}}

        item_data = item.get("data")
        if url_media_segment := self._build_url_media_segment("record", item_data):
            return url_media_segment
        return {"type": "text", "data": {"text": "[voice]"}}

    def _build_face_segment(self, item_data: Any) -> Dict[str, Any]:
        """构造 QQ 原生表情消息段。

        Args:
            item_data: Host 侧表情段数据。

        Returns:
            Dict[str, Any]: OneBot ``face`` 段；缺少有效表情 ID 时返回空字典。
        """
        face_id = ""
        if isinstance(item_data, Mapping):
            face_id = str(item_data.get("id") or "").strip()
        else:
            face_id = str(item_data or "").strip()
        if not face_id:
            return {}
        return {"type": "face", "data": {"id": face_id}}

    def _build_video_segment(self, item: Mapping[str, Any]) -> Dict[str, Any]:
        """构造视频消息段。

        Args:
            item: Host 侧视频消息段。

        Returns:
            Dict[str, Any]: OneBot ``video`` 消息段；缺少有效数据时返回空字典。
        """
        binary_base64 = str(item.get("binary_data_base64") or "").strip()
        if binary_base64:
            return {"type": "video", "data": {"file": f"base64://{binary_base64}"}}
        return self._build_url_media_segment("video", item.get("data"))

    def _build_file_segment(self, item_data: Any) -> Dict[str, Any]:
        """构造文件消息段。

        Args:
            item_data: Host 侧文件段数据。

        Returns:
            Dict[str, Any]: OneBot ``file`` 段；缺少有效数据时返回空字典。
        """
        if isinstance(item_data, str):
            normalized_file = item_data.strip()
            if not normalized_file:
                return {}
            return {"type": "file", "data": {"file": self._normalize_file_reference(normalized_file)}}

        if not isinstance(item_data, Mapping):
            return {}

        raw_file = str(item_data.get("file") or "").strip()
        raw_path = str(item_data.get("path") or "").strip()
        raw_url = str(item_data.get("url") or "").strip()
        file_ref = raw_file or raw_path or raw_url
        if not file_ref:
            return {}

        data: Dict[str, Any] = {"file": self._normalize_file_reference(file_ref)}
        for optional_field in ("name", "thumb"):
            optional_value = str(item_data.get(optional_field) or "").strip()
            if optional_value:
                data[optional_field] = optional_value
        return {"type": "file", "data": data}

    def _build_music_segment(self, item_data: Any) -> Dict[str, Any]:
        """构造音乐卡片消息段。

        Args:
            item_data: Host 侧音乐段数据。

        Returns:
            Dict[str, Any]: OneBot ``music`` 段；缺少有效数据时返回空字典。
        """
        if isinstance(item_data, str):
            normalized_song_id = item_data.strip()
            if not normalized_song_id:
                return {}
            return {"type": "music", "data": {"type": "163", "id": normalized_song_id}}

        if not isinstance(item_data, Mapping):
            return {}

        platform = str(item_data.get("type") or "163").strip() or "163"
        if platform not in {"163", "qq"}:
            platform = "163"
        song_id = str(item_data.get("id") or "").strip()
        if not song_id:
            return {}
        return {"type": "music", "data": {"type": platform, "id": song_id}}

    def _build_url_media_segment(self, segment_type: str, item_data: Any) -> Dict[str, Any]:
        """构造基于 URL 或文件引用的媒体消息段。

        Args:
            segment_type: 目标消息段类型。
            item_data: Host 侧消息段数据。

        Returns:
            Dict[str, Any]: NapCat 媒体消息段；缺少有效引用时返回空字典。
        """
        if isinstance(item_data, Mapping):
            file_reference = str(item_data.get("file") or item_data.get("url") or "").strip()
        else:
            file_reference = str(item_data or "").strip()
        if not file_reference:
            return {}
        return {"type": segment_type, "data": {"file": self._normalize_file_reference(file_reference)}}

    @staticmethod
    def _normalize_file_reference(file_reference: str) -> str:
        """规范化文件引用字符串。

        Args:
            file_reference: 原始文件引用。

        Returns:
            str: 可供 对端使用的文件引用。
        """
        if file_reference.startswith(("base64://", "file://", "http://", "https://")):
            return file_reference
        return f"file://{file_reference}"

    def _build_forward_nodes(self, forward_nodes: List[Any]) -> List[Dict[str, Any]]:
        """构造 OneBot 转发节点列表。

        Args:
            forward_nodes: 内部转发节点列表。

        Returns:
            List[Dict[str, Any]]: OneBot 转发节点列表。
        """
        built_nodes: List[Dict[str, Any]] = []
        for node in forward_nodes:
            if not isinstance(node, Mapping):
                continue
            raw_content = node.get("content", [])
            node_segments = self.convert_segments(raw_content)
            built_nodes.append(
                {
                    "type": "node",
                    "data": {
                        "name": str(node.get("user_nickname") or node.get("user_cardname") or "QQ用户"),
                        "uin": str(node.get("user_id") or ""),
                        "content": node_segments,
                    },
                }
            )
        return built_nodes

    def _build_dict_component_segment(self, item_data: Mapping[str, Any]) -> Dict[str, Any]:
        """尽力将 ``DictComponent`` 转换为 OneBot 消息段。

        Args:
            item_data: ``DictComponent`` 原始数据。

        Returns:
            Dict[str, Any]: OneBot 消息段；不支持时返回占位文本段。
        """
        raw_type = str(item_data.get("type") or "").strip()
        raw_payload = item_data.get("data", item_data)
        if raw_type == "file":
            return self._build_file_segment(raw_payload)
        if raw_type == "music":
            return self._build_music_segment(raw_payload)
        if raw_type == "video":
            if isinstance(raw_payload, Mapping):
                pseudo_item: Dict[str, Any] = {
                    "binary_data_base64": raw_payload.get("binary_data_base64"),
                    "data": raw_payload,
                }
                return self._build_video_segment(pseudo_item)
            return self._build_video_segment({"data": raw_payload})
        if raw_type == "face":
            return self._build_face_segment(raw_payload)
        if raw_type == "voiceurl":
            return self._build_url_media_segment("record", raw_payload)
        if raw_type == "imageurl":
            return self._build_url_media_segment("image", raw_payload)
        if raw_type == "videourl":
            return self._build_url_media_segment("video", raw_payload)
        if raw_type in {"image", "record", "reply", "at"} and isinstance(raw_payload, Mapping):
            return {"type": raw_type, "data": dict(raw_payload)}
        return {"type": "text", "data": {"text": f"[unsupported:{raw_type or 'dict'}]"}}
