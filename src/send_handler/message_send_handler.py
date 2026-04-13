import asyncio
import json
import uuid
from typing import Any, Dict, Optional, Tuple

from ..connection.luma_client import WebSocketConnection
from ..logger import logger


class LumaSendHandler:
    def __init__(self, connection: WebSocketConnection) -> None:
        self._connection = connection
        self._response_pool: Dict[str, asyncio.Future[Dict[str, Any]]] = {}

    async def send_payload(self, payload_type: str, payload_data: dict) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """发送消息负载"""
        uuid_str = str(uuid.uuid4())
        payload = {
            "action": payload_type,
            "params": payload_data,
            "echo": uuid_str,
        }
        future = asyncio.get_running_loop().create_future()
        self._response_pool[uuid_str] = future
        payload_str = json.dumps(payload)
        success = await self._connection.send(payload_str)
        if not success:
            future.cancel()
            self._response_pool.pop(uuid_str, None)
            return False, None
        try:
            response = await asyncio.wait_for(future, timeout=10)
            return True, response
        except asyncio.TimeoutError:
            future.cancel()
        except Exception as e:
            logger.error(f"等待响应出现错误: {e}")
            future.cancel()
        finally:
            self._response_pool.pop(uuid_str, None)
        return False, None
