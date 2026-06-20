from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Literal, Optional
from urllib.parse import urlencode

from maibot_sdk import Field, PluginConfigBase
from pydantic import field_validator

SNOWLUMA_GATEWAY_NAME = "snowluma_gateway"
SUPPORTED_CONFIG_VERSION = "1.0.3"
DEFAULT_CHAT_LIST_TYPE = "whitelist"
PRIVATE_CHAT_TOOL_BYPASS_SECONDS = 15 * 60
VOICE_TRANSCODE_SAMPLE_RATE = 24000
VOICE_TRANSCODE_TIMEOUT_SECONDS = 15.0


def _schema_i18n(
    *,
    label_en: str,
    label_ja: str,
    hint_en: Optional[str] = None,
    hint_ja: Optional[str] = None,
    placeholder_en: Optional[str] = None,
    placeholder_ja: Optional[str] = None,
) -> Dict[str, Dict[str, str]]:
    """构造 WebUI 配置项多语言说明，保留外层中文字段兼容旧格式。"""

    i18n: Dict[str, Dict[str, str]] = {
        "en_US": {"label": label_en},
        "ja_JP": {"label": label_ja},
    }
    if hint_en is not None:
        i18n["en_US"]["hint"] = hint_en
    if hint_ja is not None:
        i18n["ja_JP"]["hint"] = hint_ja
    if placeholder_en is not None:
        i18n["en_US"]["placeholder"] = placeholder_en
    if placeholder_ja is not None:
        i18n["ja_JP"]["placeholder"] = placeholder_ja
    return i18n


