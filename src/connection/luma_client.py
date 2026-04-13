from typing import Optional, Coroutine, Callable, Any
from aiohttp import (
    ClientSession,
    ClientTimeout,
    WSMsgType,
    ClientWebSocketResponse,
)
import asyncio

from ..logger import logger


class WebSocketConnection:
    """WebSocket连接类，用于连接到WebSocket服务器"""

    def __init__(
        self,
        running_flag: asyncio.Event,
        token: str,
        server: str = "127.0.0.1",
        port: int = 3001,
    ):
        self.server: str = server
        self.port: int = port
        self.token: str = token
        self._session: Optional[ClientSession] = None
        self._ws: Optional[ClientWebSocketResponse] = None
        self._handler: Optional[Callable[[str | bytes], Coroutine[Any, Any, None]]] = None
        self._running_flag: asyncio.Event = running_flag

    @property
    def url(self) -> str:
        """获取完整的WebSocket URL（带access_token参数）"""
        return f"ws://{self.server}:{self.port}?access_token={self.token}"

    async def connect(self):
        """建立WebSocket连接"""
        if self._ws is not None:
            logger.info(f"连接已建立 {self.url}")
            return
        try:
            timeout = ClientTimeout(total=10)
            self._session = ClientSession(timeout=timeout)
            self._ws = await self._session.ws_connect(self.url)
            logger.info(f"成功连接到 {self.url}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"连接失败: {e}")
            raise

    async def disconnect(self):
        """断开WebSocket连接"""
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
            logger.info(f"已断开与 {self.url} 的连接")
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def send(self, message: str | bytes) -> bool:
        """发送消息"""
        if self._ws is None:
            logger.warning("无法发送消息: 未连接")
            return False
        try:
            if isinstance(message, str):
                await self._ws.send_str(message)
            else:
                await self._ws.send_bytes(message)
            logger.debug(f"发送消息: {message[:100]}...")  # 仅打印前100字符
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return False
        return True

    async def receive(self) -> Optional[str | bytes]:
        """接收消息"""
        if self._ws is None:
            logger.error("无法接收消息: 未连接")
            return None
        try:
            msg = await self._ws.receive()
            if msg.type == WSMsgType.TEXT:
                return msg.data
            elif msg.type == WSMsgType.BINARY:
                return msg.data
            elif msg.type == WSMsgType.CLOSED:
                logger.info("连接已关闭")
                self._running_flag.set()
                return None
            elif msg.type == WSMsgType.ERROR:
                logger.error(f"连接错误: {self._ws.exception()}")
                self._running_flag.set()
                return None
            return None
        except Exception as e:
            logger.error(f"接收消息失败: {e}")
            return None

    def set_handler(self, handler: Callable[[str | bytes], Coroutine[Any, Any, None]]):
        """设置消息处理器"""
        self._handler = handler

    async def listen(self):
        """监听消息并调用处理器"""
        if self._handler is None:
            logger.warning("未设置消息处理器，无法监听消息")
            return
        if self._ws is None:
            logger.warning("无法监听消息: 未连接")
            return
        try:
            async for msg in self._ws:
                if self._running_flag.is_set():
                    logger.info("停止监听消息")
                    break
                if msg.type == WSMsgType.TEXT:
                    asyncio.create_task(self._handler(msg.data))
                elif msg.type == WSMsgType.BINARY:
                    asyncio.create_task(self._handler(msg.data))
                elif msg.type == WSMsgType.CLOSED:
                    logger.info("连接已关闭")
                    self._running_flag.set()
                    break
                elif msg.type == WSMsgType.ERROR:
                    logger.error(f"连接错误: {self._ws.exception()}")
                    self._running_flag.set()
                    break
        except Exception as e:
            logger.error(f"接收消息出现错误: {e}")
