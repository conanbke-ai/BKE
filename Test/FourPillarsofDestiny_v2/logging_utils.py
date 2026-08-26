from __future__ import annotations

import copy
import logging
from datetime import datetime

from config import SETTINGS


class MaxLevelFilter(logging.Filter):
    def __init__(self, max_level: int) -> None:
        super().__init__()
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.max_level


class ConsoleFormatter(logging.Formatter):
    """터미널에는 간결한 한 줄만 출력하고 traceback은 파일에만 남긴다."""

    def format(self, record: logging.LogRecord) -> str:
        console_record = copy.copy(record)
        console_record.exc_info = None
        console_record.exc_text = None
        console_record.stack_info = None
        return super().format(console_record)


def setup_logging() -> logging.Logger:
    SETTINGS.log_dir.mkdir(parents=True, exist_ok=True)
    day = datetime.now().strftime("%Y-%m-%d")
    info_file = SETTINGS.log_dir / f"{day}.log"
    error_file = SETTINGS.log_dir / f"{day}.error.log"

    logger = logging.getLogger("four_pillars")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    detailed = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(module)s:%(lineno)d | %(message)s"
    )

    info_handler = logging.FileHandler(info_file, encoding="utf-8")
    info_handler.setLevel(logging.DEBUG)
    info_handler.addFilter(MaxLevelFilter(logging.WARNING))
    info_handler.setFormatter(detailed)
    logger.addHandler(info_handler)

    error_handler = logging.FileHandler(error_file, encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed)
    logger.addHandler(error_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ConsoleFormatter("%(levelname)s | %(message)s"))
    logger.addHandler(console_handler)
    return logger


LOGGER = setup_logging()
