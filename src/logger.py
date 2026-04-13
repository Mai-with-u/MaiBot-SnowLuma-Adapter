from abc import ABC, abstractmethod
from loguru import logger as loguru_logger
from datetime import datetime


class BaseLogger(ABC):
    """仅用于typing检查"""

    @abstractmethod
    def info(self, message: str): ...
    @abstractmethod
    def warning(self, message: str): ...
    @abstractmethod
    def error(self, message: str): ...
    @abstractmethod
    def debug(self, message: str): ...
    @abstractmethod
    def critical(self, message: str): ...


date_str = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
loguru_logger.add(f"logs/luma_ada_{date_str}.log", rotation="1 day", retention="7 days", compression="zip")
logger: BaseLogger = loguru_logger  # type: ignore


def set_logger(new_logger):
    """设置日志记录器"""
    global logger
    logger = new_logger
