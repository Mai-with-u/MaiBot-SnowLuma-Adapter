from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Literal, Mapping, Optional, Tuple
from urllib.parse import urlencode
from uuid import uuid4

from aiohttp import ClientSession, ClientTimeout, ClientWebSocketResponse, WSMsgType
from maibot_sdk import Field, MaiBotPlugin, MessageGateway, PluginConfigBase
from pydantic import field_validator

import asyncio
import base64
import hashlib
import json
import time


SNOWLUMA_GATEWAY_NAME = "snowluma_gateway"
SUPPORTED_CONFIG_VERSION = "1.0.0"
DEFAULT_CHAT_LIST_TYPE = "whitelist"


class SnowLumaPluginSection(PluginConfigBase):
    """插件开关配置。"""

    __ui_label__: ClassVar[str] = "插件设置"
    __ui_order__: ClassVar[int] = 0

    enabled: bool = Field(
        default=False,
        description="是否启用 SnowLuma 适配器。",
        json_schema_extra={
            "label": "启用适配器",
            "hint": "关闭时插件只注册消息网关，不会主动连接 SnowLuma。",
            "order": 0,
        },
    )
    config_version: str = Field(
        default=SUPPORTED_CONFIG_VERSION,
        description="当前配置结构版本。",
        json_schema_extra={
            "disabled": True,
            "hidden": True,
            "label": "配置版本",
            "order": 99,
        },
    )


class SnowLumaClientSection(PluginConfigBase):
    """SnowLuma WebSocket 连接配置。"""

    __ui_label__: ClassVar[str] = "SnowLuma 连接"
    __ui_order__: ClassVar[int] = 1

    server: str = Field(
        default="127.0.0.1",
        description="SnowLuma WebSocket 服务地址。",
        json_schema_extra={"label": "服务地址", "order": 0, "placeholder": "127.0.0.1"},
    )
    port: int = Field(
        default=3001,
        description="SnowLuma WebSocket 服务端口。",
        json_schema_extra={"label": "端口", "order": 1},
    )
    token: str = Field(
        default="",
        description="SnowLuma 访问令牌。",
        json_schema_extra={
            "label": "访问令牌",
            "input_type": "password",
            "order": 2,
            "placeholder": "可留空",
        },
    )
    connection_id: str = Field(
        default="",
        description="可选连接标识，用于区分多条适配器链路。",
        json_schema_extra={"label": "连接标识", "order": 3},
    )
    reconnect_delay_sec: float = Field(
        default=5.0,
        description="连接断开后的重连等待时间，单位为秒。",
        json_schema_extra={"label": "重连等待", "order": 4, "step": 1},
    )
    action_timeout_sec: float = Field(
        default=10.0,
        description="调用 SnowLuma 动作接口的超时时间，单位为秒。",
        json_schema_extra={"label": "动作超时", "order": 5, "step": 1},
    )

    def build_ws_url(self) -> str:
        """构造 SnowLuma WebSocket 地址。"""

        base_url = f"ws://{self.server}:{self.port}"
        if not self.token:
            return base_url
        return f"{base_url}?{urlencode({'access_token': self.token})}"


