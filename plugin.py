"""SnowLuma 适配器（统一 QQ 连接器）插件。

以 SnowLuma 适配器的模块结构为基底，合并 SnowLuma 适配器的特性：
1. 作为客户端连接 SnowLuma / NapCat / OneBot v11 正向 WebSocket 服务，
   连接后通过 ``get_version_info`` 自动判定对端并应用对应能力画像。
2. 将入站消息、通知事件与元事件转换为 Host 侧结构。
3. 将 Host 出站消息转换为按画像定制的 OneBot 动作序列并发送。
4. 通过公开 API 暴露 QQ 平台专属查询与管理动作（含 SnowLuma 专属 QZone 组）。
5. 提供可配置开关的 LLM 工具：主动私聊、戳一戳、消息撤回、智能禁言、表情表态与消息转发（附活跃聊天流查询）。
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Mapping, Optional, cast

from maibot_sdk import MaiBotPlugin, MessageGateway, PluginConfigBase, Tool
from maibot_sdk.types import ToolParameterInfo, ToolParamType

from .apis import (
    QQAccountApiMixin,
    QQFileApiMixin,
    QQGroupApiMixin,
    QQMessageApiMixin,
    QQQzoneApiMixin,
    QQSystemApiMixin,
)
from .config import QQPluginSettings
from .constants import SNOWLUMA_GATEWAY_NAME
from .debug import AdaDebugLogger
from .profile import (
    MSG_ACTION_STYLE_GENERIC,
    PROFILE_BY_TYPE,
    ClientProfile,
    ProfileState,
)
from .qq_face_map import QQ_FACE_DESCRIPTIONS
from .runtime import QQEventRouter, QQRuntimeBuilder, QQRuntimeBundle
from .services import QQActionService, QQQueryService


def _matches_scoped_identifier(allowed_values: List[str], current_value: str) -> bool:
    """兼容 ``platform:id`` 与纯 ID 两种配置格式。"""

    normalized_current_value = str(current_value or "").strip()
    if not normalized_current_value:
        return False

    for allowed_value in allowed_values:
        normalized_allowed_value = str(allowed_value or "").strip()
        if not normalized_allowed_value:
            continue
        if normalized_allowed_value == normalized_current_value:
            return True
        if normalized_allowed_value.endswith(f":{normalized_current_value}"):
            return True
    return False


class SnowLumaAdapterPlugin(
    QQAccountApiMixin,
    QQFileApiMixin,
    QQGroupApiMixin,
    QQMessageApiMixin,
    QQQzoneApiMixin,
    QQSystemApiMixin,
    MaiBotPlugin,
):
    """SnowLuma / SnowLuma / NapCat 统一消息网关与 QQ 能力插件。"""

    config_model: ClassVar[type[PluginConfigBase] | None] = QQPluginSettings

    def __init__(self) -> None:
        """初始化适配器插件实例。"""
        super().__init__()
        self._action_service: Optional[QQActionService] = None
        self._query_service: Optional[QQQueryService] = None
        self._event_router: Optional[QQEventRouter] = None
        self._runtime_bundle: Optional[QQRuntimeBundle] = None
        self._debug_logger: Optional[AdaDebugLogger] = None

    def get_components(self) -> List[Dict[str, Any]]:
        """收集组件，并为 NapCat API 注册同名 SnowLuma 别名。"""
        components = super().get_components()
        aliases: List[Dict[str, Any]] = []
        for component in components:
            if component["type"] != "API" or not component["name"].startswith("adapter.napcat."):
                continue
            # 保留原处理器和完整元数据，让两个前缀共享参数、返回值及能力校验。
            aliases.append(
                {
                    **component,
                    "name": "adapter.snowluma." + component["name"].removeprefix("adapter.napcat."),
                    "metadata": dict(component["metadata"]),
                }
            )
        return components + aliases

    async def on_load(self) -> None:
        """在插件加载时根据配置决定是否启动连接。"""
        await self._sync_tool_components_state()
        await self._restart_connection_if_needed()

    async def on_unload(self) -> None:
        """在插件卸载时关闭连接。"""
        await self._stop_connection()

    async def on_config_update(self, scope: str, config_data: Dict[str, Any], version: str) -> None:
        """在配置更新后热重载连接（含 client_type 热切换）。

        Args:
            scope: 配置变更范围。
            config_data: 最新的配置数据。
            version: 配置版本号。
        """
        if scope != "self":
            return

        self.set_plugin_config(config_data)
        if version:
            self.ctx.logger.debug(f"适配器收到配置更新通知: {version}")
        await self._sync_tool_components_state()
        await self._restart_connection_if_needed()

    @Tool(
        "open_private_chat",
        description=(
            "向指定 QQ 用户发送一条私聊消息，用于主动开启私聊。"
            "请在宿主适配器策略中放行该私聊。"
        ),
        parameters=[
            ToolParameterInfo(
                name="user_id",
                param_type=ToolParamType.STRING,
                description="要开启私聊的 QQ 用户 ID，必须是正整数。",
                required=True,
            ),
            ToolParameterInfo(
                name="message",
                param_type=ToolParamType.STRING,
                description="要发送给该用户的第一条私聊消息。",
                required=True,
            ),
        ],
        enabled=False,
        visibility="visible",
    )
    async def tool_open_private_chat(
        self,
        user_id: Any = "",
        message: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """主动向指定用户发送私聊消息。"""
        del kwargs

        try:
            normalized_user_id = str(self._normalize_positive_int(user_id, "user_id"))
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

        normalized_message = str(message or "").strip()
        if not normalized_message:
            return {"success": False, "error": "私聊消息不能为空"}

        runtime_bundle = self._require_runtime_bundle()
        settings = self._load_settings()
        login_info = await runtime_bundle.query_service.get_login_info()
        account_id = str((login_info or {}).get("user_id") or "").strip()
        if not account_id:
            return {"success": False, "error": "无法获取当前登录账号"}

        open_session_result = await self.ctx.chat.open_session(
            platform="qq",
            chat_type="private",
            user_id=normalized_user_id,
            account_id=account_id,
            scope=settings.client.connection_id,
        )
        if not isinstance(open_session_result, Mapping) or not bool(open_session_result.get("success", False)):
            error = str(open_session_result.get("error") or "").strip() if isinstance(open_session_result, Mapping) else ""
            return {
                "success": False,
                "error": error or "打开私聊会话失败",
                "open_session_result": open_session_result,
            }

        # 发送动作按画像取值：NapCat 用 send_private_msg，SnowLuma 用通用 send_msg。
        profile = runtime_bundle.profile
        if profile.msg_action_style == MSG_ACTION_STYLE_GENERIC:
            action_name = "send_msg"
            action_params: Dict[str, Any] = {
                "message_type": "private",
                "user_id": int(normalized_user_id),
                "message": [{"type": "text", "data": {"text": normalized_message}}],
            }
        else:
            action_name = "send_private_msg"
            action_params = {
                "user_id": int(normalized_user_id),
                "message": [{"type": "text", "data": {"text": normalized_message}}],
            }

        try:
            response = await runtime_bundle.action_service.call_action(action_name, action_params)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        response_data = response.get("data", {})
        message_id = str(response_data.get("message_id") or "") if isinstance(response_data, Mapping) else ""
        self.ctx.logger.info(
            f"已主动开启私聊: user_id={normalized_user_id} message_id={message_id or '<unknown>'}"
        )
        return {
            "success": True,
            "content": (
                f"已向用户 {normalized_user_id} 发送私聊消息。"
                "请确认宿主适配器策略允许该私聊的入站消息。"
            ),
            "user_id": normalized_user_id,
            "stream_id": str(open_session_result.get("session_id") or open_session_result.get("stream_id") or ""),
            "session": open_session_result.get("stream") or {},
            "message_id": message_id,
        }

    @Tool(
        "get_qq_by_msg_id",
        description="根据当前聊天中的消息 ID 获取该消息发送者的 QQ 用户 ID。",
        parameters=[
            ToolParameterInfo(
                name="msg_id",
                param_type=ToolParamType.STRING,
                description="目标用户发送的消息 ID。",
                required=True,
            ),
        ],
        enabled=False,
        visibility="visible",
    )
    async def tool_get_qq_by_msg_id(
        self,
        msg_id: str = "",
        stream_id: str = "",
        chat_id: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """根据消息 ID 查询该消息发送者的 QQ 号。"""
        del kwargs

        normalized_msg_id = str(msg_id or "").strip()
        if not normalized_msg_id:
            return {"success": False, "error": "缺少目标消息 ID"}

        target_stream_id = str(stream_id or chat_id or "").strip()
        query_result = await self.ctx.message.get_by_id(
            normalized_msg_id,
            stream_id=target_stream_id,
            include_binary_data=False,
        )
        if not isinstance(query_result, Mapping):
            return {"success": False, "error": f"未找到消息: {normalized_msg_id}", "msg_id": normalized_msg_id}

        message_info = query_result.get("message_info", {})
        user_info = message_info.get("user_info", {}) if isinstance(message_info, Mapping) else {}
        user_info = user_info if isinstance(user_info, Mapping) else {}
        user_id = str(user_info.get("user_id") or "").strip()
        if not user_id:
            return {"success": False, "error": f"消息 {normalized_msg_id} 缺少发送者 QQ 号", "msg_id": normalized_msg_id}

        user_nickname = str(user_info.get("user_nickname") or "").strip()
        user_cardname = str(user_info.get("user_cardname") or "").strip()
        display_name = user_cardname or user_nickname or user_id
        group_info = message_info.get("group_info", {})
        group_info = group_info if isinstance(group_info, Mapping) else {}
        return {
            "success": True,
            "content": f"消息 {normalized_msg_id} 的发送者是 {display_name}，QQ 号为 {user_id}。",
            "msg_id": normalized_msg_id,
            "user_id": user_id,
            "qq": user_id,
            "user_nickname": user_nickname,
            "user_cardname": user_cardname,
            "display_name": display_name,
            "platform": str(query_result.get("platform") or "").strip(),
            "session_id": str(query_result.get("session_id") or target_stream_id).strip(),
            "group_id": str(group_info.get("group_id") or "").strip(),
            "group_name": str(group_info.get("group_name") or "").strip(),
        }

    @Tool(
        "send_poke",
        description=(
            "对指定消息的发送者发送戳一戳。"
            "群聊消息在该消息所在的群内戳；私聊消息则发送好友戳一戳。"
        ),
        parameters=[
            ToolParameterInfo(
                name="msg_id",
                param_type=ToolParamType.STRING,
                description="目标用户发送的消息 ID，戳一戳对象是该消息的发送者。",
                required=True,
            ),
        ],
        enabled=False,
        visibility="visible",
    )
    async def tool_send_poke(
        self,
        msg_id: Any = "",
        stream_id: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """对指定消息的发送者发送戳一戳。"""
        del kwargs

        normalized_msg_id = str(msg_id or "").strip()
        if not normalized_msg_id:
            return {"success": False, "error": "缺少目标消息 ID"}

        # 通过消息 ID 定位发送者与消息所在群。
        query_result = await self.ctx.message.get_by_id(
            normalized_msg_id,
            stream_id=stream_id,
            include_binary_data=False,
        )
        message_info = query_result.get("message_info", {}) if isinstance(query_result, Mapping) else {}
        user_info = message_info.get("user_info", {}) if isinstance(message_info, Mapping) else {}
        target_user_id = str(user_info.get("user_id") or "").strip()
        if not target_user_id:
            return {"success": False, "error": f"未找到消息 {normalized_msg_id} 或其缺少发送者信息"}
        try:
            normalized_user_id = self._normalize_positive_int(target_user_id, "user_id")
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

        # 群上下文由消息自身决定：群聊消息带群号，私聊消息无群号则发送好友戳一戳。
        message_group_info = message_info.get("group_info") if isinstance(message_info, Mapping) else None
        message_group_info = message_group_info if isinstance(message_group_info, Mapping) else {}
        normalized_group_id: Optional[int] = None
        resolved_group_id = str(message_group_info.get("group_id") or "").strip()
        if resolved_group_id:
            try:
                normalized_group_id = self._normalize_positive_int(resolved_group_id, "group_id")
            except ValueError as exc:
                return {"success": False, "error": str(exc)}

        try:
            await self._require_query_service().send_poke(
                user_id=normalized_user_id,
                group_id=normalized_group_id,
            )
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        target_display_name = (
            str(user_info.get("user_cardname") or "").strip()
            or str(user_info.get("user_nickname") or "").strip()
            or str(normalized_user_id)
        )
        scope_text = f"群 {normalized_group_id} 中" if normalized_group_id is not None else "私聊中"
        self.ctx.logger.info(
            f"已发送戳一戳: user_id={normalized_user_id} group_id={normalized_group_id or '<private>'} "
            f"msg_id={normalized_msg_id}"
        )
        return {
            "success": True,
            "content": f"已在{scope_text}向 {target_display_name} 发送戳一戳。",
            "user_id": str(normalized_user_id),
            "group_id": str(normalized_group_id) if normalized_group_id is not None else "",
            "msg_id": normalized_msg_id,
        }

    @Tool(
        "recall_message",
        description=(
            "撤回一条 QQ 消息。撤回自己发送的消息通常限 2 分钟内；"
            "撤回他人消息需要机器人是群管理员。message_id 使用聊天记录中的消息 ID。"
        ),
        parameters=[
            ToolParameterInfo(
                name="message_id",
                param_type=ToolParamType.STRING,
                description="要撤回的消息 ID，来自聊天记录中的消息 ID。",
                required=True,
            ),
        ],
        enabled=False,
        visibility="visible",
    )
    async def tool_recall_message(
        self,
        message_id: Any = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """撤回指定消息。"""
        del kwargs

        # 聊天记录中的消息 ID 即平台真实 ID：入站消息直接透传对端 message_id，
        # 机器人自发消息会经 message_id_echo 回填为平台 ID。
        try:
            normalized_message_id = self._normalize_message_id(message_id, "message_id")
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

        try:
            await self._require_query_service().delete_message(message_id=normalized_message_id)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        self.ctx.logger.info(f"已撤回消息: message_id={normalized_message_id}")
        return {
            "success": True,
            "content": f"已撤回消息 {normalized_message_id}。",
            "message_id": str(normalized_message_id),
        }

    @Tool(
        "mute",
        description=(
            "在群聊中根据消息 ID 禁言该消息的发送者。"
            "适用于刷屏、违规发言、用户主动要求被禁言等情况。"
            "群主、管理员和保护名单中的用户不会被禁言；时长会被限制在配置范围内。"
        ),
        parameters=[
            ToolParameterInfo(
                name="msg_id",
                param_type=ToolParamType.STRING,
                description="要禁言的目标所发送的消息 ID。",
                required=True,
            ),
            ToolParameterInfo(
                name="duration",
                param_type=ToolParamType.INTEGER,
                description="禁言时长，单位秒，正整数。",
                required=True,
            ),
            ToolParameterInfo(
                name="reason",
                param_type=ToolParamType.STRING,
                description="禁言原因，可选。",
                required=False,
            ),
        ],
        enabled=False,
        visibility="visible",
    )
    async def tool_mute(
        self,
        msg_id: Any = "",
        duration: Any = "",
        group_id: Any = "",
        stream_id: str = "",
        reason: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """根据消息 ID 禁言发送者。"""
        del kwargs

        normalized_group_id = str(group_id or "").strip()
        if not normalized_group_id:
            return {"success": False, "error": "禁言仅支持群聊，当前会话缺少群号"}

        settings = self._load_settings()
        mute_settings = settings.mute

        # 群白名单：非空时仅放行名单内的群。
        allowed_groups = [str(item).strip() for item in mute_settings.allowed_groups if str(item).strip()]
        if allowed_groups and not _matches_scoped_identifier(allowed_groups, normalized_group_id):
            return {"success": False, "error": f"群 {normalized_group_id} 不在禁言白名单内"}

        normalized_msg_id = str(msg_id or "").strip()
        if not normalized_msg_id:
            return {"success": False, "error": "缺少目标消息 ID"}

        try:
            normalized_duration = self._normalize_positive_int(duration, "duration")
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        if normalized_duration < mute_settings.min_duration:
            normalized_duration = mute_settings.min_duration
        if normalized_duration > mute_settings.max_duration:
            normalized_duration = mute_settings.max_duration

        # 通过消息 ID 定位发送者，复用宿主消息查询能力。
        query_result = await self.ctx.message.get_by_id(
            normalized_msg_id,
            stream_id=stream_id,
            include_binary_data=False,
        )
        message_info = query_result.get("message_info", {}) if isinstance(query_result, Mapping) else {}
        user_info = message_info.get("user_info", {}) if isinstance(message_info, Mapping) else {}
        target_user_id = str(user_info.get("user_id") or "").strip()
        if not target_user_id:
            return {"success": False, "error": f"未找到消息 {normalized_msg_id} 或其缺少发送者信息"}
        target_display_name = (
            str(user_info.get("user_cardname") or "").strip()
            or str(user_info.get("user_nickname") or "").strip()
            or target_user_id
        )

        # 保护名单：配置内用户一律不禁言。
        admin_users = [str(item).strip() for item in mute_settings.admin_users if str(item).strip()]
        if _matches_scoped_identifier(admin_users, target_user_id):
            return {"success": False, "error": f"用户 {target_display_name} 在禁言保护名单中，无法被禁言"}

        # 平台角色检查：群主和管理员不能被禁言，避免对端报错前的无效调用。
        member_info = await self._require_query_service().get_group_member_info(
            group_id=normalized_group_id,
            user_id=target_user_id,
            no_cache=True,
        )
        target_role = str((member_info or {}).get("role") or "").strip().lower()
        if target_role in {"owner", "admin"}:
            role_text = "群主" if target_role == "owner" else "管理员"
            return {"success": False, "error": f"{target_display_name} 是{role_text}，不能被禁言"}

        normalized_reason = str(reason or "").strip()
        try:
            await self._require_query_service().set_group_ban(
                group_id=self._normalize_positive_int(normalized_group_id, "group_id"),
                user_id=self._normalize_positive_int(target_user_id, "user_id"),
                duration=normalized_duration,
            )
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        self.ctx.logger.info(
            f"已禁言: group_id={normalized_group_id} user_id={target_user_id} "
            f"target={target_display_name} duration={normalized_duration} reason={normalized_reason or '<none>'}"
        )
        return {
            "success": True,
            "content": f"已禁言 {target_display_name}，时长 {normalized_duration} 秒。",
            "group_id": normalized_group_id,
            "user_id": target_user_id,
            "duration": normalized_duration,
            "reason": normalized_reason,
        }

    @Tool(
        "react_emoji",
        description=(
            "给一条消息贴表情表态（消息回应），如点赞、爱心等。"
            "常用表情 ID：76=赞、66=爱心、63=玫瑰、21=可爱、28=憨笑、"
            "5=流泪、9=大哭、6=害羞、78=握手、144=喝彩。"
        ),
        parameters=[
            ToolParameterInfo(
                name="message_id",
                param_type=ToolParamType.STRING,
                description="要贴表情的消息 ID，来自聊天记录中的消息 ID。",
                required=True,
            ),
            ToolParameterInfo(
                name="emoji_id",
                param_type=ToolParamType.INTEGER,
                description="QQ 表情 ID，如 76 表示赞。",
                required=True,
            ),
        ],
        enabled=False,
        visibility="visible",
    )
    async def tool_react_emoji(
        self,
        message_id: Any = "",
        emoji_id: Any = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """给指定消息贴表情表态。"""
        del kwargs

        try:
            normalized_message_id = self._normalize_message_id(message_id, "message_id")
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

        try:
            normalized_emoji_id = self._normalize_positive_int(emoji_id, "emoji_id")
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

        try:
            await self._require_query_service().set_message_emoji_like(
                message_id=normalized_message_id,
                emoji_id=normalized_emoji_id,
                set_like=True,
            )
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        emoji_name = QQ_FACE_DESCRIPTIONS.get(str(normalized_emoji_id), "")
        emoji_text = f"[{emoji_name}]" if emoji_name else f"[表情{normalized_emoji_id}]"
        self.ctx.logger.info(
            f"已贴表情表态: message_id={normalized_message_id} emoji_id={normalized_emoji_id}"
        )
        return {
            "success": True,
            "content": f"已对消息 {normalized_message_id} 贴上{emoji_text}表情。",
            "message_id": str(normalized_message_id),
            "emoji_id": normalized_emoji_id,
            "emoji_name": emoji_name or None,
        }

    @Tool(
        "list_chat_streams",
        description=(
            "列出当前所有活跃的 QQ 聊天流（群聊和私聊），"
            "返回每个流的显示名称、类型、群号或用户 QQ 号。"
            "常用于在转发消息前选择目标聊天流。"
        ),
        parameters=[],
        visibility="visible",
    )
    async def tool_list_chat_streams(self, **kwargs: Any) -> Dict[str, Any]:
        """列出所有活跃聊天流。"""
        del kwargs

        streams = await self.ctx.chat.get_all_streams(platform="qq")
        if not isinstance(streams, list):
            error = str((streams or {}).get("error") or "") if isinstance(streams, Mapping) else ""
            return {"success": False, "error": error or "获取聊天流列表失败"}

        # 显示名优先用实际名称（群名 / xxx的私聊），而不是裸 session_id。
        stream_entries: List[Dict[str, Any]] = []
        for stream in streams:
            if not isinstance(stream, Mapping):
                continue
            group_id = str(stream.get("group_id") or "").strip()
            user_id = str(stream.get("user_id") or "").strip()
            is_group = bool(stream.get("is_group_session"))
            if is_group:
                display_name = str(stream.get("group_name") or "").strip() or f"群 {group_id}"
            else:
                peer_name = (
                    str(stream.get("user_cardname") or "").strip()
                    or str(stream.get("user_nickname") or "").strip()
                )
                display_name = f"{peer_name}的私聊" if peer_name else (f"QQ {user_id} 的私聊" if user_id else "未知私聊")
            if not group_id and not user_id:
                continue
            stream_entries.append(
                {
                    "display_name": display_name,
                    "chat_type": "group" if is_group else "private",
                    "group_id": group_id,
                    "user_id": user_id,
                    "stream_id": str(stream.get("stream_id") or stream.get("session_id") or "").strip(),
                }
            )

        if not stream_entries:
            return {"success": True, "content": "当前没有活跃的聊天流。", "streams": [], "count": 0}

        lines: List[str] = []
        for index, entry in enumerate(stream_entries, start=1):
            if entry["chat_type"] == "group":
                lines.append(f"{index}. [群聊] {entry['display_name']}（群号 {entry['group_id']}）")
            else:
                lines.append(f"{index}. [私聊] {entry['display_name']}（QQ {entry['user_id']}）")
        return {
            "success": True,
            "content": f"当前活跃聊天流共 {len(stream_entries)} 个：\n" + "\n".join(lines),
            "streams": stream_entries,
            "count": len(stream_entries),
        }

    @Tool(
        "forward_messages",
        description=(
            "把一批消息打包成合并转发消息，发送到指定的群或私聊。"
            "目标群号或用户 QQ 号可先用 list_chat_streams 查询。"
            "消息 ID 来自聊天记录，将按传入顺序组成转发记录。"
        ),
        parameters=[
            ToolParameterInfo(
                name="message_ids",
                param_type=ToolParamType.ARRAY,
                description="要转发的消息 ID 列表，按顺序排列。",
                required=True,
                items_schema={"type": "string", "description": "聊天记录中的消息 ID"},
            ),
            ToolParameterInfo(
                name="target_group_id",
                param_type=ToolParamType.STRING,
                description="目标群号；与 target_user_id 二选一。",
                required=False,
            ),
            ToolParameterInfo(
                name="target_user_id",
                param_type=ToolParamType.STRING,
                description="目标私聊用户 QQ 号；与 target_group_id 二选一。",
                required=False,
            ),
        ],
        enabled=False,
        visibility="visible",
    )
    async def tool_forward_messages(
        self,
        message_ids: Any = None,
        target_group_id: Any = "",
        target_user_id: Any = "",
        stream_id: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """把一批消息打包成合并转发发送到目标聊天。"""
        del kwargs

        if not isinstance(message_ids, list) or not message_ids:
            return {"success": False, "error": "message_ids 必须是非空消息 ID 数组"}

        # 保序去重，避免同一消息被重复查询与重复出现在转发记录中。
        normalized_message_ids = list(dict.fromkeys(str(item or "").strip() for item in message_ids))
        normalized_message_ids = [item for item in normalized_message_ids if item]
        if not normalized_message_ids:
            return {"success": False, "error": "message_ids 中没有有效的消息 ID"}
        if len(normalized_message_ids) > 50:
            return {"success": False, "error": "单次转发最多支持 50 条消息"}

        normalized_target_group_id = str(target_group_id or "").strip()
        normalized_target_user_id = str(target_user_id or "").strip()
        if bool(normalized_target_group_id) == bool(normalized_target_user_id):
            return {"success": False, "error": "target_group_id 与 target_user_id 必须二选一"}

        # 逐条取回消息并构造转发节点；查询范围限定在当前聊天流。
        forward_nodes: List[Dict[str, Any]] = []
        for message_id in normalized_message_ids:
            query_result = await self.ctx.message.get_by_id(
                message_id,
                stream_id=stream_id,
                include_binary_data=True,
            )
            message_dict = query_result if isinstance(query_result, Mapping) else None
            message_info = message_dict.get("message_info", {}) if isinstance(message_dict, Mapping) else {}
            user_info = message_info.get("user_info", {}) if isinstance(message_info, Mapping) else {}
            raw_message = message_dict.get("raw_message") if isinstance(message_dict, Mapping) else None
            sender_user_id = str(user_info.get("user_id") or "").strip()
            if not isinstance(raw_message, list) or not sender_user_id:
                return {"success": False, "error": f"未找到消息 {message_id} 或其缺少发送者信息"}
            forward_nodes.append(
                {
                    "user_id": sender_user_id,
                    "user_nickname": str(user_info.get("user_nickname") or "").strip(),
                    "user_cardname": str(user_info.get("user_cardname") or "").strip(),
                    "content": raw_message,
                }
            )

        # 组装 forward 段并复用出站编解码链路：参数键按画像取值，消息段统一编码。
        runtime_bundle = self._require_runtime_bundle()
        outbound_message: Dict[str, Any] = {
            "message_info": {"group_info": {}, "user_info": {}, "additional_config": {}},
            "raw_message": [{"type": "forward", "data": forward_nodes}],
        }
        route: Dict[str, Any] = {"group_id": normalized_target_group_id, "user_id": normalized_target_user_id}
        try:
            actions = runtime_bundle.outbound_codec.build_outbound_actions(outbound_message, route)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        try:
            for action_name, params in actions:
                await runtime_bundle.action_service.call_action(action_name, params)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        target_text = (
            f"群 {normalized_target_group_id}" if normalized_target_group_id else f"用户 {normalized_target_user_id} 的私聊"
        )
        self.ctx.logger.info(
            f"已发送合并转发: target={target_text} count={len(forward_nodes)} "
            f"message_ids={normalized_message_ids}"
        )
        return {
            "success": True,
            "content": f"已把 {len(forward_nodes)} 条消息打包成合并转发发送到{target_text}。",
            "target": target_text,
            "forwarded_count": len(forward_nodes),
            "message_ids": normalized_message_ids,
        }

    @MessageGateway(
        name=SNOWLUMA_GATEWAY_NAME,
        route_type="duplex",
        platform="qq",
        protocol="snowluma",
        description="SnowLuma / NapCat 正向 WebSocket 双工消息网关",
    )
    async def handle_snowluma_gateway(
        self,
        message: Dict[str, Any],
        route: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """处理 Host 出站消息并按画像发送到对端客户端。

        Args:
            message: Host 侧标准 ``MessageDict``。
            route: Platform IO 生成的路由信息。
            metadata: Platform IO 附带的投递元数据。
            **kwargs: 预留扩展参数。

        Returns:
            Dict[str, Any]: 标准化后的发送结果。
        """
        del metadata
        del kwargs

        runtime_bundle = self._require_runtime_bundle()
        debug_logger = self._debug_logger
        internal_message_id = str(message.get("message_id") or "").strip()

        try:
            actions = runtime_bundle.outbound_codec.build_outbound_actions(message, route or {})
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        responses: List[Mapping[str, Any]] = []
        for action_name, params in actions:
            if debug_logger is not None:
                debug_logger.log_raw_outbound(internal_message_id, action_name, params)
            try:
                response = await runtime_bundle.transport.call_action(action_name, params)
            except Exception as exc:
                return {"success": False, "error": str(exc), "metadata": {"action": action_name}}
            if not self._is_action_response_ok(response):
                return {
                    "success": False,
                    "error": str(response.get("wording") or response.get("message") or "send failed"),
                    "metadata": {"action": action_name, "retcode": response.get("retcode")},
                }
            responses.append(response)

        external_message_id = ""
        for response in responses:
            response_data = response.get("data", {})
            if isinstance(response_data, Mapping):
                external_message_id = str(response_data.get("message_id") or "")
                if external_message_id:
                    break

        adapter_callbacks = []
        if internal_message_id and external_message_id and internal_message_id != external_message_id:
            adapter_callbacks.append(
                {
                    "name": "message_id_echo",
                    "payload": {
                        "content": {
                            "type": "echo",
                            "echo": internal_message_id,
                            "actual_id": external_message_id,
                        }
                    },
                }
            )

        return {
            "success": True,
            "external_message_id": external_message_id or None,
            "metadata": {
                "action": actions[0][0] if len(actions) == 1 else "multiple",
                "actions": [action_name for action_name, _ in actions],
                "adapter_callbacks": adapter_callbacks,
            },
        }

    @staticmethod
    def _is_action_response_ok(response: Mapping[str, Any]) -> bool:
        """判定动作响应是否成功。

        兼容两类口径：标准 ``status == "ok"``，以及 SnowLuma 异步执行时
        ``retcode in {0, 1}`` 的响应。

        Args:
            response: 对端返回的原始响应字典。

        Returns:
            bool: 若响应表示成功则返回 ``True``。
        """
        status = str(response.get("status") or "").strip().lower()
        if status == "ok":
            return True
        retcode = response.get("retcode")
        return isinstance(retcode, int) and retcode in {0, 1}

    def _ensure_runtime_components(self) -> None:
        """确保运行时依赖对象已经完成初始化。"""
        if self._debug_logger is None:
            self._debug_logger = AdaDebugLogger(self.ctx.logger, self._load_settings)

        if self._event_router is None:
            self._event_router = QQEventRouter(
                gateway_capability=self.ctx.gateway,
                logger=self.ctx.logger,
                gateway_name=SNOWLUMA_GATEWAY_NAME,
                load_settings=self._load_settings,
            )

        if self._runtime_bundle is None:
            settings = self._load_settings()
            profile_state = ProfileState(self._resolve_initial_profile(settings))
            runtime_builder = QQRuntimeBuilder(
                gateway_capability=self.ctx.gateway,
                logger=self.ctx.logger,
                gateway_name=SNOWLUMA_GATEWAY_NAME,
            )
            self._runtime_bundle = runtime_builder.build(
                on_connection_opened=self._event_router.bootstrap_adapter_runtime_state,
                on_connection_closed=self._event_router.handle_transport_disconnected,
                on_payload=self._event_router.handle_transport_payload,
                on_natural_lift=self._event_router.emit_natural_lift_notice,
                on_heartbeat_timeout=self._event_router.handle_heartbeat_timeout,
                profile_state=profile_state,
                load_settings=self._load_settings,
            )
            self._runtime_bundle.transport.configure(settings.client, profile_state)
            self._event_router.bind_runtime(self._runtime_bundle)
            self._bind_runtime_aliases(self._runtime_bundle)

    @staticmethod
    def _resolve_initial_profile(settings: QQPluginSettings) -> ClientProfile:
        """根据配置声明解析连接建立前的初始画像。

        auto 模式下探测尚未完成，先以 画像占位（探测完成后由路由器写回）。

        Args:
            settings: 当前生效的插件配置。

        Returns:
            ClientProfile: 初始画像。
        """
        declared_type = settings.client.client_type
        return PROFILE_BY_TYPE.get(declared_type, PROFILE_BY_TYPE["napcat"])

    async def _sync_tool_components_state(self) -> None:
        """按配置同步全部 LLM 工具组件的启停状态。"""

        settings = self._load_settings()
        abilities = settings.chat_abilities
        tool_states = (
            ("open_private_chat", abilities.enable_private_chat_tool),
            ("get_qq_by_msg_id", abilities.enable_private_chat_tool),
            ("send_poke", abilities.enable_poke_tool),
            ("recall_message", abilities.enable_recall_tool),
            ("mute", abilities.enable_mute_tool),
            ("react_emoji", abilities.enable_emoji_like_tool),
            ("forward_messages", abilities.enable_forward_tool),
        )
        try:
            for tool_name, enabled in tool_states:
                if enabled:
                    result = await self.ctx.component.enable_component(tool_name, "TOOL")
                else:
                    result = await self.ctx.component.disable_component(tool_name, "TOOL")
                if isinstance(result, Mapping) and not bool(result.get("success", False)):
                    self.ctx.logger.warning(
                        f"同步工具启停状态失败: tool={tool_name} "
                        f"error={result.get('error') or result}"
                    )
        except Exception as exc:
            self.ctx.logger.warning(f"同步工具启停状态失败: {exc}")

    def _bind_runtime_aliases(self, runtime_bundle: QQRuntimeBundle) -> None:
        """同步运行时组件到插件级别的快捷引用。

        Args:
            runtime_bundle: 已初始化的运行时组件集合。
        """
        self._action_service = runtime_bundle.action_service
        self._query_service = runtime_bundle.query_service

    def _load_settings(self) -> QQPluginSettings:
        """返回当前生效的插件配置。

        Returns:
            QQPluginSettings: 当前生效的插件配置。
        """
        return cast(QQPluginSettings, self.config)

    async def _restart_connection_if_needed(self) -> None:
        """根据当前配置重启连接循环（client_type 热切换的入口）。"""
        self._ensure_runtime_components()
        runtime_bundle = self._require_runtime_bundle()
        settings = self._load_settings()

        await self._stop_connection()
        if not settings.should_connect():
            self.ctx.logger.info("适配器保持空闲状态，因为插件或配置未启用")
            return
        if not settings.validate_runtime_config(self.ctx.logger):
            return
        if not runtime_bundle.transport.is_available():
            self.ctx.logger.error("适配器依赖 aiohttp，但当前环境未安装该依赖")
            return

        runtime_bundle.regex_filter.reload_patterns(settings.filters.regex_filter_patterns)
        if settings.filters.regex_filter_enabled and settings.filters.regex_filter_patterns:
            self.ctx.logger.info(
                f"正则消息过滤已启用: 模式={settings.filters.regex_filter_mode}，"
                f"规则数={len(settings.filters.regex_filter_patterns)}"
            )
        if not settings.notice.enabled:
            self.ctx.logger.info("通知事件转发已整体关闭：所有通知都不会传入 Host")

        runtime_bundle.transport.configure(settings.client, runtime_bundle.profile_state)
        await runtime_bundle.transport.start()

    async def _stop_connection(self) -> None:
        """停止当前连接并清理运行时缓存。"""
        runtime_bundle = self._runtime_bundle
        if runtime_bundle is None:
            return

        await runtime_bundle.transport.stop()
        if self._event_router is not None:
            self._event_router.reset_caches()

    def _require_runtime_bundle(self) -> QQRuntimeBundle:
        """返回当前已初始化的运行时组件集合。

        Returns:
            QQRuntimeBundle: 当前运行时组件集合。

        Raises:
            RuntimeError: 当运行时尚未初始化时抛出。
        """
        self._ensure_runtime_components()
        runtime_bundle = self._runtime_bundle
        if runtime_bundle is None:
            raise RuntimeError("适配器运行时尚未初始化")
        return runtime_bundle


def create_plugin() -> SnowLumaAdapterPlugin:
    """创建插件实例。

    Returns:
        SnowLumaAdapterPlugin: SnowLuma 适配器插件实例。
    """
    return SnowLumaAdapterPlugin()