class SnowLumaPluginSection(PluginConfigBase):
    """插件开关配置。"""

    __ui_label__: ClassVar[str] = "插件设置"
    __ui_order__: ClassVar[int] = 0

    enabled: bool = Field(
        default=False,
        description="是否启用 SnowLuma 适配器。",
        json_schema_extra={
            "label": "启用适配器",
            "i18n": _schema_i18n(
                label_en="Enable adapter",
                label_ja="アダプターを有効化",
                hint_en="When disabled, the plugin only registers the message gateway and will not connect to SnowLuma.",
                hint_ja="無効にすると、プラグインはメッセージゲートウェイの登録のみを行い、SnowLuma へ接続しません。",
            ),
            "order": 0,
        },
    )
    enable_ada_debug_raw_message_log: bool = Field(
        default=False,
        description="是否启用 Ada 调试模式，记录 SnowLuma 入站原始消息段。",
        json_schema_extra={
            "label": "显示原始消息段",
            "hint": "仅排查消息段结构问题时开启；开启后会记录每条入站消息的原始 message 字段。",
            "i18n": _schema_i18n(
                label_en="Ada raw message debug",
                label_ja="Ada 生メッセージデバッグ",
                hint_en="Enable only while debugging segment structure; logs each inbound raw message field at info level.",
                hint_ja="セグメント構造を調査するときだけ有効にしてください。入站 message フィールドを info レベルで記録します。",
            ),
            "order": 1,
        },
    )
    enable_private_chat_tool: bool = Field(
        default=False,
        description="是否启用主动开启私聊工具。",
        json_schema_extra={
            "label": "启用主动私聊工具",
            "hint": "开启后，模型可调用工具向指定 好友 发送首条私聊消息，并在 15 分钟内绕过私聊名单过滤。",
            "i18n": _schema_i18n(
                label_en="Enable private chat tool",
                label_ja="個人チャット開始ツールを有効化",
                hint_en=(
                    "When enabled, the model can use a tool to send the first private message to a user "
                    "and bypass private chat-list filtering for 15 minutes."
                ),
                hint_ja=(
                    "有効にすると、モデルは指定ユーザーへ最初の個人メッセージを送信し、"
                    "15 分間だけ個人チャットリストのフィルターを回避できます。"
                ),
            ),
            "order": 2,
        },
    )
    qq_face_parse_mode: Literal["description", "emoji"] = Field(
        default="description",
        description="QQ 自带表情解析模式：转为中文描述或近似 Unicode emoji。",
        json_schema_extra={
            "label": "QQ表情解析模式",
            "hint": "[description]模式会把表情转成[流泪]这种形式[emoji]会转成近似emoji表情。",
            "i18n": _schema_i18n(
                label_en="QQ face parsing",
                label_ja="QQ 標準顔文字の解析",
                hint_en=(
                    "description converts [CQ:face,id=5] to [流泪]; "
                    "emoji prefers an approximate Unicode emoji."
                ),
                hint_ja=(
                    "description は [CQ:face,id=5] を [流泪] に変換します。"
                    "emoji は近い Unicode 絵文字を優先します。"
                ),
            ),
            "order": 3,
        },
    )
    config_version: str = Field(
        default=SUPPORTED_CONFIG_VERSION,
        description="当前配置结构版本。",
        json_schema_extra={
            "disabled": True,
            "hidden": True,
            "i18n": _schema_i18n(label_en="Config version", label_ja="設定バージョン"),
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
        json_schema_extra={
            "i18n": _schema_i18n(
                label_en="Server address",
                label_ja="サーバーアドレス",
                hint_en="Usually the host running SnowLuma. Defaults to the local loopback address.",
                hint_ja="通常は SnowLuma を実行しているホストです。既定ではローカルのループバックアドレスを使用します。",
                placeholder_en="127.0.0.1",
                placeholder_ja="127.0.0.1",
            ),
            "label": "服务地址",
            "order": 0,
            "placeholder": "127.0.0.1",
        },
    )
    port: int = Field(
        default=3001,
        description="SnowLuma WebSocket 服务端口。",
        json_schema_extra={
            "i18n": _schema_i18n(
                label_en="Port",
                label_ja="ポート",
                hint_en="Keep this consistent with the SnowLuma WebSocket listening port.",
                hint_ja="SnowLuma WebSocket の待受ポートと一致させてください。",
            ),
            "label": "端口",
            "order": 1,
        },
    )
    token: str = Field(
        default="",
        description="SnowLuma 访问令牌。",
        json_schema_extra={
            "label": "访问令牌",
            "i18n": _schema_i18n(
                label_en="Access token",
                label_ja="アクセストークン",
                hint_en="If SnowLuma access token verification is enabled, enter the same token here.",
                hint_ja="SnowLuma でアクセストークン検証を有効にしている場合は、同じ token をここに入力してください。",
                placeholder_en="Optional",
                placeholder_ja="空欄可",
            ),
            "input_type": "password",
            "order": 2,
            "placeholder": "可留空",
        },
    )
    connection_id: str = Field(
        default="",
        description="可选连接标识，用于区分多条适配器链路。",
        json_schema_extra={
            "i18n": _schema_i18n(
                label_en="Connection ID",
                label_ja="接続識別子",
                hint_en="When multiple SnowLuma connections exist, use this as the routing scope identifier.",
                hint_ja="複数の SnowLuma 接続がある場合、ルーティングスコープの識別子として使用できます。",
            ),
            "label": "连接标识",
            "order": 3,
        },
    )
    reconnect_delay_sec: float = Field(
        default=5.0,
        description="连接断开后的重连等待时间，单位为秒。",
        json_schema_extra={
            "i18n": _schema_i18n(
                label_en="Reconnect delay (sec)",
                label_ja="再接続待機（秒）",
                hint_en="After a disconnect, wait this long before trying to reconnect.",
                hint_ja="接続が切断された後、再接続を試すまでこの時間待機します。",
            ),
            "label": "重连等待",
            "order": 4,
            "step": 1,
        },
    )
    action_timeout_sec: float = Field(
        default=10.0,
        description="调用 SnowLuma 动作接口的超时时间，单位为秒。",
        json_schema_extra={
            "i18n": _schema_i18n(
                label_en="Action timeout (sec)",
                label_ja="アクションタイムアウト（秒）",
                hint_en="Actions such as sending messages or querying info fail after this timeout.",
                hint_ja="メッセージ送信や情報取得などのアクションは、この時間を超えるとエラーになります。",
            ),
            "label": "动作超时",
            "order": 5,
            "step": 1,
        },
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
            "i18n": _schema_i18n(
                label_en="Enable chat list filter",
                label_ja="チャットリストフィルターを有効化",
                hint_en="When disabled, group_list and private_list are ignored; only ban_user_id rules remain.",
                hint_ja="無効にすると、group_list と private_list を無視し、ban_user_id ルールのみを適用します。",
            ),
            "label": "启用聊天名单过滤",
            "order": 0,
        },
    )
    show_dropped_chat_list_messages: bool = Field(
        default=False,
        description="是否展示未通过聊天名单过滤而被丢弃的消息。",
        json_schema_extra={
            "hint": "关闭后不记录群聊/私聊名单丢弃日志，默认关闭以减少刷屏。",
            "i18n": _schema_i18n(
                label_en="Show dropped chat-list logs",
                label_ja="チャットリストで破棄されたログを表示",
                hint_en="When disabled, dropped group/private chat-list logs are not recorded. Default off to reduce log noise.",
                hint_ja="無効にすると、チャットリストで破棄されたグループ/個人チャットのログを記録しません。ログの増加を抑えるため既定ではオフです。",
            ),
            "label": "显示聊天名单丢弃日志",
            "order": 1,
        },
    )
    group_list_type: Literal["whitelist", "blacklist"] = Field(
        default=DEFAULT_CHAT_LIST_TYPE,
        description="群聊名单模式。",
        json_schema_extra={
            "hint": "白名单模式只接收列表内群聊，黑名单模式则忽略列表内群聊。",
            "i18n": _schema_i18n(
                label_en="Group list mode",
                label_ja="グループリストモード",
                hint_en="Whitelist mode only accepts listed groups; blacklist mode ignores listed groups.",
                hint_ja="ホワイトリストではリスト内のグループのみ受信し、ブラックリストではリスト内のグループを無視します。",
            ),
            "label": "群聊名单模式",
            "order": 2,
        },
    )
    group_list: List[str] = Field(
        default_factory=list,
        description="群聊名单中的群号列表。",
        json_schema_extra={
            "hint": "群号会被统一转换为字符串并自动去重。",
            "i18n": _schema_i18n(
                label_en="Group list",
                label_ja="グループリスト",
                hint_en="Group IDs are normalized to strings and deduplicated automatically.",
                hint_ja="グループ ID は文字列に正規化され、自動的に重複排除されます。",
                placeholder_en="Enter group ID",
                placeholder_ja="グループ ID を入力",
            ),
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
            "i18n": _schema_i18n(
                label_en="Private list mode",
                label_ja="個人チャットリストモード",
                hint_en="Whitelist mode only accepts listed private chats; blacklist mode ignores listed private chats.",
                hint_ja="ホワイトリストではリスト内の個人チャットのみ受信し、ブラックリストではリスト内の個人チャットを無視します。",
            ),
            "label": "私聊名单模式",
            "order": 4,
        },
    )
    private_list: List[str] = Field(
        default_factory=list,
        description="私聊名单中的用户 ID 列表。",
        json_schema_extra={
            "hint": "用户 ID 会被统一转换为字符串并自动去重。",
            "i18n": _schema_i18n(
                label_en="Private list",
                label_ja="個人チャットリスト",
                hint_en="User IDs are normalized to strings and deduplicated automatically.",
                hint_ja="ユーザー ID は文字列に正規化され、自動的に重複排除されます。",
                placeholder_en="Enter user ID",
                placeholder_ja="ユーザー ID を入力",
            ),
            "label": "私聊名单",
            "order": 5,
            "placeholder": "请输入用户 ID",
        },
    )
    ban_user_id: List[str] = Field(
        default_factory=list,
        description="全局屏蔽的用户 ID 列表。",
        json_schema_extra={
            "hint": "这些用户的消息会被直接丢弃。",
            "i18n": _schema_i18n(
                label_en="Globally blocked users",
                label_ja="全体ブロックユーザー",
                hint_en="Messages from these users are dropped before entering the Host.",
                hint_ja="これらのユーザーからのメッセージは Host に入る前に破棄されます。",
                placeholder_en="Enter user ID",
                placeholder_ja="ユーザー ID を入力",
            ),
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
            "i18n": _schema_i18n(
                label_en="Block official bots",
                label_ja="公式 Bot をブロック",
                hint_en="When SnowLuma push events identify an official bot marker, matching messages are dropped.",
                hint_ja="SnowLuma のプッシュ内で公式 Bot のマーカーを識別できる場合、該当メッセージを破棄します。",
            ),
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
        description="是否忽略手动用bot账号发送的消息。",
        json_schema_extra={
            "hint": "如果人类使用bot账号手动发送消息，开启此项后，不处理这类消息",
            "i18n": _schema_i18n(
                label_en="Ignore self messages",
                label_ja="自身のメッセージを無視",
                hint_en="Recommended on to avoid the bot processing messages it just sent.",
                hint_ja="Bot が自分で送信した直後のメッセージを処理しないよう、有効のままにすることを推奨します。",
            ),
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

