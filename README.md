# MaiBot SnowLuma Adapter
本项目是对接 SnowLuma 的 MaiBot 适配器插件，仅支持作为 Adapter 插件被 MaiBot 加载。

## 0.7.1更新

- 支持通知信息获取

## 0.7.0更新

- 支持发送转发消息
- 支持撤回消息
- 兼容napcat的一些接口

## 主动私聊工具

在 `[plugin]` 中将 `enable_private_chat_tool` 设置为 `true` 后，模型可以调用 `open_private_chat` 打开指定 QQ 用户的私聊聊天流并发送首条私聊消息。发送成功后，该用户 15 分钟内的私聊入站消息会绕过私聊名单黑白名单过滤，但仍会遵守全局屏蔽用户规则。

如果只知道某条消息的 `msg_id`，可以先调用 `get_qq_by_msg_id` 获取该消息发送者的 QQ 号，再传给 `open_private_chat`。
