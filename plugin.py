"""SnowLuma 适配器（统一 QQ 连接器）插件。

以 SnowLuma 适配器的模块结构为基底，合并 SnowLuma 适配器的特性：
1. 作为客户端连接 SnowLuma / NapCat / OneBot v11 正向 WebSocket 服务，
   连接后通过 ``get_version_info`` 自动判定对端并应用对应能力画像。
2. 将入站消息、通知事件与元事件转换为 Host 侧结构。
3. 将 Host 出站消息转换为按画像定制的 OneBot 动作序列并发送。
4. 通过公开 API 暴露 QQ 平台专属查询与管理动作（含 SnowLuma 专属 QZone 组）。
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
from .runtime import QQEventRouter, QQRuntimeBuilder, QQRuntimeBundle
from .services import QQActionService, QQQueryService


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

    async def on_load(self) -> None:
        """在插件加载时根据配置决定是否启动连接。"""
        await self._sync_private_chat_tool_component_state()
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
        await self._sync_private_chat_tool_component_state()
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

    async def _sync_private_chat_tool_component_state(self) -> None:
        """按配置同步主动私聊工具组件的启停状态。"""

        enabled = self._load_settings().plugin.enable_private_chat_tool
        tool_names = ("open_private_chat", "get_qq_by_msg_id")
        try:
            for tool_name in tool_names:
                if enabled:
                    result = await self.ctx.component.enable_component(tool_name, "TOOL")
                else:
                    result = await self.ctx.component.disable_component(tool_name, "TOOL")
                if isinstance(result, Mapping) and not bool(result.get("success", False)):
                    self.ctx.logger.warning(
                        f"同步主动私聊工具启停状态失败: tool={tool_name} "
                        f"error={result.get('error') or result}"
                    )
        except Exception as exc:
            self.ctx.logger.warning(f"同步主动私聊工具启停状态失败: {exc}")

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
