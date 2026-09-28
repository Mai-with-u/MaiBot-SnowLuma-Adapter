"""入站消息编解码（SnowLuma / NapCat 通用，画像钩子见各转换分支）。"""

from __future__ import annotations

from binascii import Error as BinasciiError
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple
from uuid import uuid4

import base64
import hashlib
import time

from ...qq_face_map import QQ_FACE_DESCRIPTIONS, QQ_FACE_EMOJIS
from ...services import QQQueryService
from ...types import QQIncomingSegment, QQIncomingSegments, QQPayload, QQSegment, QQSegments
from ...voice import is_silk_voice_binary, transcode_silk_voice_binary
from ..notice.helpers import normalize_optional_string
from .cards import QQInboundCardMixin
from .text import QQInboundTextMixin



class QQInboundCodec(QQInboundCardMixin, QQInboundTextMixin):
    """入站消息编码器。"""

    def __init__(
        self,
        logger: Any,
        query_service: QQQueryService,
        profile_state: Any,
        load_settings: Callable[[], Any],
    ) -> None:
        """初始化入站消息编码器。

        Args:
            logger: 插件日志对象。
            query_service: QQ 查询服务。
            profile_state: 当前连接的客户端画像容器。
            load_settings: 返回当前生效插件配置的回调。
        """
        self._logger = logger
        self._query_service = query_service
        self._profile_state = profile_state
        self._load_settings = load_settings
        self._group_name_cache: Dict[str, str] = {}

    def clear_cache(self) -> None:
        """清空群名缓存（断连时调用，避免跨连接脏数据）。"""
        self._group_name_cache.clear()

    async def build_message_dict(
        self,
        payload: QQPayload,
        self_id: str,
        sender_user_id: str,
        sender: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """构造 Host 侧可接受的 ``MessageDict``。

        Args:
            payload: 原始消息事件。
            self_id: 当前机器人账号 ID。
            sender_user_id: 发送者用户 ID。
            sender: 发送者信息字典。

        Returns:
            Dict[str, Any]: 规范化后的 ``MessageDict``。
        """
        message_type = str(payload.get("message_type") or "").strip() or "private"
        group_id = str(payload.get("group_id") or "").strip()
        # SnowLuma 的推送不带 group_name，需要查询对端补全（移植自 SnowLuma 适配器）；
        # NapCat 推送自带该字段，查询不会触发。
        group_name = await self._resolve_group_name(payload, group_id)
        user_nickname = str(sender.get("nickname") or sender.get("card") or sender_user_id).strip() or sender_user_id
        user_cardname = str(sender.get("card") or "").strip() or None

        raw_message, is_at, platform_card_payloads = await self.convert_segments_with_metadata(payload, self_id)
        if not raw_message:
            raw_message = [self._build_text_segment("[unsupported]")]

        plain_text = self.build_plain_text(raw_message)
        timestamp_seconds = payload.get("time")
        if not isinstance(timestamp_seconds, (int, float)):
            timestamp_seconds = time.time()

        additional_config: Dict[str, Any] = {
            "self_id": self_id,
            "napcat_message_type": message_type,
            "client_type": self._profile_state.profile.client_type,
        }
        if group_id:
            additional_config["platform_io_target_group_id"] = group_id
        else:
            additional_config["platform_io_target_user_id"] = sender_user_id
        if platform_card_payloads:
            additional_config["platform_card_payloads"] = platform_card_payloads

        message_info: Dict[str, Any] = {
            "user_info": {
                "user_id": sender_user_id,
                "user_nickname": user_nickname,
                "user_cardname": user_cardname,
            },
            "additional_config": additional_config,
        }
        if group_id:
            message_info["group_info"] = {"group_id": group_id, "group_name": group_name}

        # message_id 是平台侧消息的主键，缺失时无法引用/去重/撤回；
        # 明确报错丢弃该消息，不合成内部 ID 掩盖对端数据问题。
        message_id = str(payload.get("message_id") or "").strip()
        if not message_id:
            raise ValueError("入站消息缺少 message_id")
        has_picture = any(
            isinstance(segment, Mapping) and str(segment.get("type") or "") in {"image", "picture"}
            for segment in raw_message
        )
        return {
            "message_id": message_id,
            "timestamp": str(float(timestamp_seconds)),
            "platform": "qq",
            "message_info": message_info,
            "raw_message": raw_message,
            "is_mentioned": is_at,
            "is_at": is_at,
            "is_emoji": False,
            "is_picture": has_picture,
            "is_command": plain_text.startswith("/"),
            "is_notify": False,
            "session_id": "",
            "processed_plain_text": plain_text,
            "display_message": plain_text,
        }

    async def convert_segments(self, payload: QQPayload, self_id: str) -> Tuple[QQSegments, bool]:
        """将 OneBot 消息段转换为 Host 消息段结构。

        Args:
            payload: OneBot 原始消息事件。
            self_id: 当前机器人账号 ID。

        Returns:
            Tuple[QQSegments, bool]: 转换后的消息段列表，以及是否 @ 到当前机器人。

        Raises:
            ValueError: 当载荷缺少结构化 ``message`` 段列表时抛出。
        """
        raw_message, is_at, _platform_card_payloads = await self.convert_segments_with_metadata(payload, self_id)
        return raw_message, is_at

    async def convert_segments_with_metadata(
        self,
        payload: QQPayload,
        self_id: str,
    ) -> Tuple[QQSegments, bool, List[Dict[str, Any]]]:
        """将 OneBot 消息段转换为 Host 消息段结构，并收集平台卡片元数据。

        Args:
            payload: OneBot 原始消息事件。
            self_id: 当前机器人账号 ID。

        Returns:
            Tuple[QQSegments, bool, List[Dict[str, Any]]]: 转换后的消息段列表、是否 @ 到当前机器人，
            以及不参与纯文本处理的平台卡片元数据。
        """
        message_payload = self._require_message_segments(payload)
        group_id = str(payload.get("group_id") or "").strip()
        platform_card_payloads: List[Dict[str, Any]] = []
        raw_message, is_at = await self._convert_incoming_segments(
            message_payload,
            self_id,
            group_id,
            platform_card_payloads=platform_card_payloads,
        )
        return raw_message, is_at, platform_card_payloads

    def _require_message_segments(self, payload: QQPayload) -> QQIncomingSegments:
        """从载荷中提取结构化消息段列表。

        SnowLuma 部分事件会以纯字符串形式携带 ``message`` 字段，
        此时整体视为单个文本段。

        Args:
            payload: 对端原始载荷。

        Returns:
            QQIncomingSegments: 规范化后的结构化消息段列表。

        Raises:
            ValueError: 当 ``message`` 字段为空或不可识别时抛出。
        """
        message_payload = payload.get("message")
        if isinstance(message_payload, str):
            message_text = message_payload.strip()
            if not message_text:
                raise ValueError("入站消息 message 字段为空")
            return [
                QQIncomingSegment(
                    type="text",
                    data={"text": message_payload},
                )
            ]
        if not isinstance(message_payload, list):
            raise ValueError("入站消息缺少结构化 message 段列表")

        normalized_segments = self._normalize_incoming_segments(message_payload)
        if not normalized_segments:
            raise ValueError("入站消息未包含可识别的结构化消息段")
        return normalized_segments

    def _normalize_incoming_segments(self, message_payload: List[Any]) -> QQIncomingSegments:
        """规范化 NapCat / OneBot 原始消息段列表。

        Args:
            message_payload: 原始 ``message`` 字段值。

        Returns:
            QQIncomingSegments: 过滤并标准化后的消息段列表。
        """
        normalized_segments: QQIncomingSegments = []
        for segment in message_payload:
            if not isinstance(segment, Mapping):
                continue
            segment_type = str(segment.get("type") or "").strip()
            segment_data = segment.get("data", {})
            if not segment_type or not isinstance(segment_data, Mapping):
                continue
            normalized_segments.append(
                QQIncomingSegment(
                    type=segment_type,
                    data=dict(segment_data),
                )
            )
        return normalized_segments

    async def _convert_incoming_segments(
        self,
        message_payload: QQIncomingSegments,
        self_id: str,
        group_id: str,
        *,
        platform_card_payloads: Optional[List[Dict[str, Any]]] = None,
        resolve_reply_details: bool = True,
    ) -> Tuple[QQSegments, bool]:
        """将结构化 OneBot 消息段转换为 Host 消息段结构。

        Args:
            message_payload: NapCat / OneBot 结构化消息段列表。
            self_id: 当前机器人账号 ID。
            group_id: 当前消息所在群号；私聊消息为空字符串。
            resolve_reply_details: 是否查询引用目标详情；转发节点和引用预览只保留目标 ID。

        Returns:
            Tuple[QQSegments, bool]: 转换后的消息段列表，以及是否 @ 到当前机器人。
        """
        converted_segments: QQSegments = []
        at_target_cache: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
        is_at = False
        for segment in message_payload:
            segment_type = str(segment.get("type") or "").strip()
            segment_data = segment.get("data", {})
            if not isinstance(segment_data, Mapping):
                segment_data = {}

            if segment_type == "text":
                if text_value := str(segment_data.get("text") or ""):
                    converted_segments.append(self._build_text_segment(text_value))
                continue

            if segment_type == "at":
                if target_user_id := str(segment_data.get("qq") or "").strip():
                    if target_user_id in at_target_cache:
                        target_user_nickname, target_user_cardname = at_target_cache[target_user_id]
                    else:
                        target_user_nickname, target_user_cardname = await self._resolve_at_target_info(
                            group_id=group_id,
                            target_user_id=target_user_id,
                        )
                        at_target_cache[target_user_id] = (target_user_nickname, target_user_cardname)

                    converted_segments.append(
                        {
                            "type": "at",
                            "data": {
                                "target_user_id": target_user_id,
                                "target_user_nickname": target_user_nickname,
                                "target_user_cardname": target_user_cardname,
                            },
                        }
                    )
                    if self_id and target_user_id == self_id:
                        is_at = True
                continue

            if segment_type == "reply":
                if reply_segment := await self._build_reply_segment(
                    segment_data, resolve_details=resolve_reply_details
                ):
                    converted_segments.append(reply_segment)
                continue

            if segment_type == "face":
                converted_segments.append(self._build_face_text_segment(segment_data))
                continue

            if segment_type == "image":
                converted_segments.append(await self._build_image_like_segment(segment_data, is_emoji=False))
                continue

            if segment_type == "record":
                converted_segments.append(await self._build_record_segment(segment_data))
                continue

            if segment_type == "video":
                converted_segments.append(self._build_video_text_segment(segment_data))
                continue

            if segment_type == "file":
                converted_segments.append(self._build_file_text_segment(segment_data))
                continue

            if segment_type == "json":
                converted_segments.extend(
                    await self._build_json_segments(
                        segment_data,
                        platform_card_payloads=platform_card_payloads,
                    )
                )
                continue

            if segment_type == "forward":
                if forward_segment := await self._build_forward_segment(segment_data):
                    converted_segments.append(forward_segment)
                continue

            if segment_type in {"xml", "share"}:
                converted_segments.append(self._build_text_segment(f"[{segment_type}]"))

        return converted_segments, is_at

    async def _resolve_at_target_info(
        self,
        group_id: str,
        target_user_id: str,
    ) -> Tuple[Optional[str], Optional[str]]:
        """解析 ``at`` 目标的展示信息。

        Args:
            group_id: 当前消息所在群号；私聊消息为空字符串。
            target_user_id: 被 ``at`` 的用户号。

        Returns:
            Tuple[Optional[str], Optional[str]]: 依次返回 QQ 昵称和群昵称。
        """
        if not target_user_id or target_user_id == "all":
            return None, None

        target_user_nickname: Optional[str] = None
        target_user_cardname: Optional[str] = None

        if group_id:
            member_info = await self._query_service.get_group_member_info(group_id, target_user_id, no_cache=True)
            if member_info is not None:
                target_user_nickname = normalize_optional_string(member_info.get("nickname"))
                target_user_cardname = normalize_optional_string(member_info.get("card"))

        if target_user_nickname or target_user_cardname:
            return target_user_nickname, target_user_cardname

        stranger_info = await self._query_service.get_stranger_info(target_user_id)
        if stranger_info is None:
            return None, None

        return normalize_optional_string(stranger_info.get("nickname")), target_user_cardname

    @staticmethod
    def _build_text_segment(text: str) -> QQSegment:
        """构造一条纯文本 Host 消息段。

        Args:
            text: 文本内容。

        Returns:
            QQSegment: Host 侧纯文本消息段。
        """
        return {"type": "text", "data": text}

    @staticmethod
    def _normalize_inbound_reply_id(value: Any) -> str:
        """规范化入站引用消息 ID，过滤 OneBot 的空引用。

        Args:
            value: ``reply`` 段的原始 id 值。

        Returns:
            str: 规范化后的消息 ID；空引用返回空字符串。
        """

        normalized_value = str(value or "").strip()
        if not normalized_value:
            return ""
        try:
            reply_id = int(normalized_value)
        except ValueError:
            return normalized_value
        if reply_id == 0:
            return ""
        return str(reply_id)

    async def _build_reply_segment(
        self, segment_data: Mapping[str, Any], *, resolve_details: bool = True
    ) -> Optional[QQSegment]:
        """构造回复消息段。

        SnowLuma / OneBot 会推送 ``id=0`` 的空引用，统一过滤。

        Args:
            segment_data: OneBot ``reply`` 段的 ``data`` 字典。
            resolve_details: 是否查询引用目标的内容和发送者信息。

        Returns:
            Optional[QQSegment]: 转换后的回复消息段；缺少有效消息 ID 时返回 ``None``。
        """
        target_message_id = self._normalize_inbound_reply_id(segment_data.get("id"))
        if not target_message_id:
            return None

        reply_payload: Dict[str, Any] = {"target_message_id": target_message_id}
        message_detail = await self._query_service.get_message_detail(target_message_id) if resolve_details else None
        if message_detail is not None:
            sender = message_detail.get("sender", {})
            if not isinstance(sender, Mapping):
                sender = {}
            reply_payload["target_message_content"] = await self._build_reply_preview_text(message_detail)
            reply_payload["target_message_sender_id"] = (
                str(message_detail.get("user_id") or sender.get("user_id") or "").strip() or None
            )
            reply_payload["target_message_sender_nickname"] = str(sender.get("nickname") or "").strip() or None
            reply_payload["target_message_sender_cardname"] = str(sender.get("card") or "").strip() or None

        return {"type": "reply", "data": reply_payload}

    async def _build_reply_preview_text(self, message_detail: QQPayload) -> Optional[str]:
        """为回复引用构造结构化消息预览文本。

        Args:
            message_detail: ``get_msg`` 返回的消息详情。

        Returns:
            Optional[str]: 基于结构化消息段生成的预览文本；无法生成时返回 ``None``。
        """
        try:
            message_payload = self._require_message_segments(message_detail)
            group_id = str(message_detail.get("group_id") or "").strip()
            # 引用目标可能再次引用自身或另一条消息；预览不继续查询目标详情。
            reply_segments, _ = await self._convert_incoming_segments(
                message_payload, "", group_id, resolve_reply_details=False
            )
        except ValueError:
            return None

        if not reply_segments:
            return None
        return self.build_plain_text(reply_segments)

    async def _build_image_like_segment(
        self,
        segment_data: Mapping[str, Any],
        is_emoji: bool,
    ) -> QQSegment:
        """构造图片或表情消息段。

        媒体取数链（移植自 SnowLuma 适配器）：优先段内 base64，
        其次本地路径，再次 URL 下载，最后 ``get_image`` 动作兜底。

        Args:
            segment_data: OneBot ``image`` 段的 ``data`` 字典。
            is_emoji: 是否按表情组件处理。

        Returns:
            QQSegment: 转换后的图片或表情消息段。
        """
        subtype = self._normalize_numeric_segment_value(segment_data.get("sub_type"))
        actual_is_emoji = is_emoji or (subtype is not None and subtype not in {0, 4, 9})
        emoji_hint = str(segment_data.get("summary") or "").strip()
        if not actual_is_emoji and emoji_hint and emoji_hint != "[图片]":
            actual_is_emoji = True

        binary_data = await self._load_binary_from_segment_data(segment_data, image_action_fallback=True)
        if not binary_data:
            return self._build_text_segment("[emoji]" if actual_is_emoji else "[image]")

        return {
            "type": "emoji" if actual_is_emoji else "image",
            "data": "",
            "hash": hashlib.sha256(binary_data).hexdigest(),
            "binary_data_base64": self._encode_binary(binary_data),
        }

    async def _build_record_segment(self, segment_data: Mapping[str, Any]) -> QQSegment:
        """构造语音消息段。

        画像决定 ``get_record`` 的 out_format：直接要 wav；
        SnowLuma 要 mp3，且服务端可能仍返回 silk，统一走 silk 转码链。

        Args:
            segment_data: OneBot ``record`` 段的 ``data`` 字典。

        Returns:
            QQSegment: 转换后的语音或占位文本消息段。
        """
        file_name = str(segment_data.get("file") or "").strip()
        file_id = str(segment_data.get("file_id") or "").strip() or None
        if not file_name:
            return self._build_text_segment("[voice]")

        out_format = str(self._profile_state.profile.record_out_format or "wav").strip() or "wav"
        record_detail = await self._query_service.get_record_detail(
            file_name=file_name,
            file_id=file_id,
            out_format=out_format,
        )
        if record_detail is None:
            return self._build_text_segment("[voice]")

        record_base64 = str(record_detail.get("base64") or "").strip()
        binary_data: Optional[bytes] = None
        if record_base64:
            try:
                binary_data = self._decode_binary(record_base64)
            except Exception:
                binary_data = None
        if binary_data is None:
            # 部分实现的 get_record 返回本地文件路径而非 base64。
            binary_data = await self._load_binary_reference(str(record_detail.get("file") or "").strip())
        if not binary_data:
            return self._build_text_segment("[voice]")

        if self._profile_state.profile.transcode_silk_voice and is_silk_voice_binary(binary_data):
            mp3_data = await transcode_silk_voice_binary(binary_data)
            if mp3_data:
                binary_data = mp3_data
            else:
                self._logger.warning(
                    "silk 语音转码失败：请安装插件依赖 silk-python 并确认 ffmpeg 可用，已降级为占位文本"
                )
                return self._build_text_segment("[voice]")

        return {
            "type": "voice",
            "data": "",
            "hash": hashlib.sha256(binary_data).hexdigest(),
            "binary_data_base64": self._encode_binary(binary_data),
        }

    async def _load_binary_from_segment_data(
        self,
        segment_data: Mapping[str, Any],
        *,
        image_action_fallback: bool = False,
    ) -> Optional[bytes]:
        """从消息段字段中按优先级加载媒体二进制。

        取数顺序：``base64`` 字段 → ``base64://`` 引用 → 本地路径 → URL 下载
        →（可选）``get_image`` 动作兜底。

        Args:
            segment_data: 消息段的 ``data`` 字典。
            image_action_fallback: 前序来源全部失败时是否尝试 ``get_image`` 动作。

        Returns:
            Optional[bytes]: 加载到的二进制内容；全部失败时返回 ``None``。
        """
        inline_base64 = str(segment_data.get("base64") or "").strip()
        if inline_base64:
            try:
                return self._decode_binary(inline_base64)
            except Exception:
                pass

        for reference in (segment_data.get("file"), segment_data.get("url")):
            binary_data = await self._load_binary_reference(str(reference or "").strip())
            if binary_data:
                return binary_data

        if image_action_fallback:
            file_identifier = str(segment_data.get("file") or segment_data.get("file_id") or "").strip()
            if file_identifier:
                image_detail = await self._query_service.safe_call_action_data(
                    "get_image",
                    {"file": file_identifier},
                )
                if isinstance(image_detail, Mapping):
                    for reference in (image_detail.get("file"), image_detail.get("url")):
                        binary_data = await self._load_binary_reference(str(reference or "").strip())
                        if binary_data:
                            return binary_data
        return None

    async def _load_binary_reference(self, reference: str) -> Optional[bytes]:
        """加载一个媒体引用（base64://、本地路径或 URL）。

        Args:
            reference: 媒体引用字符串。

        Returns:
            Optional[bytes]: 加载到的二进制内容；引用为空或加载失败时返回 ``None``。
        """
        if not reference:
            return None

        if reference.startswith("base64://"):
            try:
                return base64.b64decode(reference[len("base64://"):], validate=False)
            except (BinasciiError, ValueError):
                return None

        if reference.startswith("http://") or reference.startswith("https://"):
            return await self._query_service.download_binary(reference)

        candidate_path = Path(reference)
        if candidate_path.is_file():
            try:
                return candidate_path.read_bytes()
            except OSError:
                return None
        return None

    def _build_face_text_segment(self, segment_data: Mapping[str, Any]) -> QQSegment:
        """构造 QQ 原生表情文本段。

        支持双模式（移植自 SnowLuma 适配器）：description 转中文描述，
        emoji 转近似 Unicode 表情；未收录的 ID 回退描述表，再回退占位符。

        Args:
            segment_data: OneBot ``face`` 段的 ``data`` 字典。

        Returns:
            QQSegment: 转换后的文本消息段。
        """
        face_id = str(segment_data.get("id", "")).strip()
        face_text = self._resolve_face_text(face_id)
        return self._build_text_segment(face_text)

    def _resolve_face_text(self, face_id: str) -> str:
        """按配置的表情解析模式返回表情文本。

        Args:
            face_id: QQ 表情 ID。

        Returns:
            str: 解析后的表情文本。
        """
        parse_mode = str(getattr(self._load_settings().plugin, "qq_face_parse_mode", "description") or "description")
        if parse_mode == "emoji" and face_id in QQ_FACE_EMOJIS:
            return str(QQ_FACE_EMOJIS[face_id])
        if face_id in QQ_FACE_DESCRIPTIONS:
            return f"[{QQ_FACE_DESCRIPTIONS[face_id]}]"
        return "[表情]"

    async def _resolve_group_name(self, payload: Mapping[str, Any], group_id: str) -> str:
        """解析群名称：优先推送字段，缺失时查询对端 ``get_group_info`` 并缓存。

        移植自 SnowLuma 适配器：SnowLuma 的推送不带 ``group_name``，
        仅靠 payload 会全部退化成 ``group_<id>``。

        Args:
            payload: 原始消息事件。
            group_id: 当前消息所在群号；私聊消息为空字符串。

        Returns:
            str: 解析出的群名称；私聊或查询失败时返回空串或 ``group_<id>`` 占位。
        """
        if not group_id:
            return ""

        raw_group_name = str(payload.get("group_name") or "").strip()
        if raw_group_name:
            self._group_name_cache[group_id] = raw_group_name
            return raw_group_name

        cached_group_name = self._group_name_cache.get(group_id, "")
        if cached_group_name:
            return cached_group_name

        try:
            group_info = await self._query_service.get_group_info(group_id)
        except Exception as exc:
            self._logger.debug(f"查询群名称失败: group_id={group_id} error={exc}")
            return f"group_{group_id}"

        if group_info is not None:
            resolved_group_name = str(group_info.get("group_name") or "").strip()
            if resolved_group_name:
                self._group_name_cache[group_id] = resolved_group_name
                return resolved_group_name

        return f"group_{group_id}"

    def _build_video_text_segment(self, segment_data: Mapping[str, Any]) -> QQSegment:
        """构造视频消息的可读文本段。

        Args:
            segment_data: OneBot ``video`` 段的 ``data`` 字典。

        Returns:
            QQSegment: 转换后的文本消息段。
        """
        file_name = str(segment_data.get("file") or "").strip()
        file_size = str(segment_data.get("file_size") or "").strip()
        parts: List[str] = []
        if file_name:
            parts.append(f"文件: {file_name}")
        if file_size:
            parts.append(f"大小: {file_size}")
        if parts:
            return self._build_text_segment(f"[视频] {'，'.join(parts)}")
        return self._build_text_segment("[视频]")

    def _build_file_text_segment(self, segment_data: Mapping[str, Any]) -> QQSegment:
        """构造文件消息的可读文本段。

        Args:
            segment_data: OneBot ``file`` 段的 ``data`` 字典。

        Returns:
            QQSegment: 转换后的文本消息段。
        """
        file_name = str(segment_data.get("file") or segment_data.get("name") or "").strip()
        file_size = str(segment_data.get("file_size") or "").strip()
        file_url = str(segment_data.get("url") or "").strip()
        text_parts: List[str] = []
        if file_name:
            text_parts.append(file_name)
        if file_size:
            text_parts.append(f"大小: {file_size}")
        file_text = "[文件]"
        if text_parts:
            file_text = f"[文件] {'，'.join(text_parts)}"
        if file_url:
            file_text = f"{file_text}，链接: {file_url}"
        return self._build_text_segment(file_text)

    async def _build_forward_segment(self, segment_data: Mapping[str, Any]) -> Optional[QQSegment]:
        """构造合并转发消息段。

        Args:
            segment_data: OneBot ``forward`` 段的 ``data`` 字典。

        Returns:
            Optional[QQSegment]: 转换后的合并转发消息段；失败时返回 ``None``。
        """
        inline_messages = self._extract_forward_messages(segment_data)
        messages = inline_messages

        if messages is None:
            message_id = str(segment_data.get("id") or "").strip()
            if not message_id:
                return None

            forward_detail = await self._query_service.get_forward_message(message_id)
            if forward_detail is None:
                return self._build_text_segment("[forward]")

            messages = self._extract_forward_messages(forward_detail)

        if not isinstance(messages, list):
            return self._build_text_segment("[forward]")

        forward_nodes = await self._build_forward_nodes(messages)
        if not forward_nodes:
            return self._build_text_segment("[forward]")
        return {"type": "forward", "data": forward_nodes}

    def _extract_forward_messages(self, payload: Mapping[str, Any]) -> Optional[List[Any]]:
        """从转发载荷中提取节点列表。

        Args:
            payload: 转发段 ``data`` 或 ``get_forward_msg`` 返回的载荷。

        Returns:
            Optional[List[Any]]: 提取到的节点列表；当载荷中不存在节点列表时返回 ``None``。
        """
        direct_messages = payload.get("messages")
        if isinstance(direct_messages, list):
            return direct_messages

        direct_content = payload.get("content")
        if isinstance(direct_content, list):
            return direct_content

        nested_data = payload.get("data")
        if isinstance(nested_data, Mapping):
            nested_messages = nested_data.get("messages")
            if isinstance(nested_messages, list):
                return nested_messages

            nested_content = nested_data.get("content")
            if isinstance(nested_content, list):
                return nested_content

        return None

    async def _build_forward_nodes(self, messages: List[Any]) -> List[Dict[str, Any]]:
        """将 OneBot 转发节点列表转换为 Host 转发节点列表。

        Args:
            messages: 对端返回的转发节点列表。

        Returns:
            List[Dict[str, Any]]: Host 侧可识别的转发节点列表。
        """
        forward_nodes: List[Dict[str, Any]] = []
        for forward_message in messages:
            if not isinstance(forward_message, Mapping):
                continue

            raw_content = self._extract_forward_node_content(forward_message)
            content_segments = await self._convert_forward_content(raw_content, "")
            sender = self._extract_forward_node_sender(forward_message)

            node_data = forward_message.get("data", {})
            if not isinstance(node_data, Mapping):
                node_data = {}

            forward_nodes.append(
                {
                    "user_id": str(
                        sender.get("user_id")
                        or sender.get("uin")
                        or node_data.get("user_id")
                        or node_data.get("uin")
                        or ""
                    ).strip()
                    or None,
                    "user_nickname": str(
                        sender.get("nickname")
                        or sender.get("name")
                        or node_data.get("nickname")
                        or node_data.get("name")
                        or "未知用户"
                    ),
                    "user_cardname": str(sender.get("card") or node_data.get("card") or "").strip() or None,
                    "message_id": str(
                        forward_message.get("message_id")
                        or forward_message.get("id")
                        or node_data.get("id")
                        or uuid4().hex
                    ),
                    "content": content_segments or [self._build_text_segment("[empty]")],
                }
            )
        return forward_nodes

    def _extract_forward_node_content(self, forward_message: Mapping[str, Any]) -> Any:
        """提取单个转发节点中的消息段列表。

        Args:
            forward_message: 对端返回的单个转发节点。

        Returns:
            Any: 原始消息段列表；不存在时返回空列表。
        """
        direct_content = forward_message.get("content")
        if isinstance(direct_content, list):
            return direct_content

        direct_message = forward_message.get("message")
        if isinstance(direct_message, list):
            return direct_message

        node_data = forward_message.get("data", {})
        if not isinstance(node_data, Mapping):
            return []

        nested_content = node_data.get("content")
        if isinstance(nested_content, list):
            return nested_content

        nested_message = node_data.get("message")
        if isinstance(nested_message, list):
            return nested_message

        return []

    def _extract_forward_node_sender(self, forward_message: Mapping[str, Any]) -> Mapping[str, Any]:
        """提取单个转发节点的发送者信息。

        Args:
            forward_message: 对端返回的单个转发节点。

        Returns:
            Mapping[str, Any]: 归一化后的发送者信息映射。
        """
        sender = forward_message.get("sender", {})
        if isinstance(sender, Mapping):
            return sender

        node_data = forward_message.get("data", {})
        if not isinstance(node_data, Mapping):
            return {}

        normalized_sender: Dict[str, Any] = {}
        user_id = str(node_data.get("user_id") or node_data.get("uin") or "").strip()
        nickname = str(node_data.get("nickname") or node_data.get("name") or "").strip()
        cardname = str(node_data.get("card") or "").strip()
        if user_id:
            normalized_sender["user_id"] = user_id
            normalized_sender["uin"] = user_id
        if nickname:
            normalized_sender["nickname"] = nickname
            normalized_sender["name"] = nickname
        if cardname:
            normalized_sender["card"] = cardname
        return normalized_sender

    async def _convert_forward_content(self, raw_content: Any, self_id: str) -> QQSegments:
        """转换转发节点内部的消息段列表。

        Args:
            raw_content: 转发节点原始内容。
            self_id: 当前机器人账号 ID。

        Returns:
            QQSegments: 转换后的消息段列表。
        """
        if not isinstance(raw_content, list):
            return []

        normalized_segments = self._normalize_incoming_segments(raw_content)
        if not normalized_segments:
            return []

        # 转发节点的引用可能不在当前账号的消息库中，只保留引用 ID。
        segments, _ = await self._convert_incoming_segments(
            normalized_segments, self_id, "", resolve_reply_details=False
        )
        return segments
