# Changelog

## [0.8.2]

- 支持视频与文件上传发送

## [0.8.1]

- 修复发送的表情包变为图片的问题
- 新增显示发送消息的详细信息调试选项

## [0.8.0]

### 用户感知功能

- 补充群资料与群成员相关 NapCat 兼容 API：`adapter.napcat.group.get_group_list`、`adapter.napcat.group.get_group_info`、`adapter.napcat.group.get_group_member_list`。
- 补充群管理相关 NapCat 兼容 API：`adapter.napcat.group.set_group_kick`、`adapter.napcat.group.set_group_card`、`adapter.napcat.group.set_group_name`。
- 补充好友与陌生人信息相关 NapCat 兼容 API：`adapter.napcat.account.get_friend_list`、`adapter.napcat.account.get_stranger_info`。
- 补充消息与互动相关 NapCat 兼容 API：`adapter.napcat.message.send_msg`、`adapter.napcat.message.get_forward_msg`、`adapter.napcat.message.send_poke`。
- 补充文件与语音相关 NapCat 兼容 API：`adapter.napcat.file.get_record`、`adapter.napcat.file.get_group_file_url`、`adapter.napcat.file.upload_group_file`。
- 补充图片 OCR 与点赞相关 NapCat 兼容 API：`adapter.napcat.account.ocr_image`、`adapter.napcat.account.send_like`、`adapter.napcat.account.get_profile_like`。
- 补充个人资料、头像和状态相关 NapCat 兼容 API：`adapter.napcat.account.set_qq_profile`、`adapter.napcat.account.set_qq_avatar`、`adapter.napcat.account.set_self_longnick`、`adapter.napcat.account.set_diy_online_status`、`adapter.napcat.system.set_input_status`、`adapter.napcat.system.set_online_status`。
- 新增 SnowLuma Qzone 能力的 NapCat 风格兼容入口：`adapter.napcat.qzone.get_qzone_msg_list`、`adapter.napcat.qzone.get_qzone_feeds`、`adapter.napcat.qzone.send_qzone_msg`、`adapter.napcat.qzone.delete_qzone_msg`、`adapter.napcat.qzone.like_qzone`、`adapter.napcat.qzone.unlike_qzone`、`adapter.napcat.qzone.comment_qzone`。


## [0.7.2]

### 用户感知功能

- 修复表情包出站消息被 SnowLuma 按普通图片发送的问题，现在会按 OneBot 表情包 subtype 发送。

## [0.7.1]

### 用户感知功能

- 支持通知信息获取。

## [0.7.0]

### 用户感知功能

- 支持发送转发消息。
- 支持撤回消息。
- 兼容 NapCat 的一些接口。