class SnowLumaChatSection(PluginConfigBase):
    """聊天名单过滤配置。"""

    __ui_label__: ClassVar[str] = "聊天过滤"
    __ui_order__: ClassVar[int] = 2

    enable_chat_list_filter: bool = Field(
        default=True,
        description="是否启用群聊与私聊名单过滤。",
        json_schema_extra={
            "hint": "关闭后将忽略 group_list 和 private_list，仅保留 ban_user_id 规则。",
            "label": "启用聊天名单过滤",
            "order": 0,
        },
    )
    show_dropped_chat_list_messages: bool = Field(
        default=False,
        description="是否记录未通过聊天名单过滤而被丢弃的消息。",
        json_schema_extra={
            "hint": "关闭后不记录群聊/私聊名单丢弃日志，默认关闭以减少刷屏。",
            "label": "显示聊天名单丢弃日志",
            "order": 1,
        },
    )
    group_list_type: Literal["whitelist", "blacklist"] = Field(
        default=DEFAULT_CHAT_LIST_TYPE,
        description="群聊名单模式。",
        json_schema_extra={
            "hint": "白名单模式只接收列表内群聊，黑名单模式则忽略列表内群聊。",
            "label": "群聊名单模式",
            "order": 2,
        },
    )
    group_list: List[str] = Field(
        default_factory=list,
        description="群聊名单中的群号列表。",
        json_schema_extra={
            "hint": "群号会被统一转换为字符串并自动去重。",
            "label": "群聊名单",
            "order": 3,
            "placeholder": "请输入群号",
        },
    )
    private_list_type: Literal["whitelist", "blacklist"] = Field(
        default=DEFAULT_CHAT_LIST_TYPE,
        description="私聊名单模式。",
        json_schema_extra={
            "hint": "白名单模式只接收列表内私聊，黑名单模式则忽略列表内私聊。",
            "label": "私聊名单模式",
            "order": 4,
        },
    )
    private_list: List[str] = Field(
        default_factory=list,
        description="私聊名单中的用户 ID 列表。",
        json_schema_extra={
            "hint": "用户 ID 会被统一转换为字符串并自动去重。",
            "label": "私聊名单",
            "order": 5,
            "placeholder": "请输入用户 ID",
        },
    )
    ban_user_id: List[str] = Field(
        default_factory=list,
        description="全局屏蔽的用户 ID 列表。",
        json_schema_extra={
            "hint": "这些用户的消息会在进入 Host 之前被直接丢弃。",
            "label": "全局屏蔽用户",
            "order": 6,
            "placeholder": "请输入用户 ID",
        },
    )
    ban_qq_bot: bool = Field(
        default=False,
        description="是否屏蔽 QQ 官方机器人消息。",
        json_schema_extra={
            "hint": "SnowLuma 推送中能识别出官方机器人标记时会丢弃对应消息。",
            "label": "屏蔽官方机器人",
            "order": 7,
        },
    )

    @field_validator("group_list_type", "private_list_type", mode="before")
    @classmethod
    def _normalize_list_types(cls, value: Any) -> Literal["whitelist", "blacklist"]:
        """规范化名单模式字段。"""

        normalized_value = str(value or DEFAULT_CHAT_LIST_TYPE).strip().lower()
        if normalized_value not in {"whitelist", "blacklist"}:
            return DEFAULT_CHAT_LIST_TYPE
        return normalized_value  # type: ignore[return-value]

    @field_validator("group_list", "private_list", "ban_user_id", mode="before")
    @classmethod
    def _normalize_id_lists(cls, value: Any) -> List[str]:
        """规范化 ID 列表字段。"""

        if value is None:
            return []
        raw_values = value if isinstance(value, list) else [value]
        normalized_values: List[str] = []
        seen_values: set[str] = set()
        for raw_value in raw_values:
            normalized_value = str(raw_value or "").strip()
            if not normalized_value or normalized_value in seen_values:
                continue
            normalized_values.append(normalized_value)
            seen_values.add(normalized_value)
        return normalized_values


class SnowLumaFilterSection(PluginConfigBase):
    """消息过滤配置。"""

    __ui_label__: ClassVar[str] = "消息过滤"
    __ui_order__: ClassVar[int] = 3

    ignore_self_message: bool = Field(
        default=True,
        description="是否忽略机器人自身发送的消息。",
        json_schema_extra={
            "hint": "建议保持开启，避免机器人处理自己刚刚发出的消息。",
            "label": "忽略自身消息",
            "order": 0,
        },
    )


class SnowLumaAdapterSettings(PluginConfigBase):
    """SnowLuma 适配器完整配置。"""

    plugin: SnowLumaPluginSection = Field(default_factory=SnowLumaPluginSection)
    luma_client: SnowLumaClientSection = Field(default_factory=SnowLumaClientSection)
    chat: SnowLumaChatSection = Field(default_factory=SnowLumaChatSection)
    filters: SnowLumaFilterSection = Field(default_factory=SnowLumaFilterSection)

    def should_connect(self) -> bool:
        """判断当前配置是否应该建立连接。"""

        return self.plugin.enabled


