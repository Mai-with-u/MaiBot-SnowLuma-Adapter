import asyncio
import json
import base64
from pathlib import Path

from src.config import Config
from src.connection.luma_client import WebSocketConnection
from src.send_handler.message_send_handler import LumaSendHandler

# from src.api_handler.api import LumaAPI
from src.logger import logger

running_flag = asyncio.Event()


async def dispatch_content(message: str | bytes):
    """分发消息内容到不同的处理器"""
    if isinstance(message, bytes):
        logger.critical("收到二进制消息，当前版本仅支持文本消息")
        return
    raw_dict = json.loads(message)
    logger.info(f"分发消息内容: {raw_dict}")


async def main(config: Config):
    client = WebSocketConnection(
        running_flag=running_flag,
        token=config.luma_client.token,
        server=config.luma_client.server,
        port=config.luma_client.port,
    )
    # send_handler = LumaSendHandler(client)
    await client.connect()
    client.set_handler(dispatch_content)
    await asyncio.sleep(1)  # 等待连接稳定

    try:
        # await test_send_text(send_handler)
        # await test_send_image(send_handler)
        await client.listen()
    except Exception as e:
        logger.error(f"连接或监听出现错误: {e}")
    await client.disconnect()


async def cleanup():
    logger.info("正在执行清理操作...")
    running_flag.set()
    pending_tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
    for task in pending_tasks:
        task.cancel()
    try:
        await asyncio.wait_for(asyncio.gather(*pending_tasks, return_exceptions=True), timeout=10)
    except asyncio.TimeoutError:
        logger.warning("清理任务超时，强制退出")
        return
    logger.info("清理完成，程序即将退出")


async def test_send_text(send_handler: LumaSendHandler):
    await send_handler.send_payload(
        "send_msg",
        {
            "message_type": "group",
            "group_id": "1081372778",
            "message": [
                {"type": "text", "data": {"text": "这是一个测试消息"}},
            ],
        },
    )


async def test_send_image(send_handler: LumaSendHandler):
    # 读取图片并转换为base64
    image_path = Path(__file__).parent / "test" / "111.jpeg"
    with open(image_path, "rb") as f:
        image_data = f.read()
    base64_content = base64.b64encode(image_data).decode("utf-8")
    await send_handler.send_payload(
        "send_msg",
        {
            "message_type": "group",
            "group_id": "1036092828",
            "message": [
                {
                    "type": "image",
                    "data": {
                        "summary": "我喜欢你，和我结婚吧！",
                        "file": f"base64://{base64_content}",
                    },
                }
            ],
        },
    )


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    from src.config import load_config_from_file

    config = load_config_from_file(Path(__file__).parent / "config.toml")
    try:
        loop.run_until_complete(main(config))
    except OSError as e:
        logger.error(f"网络错误: {e}")
    except KeyboardInterrupt:
        logger.info("程序已被用户中断")
    finally:
        loop.run_until_complete(cleanup())
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