class SnowLumaAdapterPlugin(MaiBotPlugin):
    """SnowLuma 消息网关插件。"""

    config_model: ClassVar[type[PluginConfigBase] | None] = SnowLumaAdapterSettings

    def __init__(self) -> None:
        """初始化 SnowLuma 适配器插件。"""

        super().__init__()
        self._session: Optional[ClientSession] = None
        self._ws: Optional[ClientWebSocketResponse] = None
        self._connection_task: Optional[asyncio.Task[None]] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._response_pool: Dict[str, asyncio.Future[Dict[str, Any]]] = {}
        self._connected_account_id: str = ""
        self._group_name_cache: Dict[str, str] = {}

    async def on_load(self) -> None:
        """插件加载后按配置启动连接。"""

        await self._restart_connection_if_needed()

    async def on_unload(self) -> None:
        """插件卸载前关闭连接。"""

        await self._stop_connection()

    async def on_config_update(self, scope: str, config_data: Dict[str, Any], version: str) -> None:
        """配置更新后重启连接。"""

        if scope != "self":
            return

        self.set_plugin_config(config_data)
        if version:
            self.ctx.logger.debug(f"SnowLuma 适配器收到配置更新: {version}")
        await self._restart_connection_if_needed()

    @MessageGateway(
        name=SNOWLUMA_GATEWAY_NAME,
        route_type="duplex",
        platform="qq",
        protocol="snowluma",
        description="SnowLuma WebSocket 双工消息网关",
    )
    async def handle_snowluma_gateway(
        self,
        message: Dict[str, Any],
        route: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """处理 Host 出站消息并发送到 SnowLuma。"""

        del metadata
        del kwargs

        if self._ws is None:
            return {"success": False, "error": "SnowLuma WebSocket 尚未连接"}

        try:
            action_name, params = self._build_outbound_action(message, route or {})
            response = await self._call_action(action_name, params)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        if not isinstance(response, Mapping):
            return {"success": False, "error": "SnowLuma 返回了无效响应"}

        status = str(response.get("status") or "").lower()
        retcode = response.get("retcode")
        if status and status != "ok":
            return {
                "success": False,
                "error": str(response.get("wording") or response.get("message") or "SnowLuma send failed"),
                "metadata": {"retcode": retcode},
            }
        if isinstance(retcode, int) and retcode not in {0, 1}:
            return {
                "success": False,
                "error": str(response.get("wording") or response.get("message") or "SnowLuma send failed"),
                "metadata": {"retcode": retcode},
            }

        response_data = response.get("data", {})
        external_message_id = ""
        if isinstance(response_data, Mapping):
            external_message_id = str(response_data.get("message_id") or "")

        return {
            "success": True,
            "external_message_id": external_message_id or None,
            "metadata": {"action": action_name},
        }

    def _load_settings(self) -> SnowLumaAdapterSettings:
        """返回当前强类型配置。"""

        return self.config  # type: ignore[return-value]

    async def _restart_connection_if_needed(self) -> None:
        """根据当前配置重启连接循环。"""

        await self._stop_connection()
        settings = self._load_settings()
        if not settings.should_connect():
            self.ctx.logger.info("SnowLuma 适配器保持空闲状态，因为插件未启用")
            return

        self._stop_event = asyncio.Event()
        self._connection_task = asyncio.create_task(self._run_connection_loop(), name="snowluma-adapter-loop")

    async def _stop_connection(self) -> None:
        """停止连接循环并清理资源。"""

        if self._stop_event is not None:
            self._stop_event.set()

        task = self._connection_task
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            self._connection_task = None

        await self._disconnect()
        await self._report_gateway_ready(False)

    async def _run_connection_loop(self) -> None:
        """维持到 SnowLuma 的 WebSocket 连接。"""

        while self._stop_event is not None and not self._stop_event.is_set():
            settings = self._load_settings()
            try:
                await self._connect(settings)
                await self._bootstrap_runtime_state(settings)
                await self._listen()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.ctx.logger.warning(f"SnowLuma 连接异常，稍后重试: {exc}")
            finally:
                await self._disconnect()
                await self._report_gateway_ready(False)

            if self._stop_event is None or self._stop_event.is_set():
                break
            await asyncio.sleep(max(1.0, settings.luma_client.reconnect_delay_sec))

    async def _connect(self, settings: SnowLumaAdapterSettings) -> None:
        """建立 WebSocket 连接。"""

        timeout = ClientTimeout(total=10)
        self._session = ClientSession(timeout=timeout)
        self._ws = await self._session.ws_connect(settings.luma_client.build_ws_url())
        self.ctx.logger.info(f"SnowLuma WebSocket 已连接: {settings.luma_client.build_ws_url()}")

    async def _disconnect(self) -> None:
        """关闭 WebSocket 和未完成动作。"""

        if self._ws is not None:
            await self._ws.close()
            self._ws = None

        if self._session is not None:
            await self._session.close()
            self._session = None

        for future in self._response_pool.values():
            if not future.done():
                future.cancel()
        self._response_pool.clear()
        self._connected_account_id = ""

    async def _bootstrap_runtime_state(self, settings: SnowLumaAdapterSettings) -> None:
        """连接建立后激活消息网关路由。"""

        await self._report_gateway_ready(True, settings=settings)

    async def _report_gateway_ready(
        self,
        ready: bool,
        *,
        account_id: str = "",
        settings: Optional[SnowLumaAdapterSettings] = None,
    ) -> bool:
        """向 Host 上报消息网关运行状态。"""

        metadata: Dict[str, Any] = {}
        scope = ""
        if settings is not None:
            metadata["ws_url"] = settings.luma_client.build_ws_url()
            scope = settings.luma_client.connection_id

        try:
            return await self.ctx.gateway.update_state(
                gateway_name=SNOWLUMA_GATEWAY_NAME,
                ready=ready,
                platform="qq",
                account_id=account_id,
                scope=scope,
                metadata=metadata,
            )
        except Exception as exc:
            self.ctx.logger.warning(f"SnowLuma 消息网关状态上报失败: {exc}")
            return False

    async def _listen(self) -> None:
        """监听 SnowLuma 推送。"""

        if self._ws is None:
            return

        async for ws_message in self._ws:
            if ws_message.type == WSMsgType.TEXT:
                await self._handle_text_payload(ws_message.data)
                continue
            if ws_message.type == WSMsgType.BINARY:
                self.ctx.logger.debug("SnowLuma 收到二进制消息，已忽略")
                continue
            if ws_message.type in {WSMsgType.CLOSED, WSMsgType.ERROR}:
                break

    async def _handle_text_payload(self, raw_payload: str) -> None:
        """处理 SnowLuma 文本载荷。"""

        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            self.ctx.logger.warning(f"SnowLuma 收到非 JSON 文本: {raw_payload[:120]}")
            return

        if not isinstance(payload, dict):
            return

        echo = str(payload.get("echo") or "").strip()
        if echo:
            self._resolve_echo_response(echo, payload)
            return

        post_type = str(payload.get("post_type") or "").strip()
        if self_id := str(payload.get("self_id") or "").strip():
            await self._update_connected_account(self_id)
        if post_type == "message" or "message" in payload:
            asyncio.create_task(self._route_inbound_message(payload), name="snowluma-route-message")

    async def _update_connected_account(self, account_id: str) -> None:
        """从 SnowLuma 推送中更新当前账号 ID。"""

        if not account_id or account_id == self._connected_account_id:
            return
        self._connected_account_id = account_id
        await self._report_gateway_ready(True, account_id=account_id, settings=self._load_settings())

    def _resolve_echo_response(self, echo: str, payload: Dict[str, Any]) -> None:
        """回填动作调用响应。"""

        future = self._response_pool.pop(echo, None)
        if future is not None and not future.done():
            future.set_result(payload)

    async def _call_action(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """调用 SnowLuma OneBot 风格动作接口。"""

        if self._ws is None:
            raise RuntimeError("SnowLuma WebSocket 尚未连接")

        settings = self._load_settings()
        echo = uuid4().hex
        future: asyncio.Future[Dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._response_pool[echo] = future

        payload = {"action": action, "params": params, "echo": echo}
        await self._ws.send_str(json.dumps(payload, ensure_ascii=False))
        try:
            return await asyncio.wait_for(future, timeout=max(1.0, settings.luma_client.action_timeout_sec))
        finally:
            self._response_pool.pop(echo, None)

    async def _route_inbound_message(self, payload: Dict[str, Any]) -> None:
        """将 SnowLuma 入站消息转换为 Host 标准消息并注入。"""

        if not self._is_inbound_message_allowed(payload):
            return

        try:
            message_dict = await self._build_inbound_message_dict(payload)
        except ValueError as exc:
            self.ctx.logger.warning(f"SnowLuma 入站消息格式不受支持，已丢弃: {exc}")
            return

        external_message_id = str(payload.get("message_id") or "").strip()
        route_metadata: Dict[str, Any] = {}
        if self._connected_account_id:
            route_metadata["self_id"] = self._connected_account_id
        if connection_id := self._load_settings().luma_client.connection_id:
            route_metadata["connection_id"] = connection_id

        accepted = await self.ctx.gateway.route_message(
            gateway_name=SNOWLUMA_GATEWAY_NAME,
            message=message_dict,
            route_metadata=route_metadata,
            external_message_id=external_message_id,
            dedupe_key=external_message_id,
        )
        if not accepted:
            self.ctx.logger.debug(f"Host 丢弃了 SnowLuma 入站消息: {external_message_id or '无消息 ID'}")

    def _is_inbound_message_allowed(self, payload: Mapping[str, Any]) -> bool:
        """检查入站消息是否通过聊天黑白名单过滤。"""

        settings = self._load_settings()
        sender = payload.get("sender", {})
        if not isinstance(sender, Mapping):
            sender = {}

        sender_user_id = str(payload.get("user_id") or sender.get("user_id") or "").strip()
        group_id = str(payload.get("group_id") or "").strip()
        if not sender_user_id:
            return False

        if (
            settings.filters.ignore_self_message
            and self._connected_account_id
            and sender_user_id == self._connected_account_id
        ):
            return False

        if sender_user_id in settings.chat.ban_user_id:
            self.ctx.logger.warning(f"SnowLuma 用户 {sender_user_id} 在全局禁止名单中，消息已丢弃")
            return False

        if settings.chat.ban_qq_bot and self._is_official_qq_bot_payload(payload, sender):
            self.ctx.logger.debug(f"SnowLuma 官方机器人消息已丢弃: user_id={sender_user_id}")
            return False

        if not settings.chat.enable_chat_list_filter:
            return True

        if group_id:
            allowed = self._is_id_allowed_by_list_policy(
                group_id,
                settings.chat.group_list_type,
                settings.chat.group_list,
            )
            if not allowed:
                self._log_chat_list_rejection(
                    settings.chat.show_dropped_chat_list_messages,
                    f"SnowLuma 群聊 {group_id} 未通过聊天名单过滤，消息已丢弃",
                )
            return allowed

        allowed = self._is_id_allowed_by_list_policy(
            sender_user_id,
            settings.chat.private_list_type,
            settings.chat.private_list,
        )
        if not allowed:
            self._log_chat_list_rejection(
                settings.chat.show_dropped_chat_list_messages,
                f"SnowLuma 私聊用户 {sender_user_id} 未通过聊天名单过滤，消息已丢弃",
            )
        return allowed

    def _log_chat_list_rejection(self, enabled: bool, message: str) -> None:
        """按配置决定是否记录聊天名单过滤丢弃日志。"""

        if enabled:
            self.ctx.logger.warning(message)

    @staticmethod
    def _is_id_allowed_by_list_policy(target_id: str, list_type: str, configured_ids: List[str]) -> bool:
        """根据白名单或黑名单规则判断目标 ID 是否允许通过。"""

        if list_type == "whitelist":
            return target_id in configured_ids
        return target_id not in configured_ids

    @staticmethod
    def _is_official_qq_bot_payload(payload: Mapping[str, Any], sender: Mapping[str, Any]) -> bool:
        """尽力识别 QQ 官方机器人或频道机器人消息。"""

        role_values = {
            str(payload.get("sub_type") or "").lower(),
            str(payload.get("message_sub_type") or "").lower(),
            str(sender.get("role") or "").lower(),
            str(sender.get("user_type") or "").lower(),
        }
        if role_values & {"qq_bot", "official_bot", "bot", "guild"}:
            return True

        sender_title = str(sender.get("title") or sender.get("card") or sender.get("nickname") or "").lower()
        return "官方机器人" in sender_title or "qq bot" in sender_title

    async def _build_inbound_message_dict(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        """构造 Host 可接受的 MessageDict。"""

        sender = payload.get("sender", {})
        if not isinstance(sender, Mapping):
            sender = {}

        user_id = str(payload.get("user_id") or sender.get("user_id") or "").strip()
        if not user_id:
            raise ValueError("缺少 user_id")

        message_type = str(payload.get("message_type") or "").strip() or "private"
        group_id = str(payload.get("group_id") or "").strip()
        user_nickname = str(sender.get("nickname") or sender.get("card") or user_id).strip() or user_id
        user_cardname = str(sender.get("card") or "").strip() or None

        raw_message, plain_text, is_at, is_picture = await self._convert_inbound_segments(payload.get("message"))
        if not raw_message:
            raw_message = [{"type": "text", "data": "[unsupported]"}]
            plain_text = "[unsupported]"

        timestamp_seconds = payload.get("time")
        if not isinstance(timestamp_seconds, (int, float)):
            timestamp_seconds = time.time()

        additional_config: Dict[str, Any] = {
            "self_id": self._connected_account_id,
            "snowluma_message_type": message_type,
        }
        if group_id:
            additional_config["platform_io_target_group_id"] = group_id
        else:
            additional_config["platform_io_target_user_id"] = user_id

        message_info: Dict[str, Any] = {
            "user_info": {
                "user_id": user_id,
                "user_nickname": user_nickname,
                "user_cardname": user_cardname,
            },
            "additional_config": additional_config,
        }
        if group_id:
            group_name = await self._resolve_group_name(payload, group_id)
            message_info["group_info"] = {"group_id": group_id, "group_name": group_name}

        message_id = str(payload.get("message_id") or f"snowluma-{uuid4().hex}").strip()
        return {
            "message_id": message_id,
            "timestamp": str(float(timestamp_seconds)),
            "platform": "qq",
            "message_info": message_info,
            "raw_message": raw_message,
            "is_mentioned": is_at,
            "is_at": is_at,
            "is_emoji": False,
            "is_picture": is_picture,
            "is_command": plain_text.startswith("/"),
            "is_notify": False,
            "session_id": "",
            "processed_plain_text": plain_text,
        }

    async def _resolve_group_name(self, payload: Mapping[str, Any], group_id: str) -> str:
        """解析群名称，优先使用推送字段，缺失时查询 SnowLuma。"""

        raw_group_name = str(payload.get("group_name") or "").strip()
        if raw_group_name:
            self._group_name_cache[group_id] = raw_group_name
            return raw_group_name

        cached_group_name = self._group_name_cache.get(group_id, "")
        if cached_group_name:
            return cached_group_name

        for action_name in ("get_group_info", "get_group_info_ex"):
            try:
                response = await self._call_action(action_name, {"group_id": group_id})
            except Exception as exc:
                self.ctx.logger.debug(f"SnowLuma 查询群名称失败: action={action_name} group_id={group_id} error={exc}")
                continue

            group_info = response.get("data", response)
            if not isinstance(group_info, Mapping):
                continue

            resolved_group_name = str(
                group_info.get("group_name")
                or group_info.get("group_remark")
                or group_info.get("name")
                or ""
            ).strip()
            if resolved_group_name:
                self._group_name_cache[group_id] = resolved_group_name
                return resolved_group_name

        return f"group_{group_id}"

    async def _convert_inbound_segments(self, raw_message: Any) -> Tuple[List[Dict[str, Any]], str, bool, bool]:
        """转换 OneBot 消息段为 Host 消息段。"""

        if isinstance(raw_message, str):
            return ([{"type": "text", "data": raw_message}], raw_message, False, False)

        if not isinstance(raw_message, list):
            return ([], "", False, False)

        segments: List[Dict[str, Any]] = []
        plain_text_parts: List[str] = []
        is_at = False
        is_picture = False
        for item in raw_message:
            if not isinstance(item, Mapping):
                continue

            item_type = str(item.get("type") or "").strip()
            item_data = item.get("data", {})
            if not isinstance(item_data, Mapping):
                item_data = {}

            if item_type == "text":
                text = str(item_data.get("text") or "")
                if text:
                    segments.append({"type": "text", "data": text})
                    plain_text_parts.append(text)
                continue

            if item_type == "at":
                target_user_id = str(item_data.get("qq") or "").strip()
                if target_user_id:
                    segments.append(
                        {
                            "type": "at",
                            "data": {
                                "target_user_id": target_user_id,
                                "target_user_nickname": None,
                                "target_user_cardname": None,
                            },
                        }
                    )
                    plain_text_parts.append(f"@{target_user_id}")
                    if self._connected_account_id and target_user_id == self._connected_account_id:
                        is_at = True
                continue

            if item_type == "reply":
                target_message_id = str(item_data.get("id") or "").strip()
                if target_message_id:
                    segments.append({"type": "reply", "data": {"target_message_id": target_message_id}})
                continue

            if item_type == "image":
                image_ref = str(item_data.get("url") or item_data.get("file") or "").strip()
                is_emoji_segment = self._is_emoji_image_segment(item_data)
                image_segment = await self._build_inbound_binary_segment(
                    "emoji" if is_emoji_segment else "image",
                    image_ref,
                    "[emoji]" if is_emoji_segment else "[image]",
                )
                segments.append(image_segment)
                plain_text_parts.append("[image]")
                is_picture = True
                continue

            if item_type == "record":
                voice_ref = str(item_data.get("url") or item_data.get("file") or "").strip()
                voice_segment = await self._build_inbound_binary_segment("voice", voice_ref, "[voice]")
                segments.append(voice_segment)
                plain_text_parts.append("[voice]")
                continue

            if item_type in {"face", "emoji"}:
                face_id = str(item_data.get("id") or "").strip()
                text = f"[face:{face_id}]" if face_id else "[face]"
                segments.append({"type": "text", "data": text})
                plain_text_parts.append(text)
                continue

            fallback_text = f"[{item_type or 'unknown'}]"
            segments.append({"type": "text", "data": fallback_text})
            plain_text_parts.append(fallback_text)

        return segments, "".join(plain_text_parts), is_at, is_picture

    async def _build_inbound_binary_segment(
        self,
        segment_type: str,
        file_reference: str,
        fallback_text: str,
    ) -> Dict[str, Any]:
        """构造 Host 可识别的入站媒体段。"""

        binary_data = await self._load_binary_reference(file_reference)
        if not binary_data:
            self.ctx.logger.debug(f"SnowLuma 媒体下载失败，降级为文本: type={segment_type} ref={file_reference[:120]}")
            return {"type": "text", "data": fallback_text}

        return {
            "type": segment_type,
            "data": "",
            "hash": self._hash_binary(binary_data),
            "binary_data_base64": self._encode_binary(binary_data),
        }

    async def _load_binary_reference(self, file_reference: str) -> bytes:
        """加载 OneBot 媒体引用中的二进制内容。"""

        normalized_reference = str(file_reference or "").strip()
        if not normalized_reference:
            return b""

        if normalized_reference.startswith("base64://"):
            try:
                return base64.b64decode(normalized_reference.removeprefix("base64://"))
            except Exception:
                return b""

        if normalized_reference.startswith(("http://", "https://")):
            session = self._session
            if session is None:
                return b""
            try:
                async with session.get(normalized_reference) as response:
                    if response.status >= 400:
                        return b""
                    return await response.read()
            except Exception as exc:
                self.ctx.logger.debug(f"SnowLuma 下载媒体失败: {exc}")
                return b""

        return b""

    @staticmethod
    def _is_emoji_image_segment(segment_data: Mapping[str, Any]) -> bool:
        """判断 OneBot image 段是否更像表情包。"""

        raw_sub_type = str(segment_data.get("sub_type") or segment_data.get("subType") or "").strip()
        if raw_sub_type and raw_sub_type not in {"0", "4", "9", "normal"}:
            return True

        summary = str(segment_data.get("summary") or "").strip()
        if "表情" in summary or "emoji" in summary.lower():
            return True

        return False

    def _build_outbound_action(
        self,
        message: Mapping[str, Any],
        route: Mapping[str, Any],
    ) -> Tuple[str, Dict[str, Any]]:
        """将 Host 出站消息转换为 SnowLuma 动作。"""

        message_info = message.get("message_info", {})
        if not isinstance(message_info, Mapping):
            message_info = {}

        group_info = message_info.get("group_info", {})
        if not isinstance(group_info, Mapping):
            group_info = {}

        additional_config = message_info.get("additional_config", {})
        if not isinstance(additional_config, Mapping):
            additional_config = {}

        segments = self._convert_outbound_segments(message.get("raw_message", []))
        target_group_id = str(
            group_info.get("group_id")
            or additional_config.get("platform_io_target_group_id")
            or route.get("group_id")
            or route.get("target_group_id")
            or ""
        ).strip()
        if target_group_id:
            return "send_msg", {"message_type": "group", "group_id": target_group_id, "message": segments}

        target_user_id = str(
            additional_config.get("platform_io_target_user_id")
            or additional_config.get("target_user_id")
            or route.get("user_id")
            or route.get("target_user_id")
            or ""
        ).strip()
        if not target_user_id:
            raise ValueError("出站私聊消息缺少 target_user_id")

        return "send_msg", {"message_type": "private", "user_id": target_user_id, "message": segments}

    def _convert_outbound_segments(self, raw_message: Any) -> List[Dict[str, Any]]:
        """将 Host 消息段转换为 OneBot 消息段。"""

        if not isinstance(raw_message, list):
            return [{"type": "text", "data": {"text": ""}}]

        segments: List[Dict[str, Any]] = []
        for item in raw_message:
            if not isinstance(item, Mapping):
                continue

            item_type = str(item.get("type") or "").strip()
            item_data = item.get("data")
            if item_type == "text":
                segments.append({"type": "text", "data": {"text": str(item_data or "")}})
                continue

            if item_type == "at" and isinstance(item_data, Mapping):
                target_user_id = str(item_data.get("target_user_id") or "").strip()
                if target_user_id:
                    segments.append({"type": "at", "data": {"qq": target_user_id}})
                continue

            if item_type == "reply":
                target_message_id = ""
                if isinstance(item_data, Mapping):
                    target_message_id = str(item_data.get("target_message_id") or "").strip()
                else:
                    target_message_id = str(item_data or "").strip()
                normalized_reply_id = self._normalize_outbound_reply_id(target_message_id)
                if normalized_reply_id is not None:
                    segments.append({"type": "reply", "data": {"id": normalized_reply_id}})
                elif target_message_id:
                    self.ctx.logger.debug(f"SnowLuma 跳过无效回复目标消息 ID: {target_message_id}")
                continue

            if item_type in {"image", "emoji"}:
                image_segment = self._build_media_segment("image", item)
                if image_segment:
                    segments.append(image_segment)
                continue

            if item_type == "voice":
                voice_segment = self._build_media_segment("record", item)
                if voice_segment:
                    segments.append(voice_segment)
                continue

            segments.append({"type": "text", "data": {"text": f"[unsupported:{item_type or 'unknown'}]"}})

        if not segments:
            segments.append({"type": "text", "data": {"text": ""}})
        return segments

    @staticmethod
    def _build_media_segment(segment_type: str, item: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        """构造 OneBot 媒体消息段。"""

        binary_base64 = str(item.get("binary_data_base64") or "").strip()
        if binary_base64:
            return {"type": segment_type, "data": {"file": f"base64://{binary_base64}"}}

        item_data = item.get("data")
        file_reference = ""
        if isinstance(item_data, Mapping):
            file_reference = str(item_data.get("file") or item_data.get("url") or "").strip()
        else:
            file_reference = str(item_data or "").strip()

        if not file_reference:
            return None

        if not file_reference.startswith(("base64://", "file://", "http://", "https://")):
            file_reference = f"file://{file_reference}"
        return {"type": segment_type, "data": {"file": file_reference}}

    @staticmethod
    def _normalize_outbound_reply_id(message_id: str) -> Optional[int]:
        """把内部回复目标 ID 转成 SnowLuma 可接受的 OneBot 消息 ID。"""

        normalized_message_id = str(message_id or "").strip()
        if not normalized_message_id or normalized_message_id.startswith("snowluma-"):
            return None

        try:
            reply_id = int(normalized_message_id)
        except ValueError:
            return None

        if reply_id == 0:
            return None
        return reply_id

    @staticmethod
    def _encode_binary(binary_data: bytes) -> str:
        """保留给后续二进制媒体扩展使用。"""

        return base64.b64encode(binary_data).decode("utf-8")

    @staticmethod
    def _hash_binary(binary_data: bytes) -> str:
        """保留给后续二进制媒体扩展使用。"""

        return hashlib.sha256(binary_data).hexdigest()


def create_plugin() -> SnowLumaAdapterPlugin:
    """创建 SnowLuma 适配器插件实例。"""

    return SnowLumaAdapterPlugin()
