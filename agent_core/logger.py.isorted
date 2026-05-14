"""Central logger. Writes to logs/actions.log and the console."""

import logging
import os
import sys


class Logger:
    _instance = None

    def __new__(cls, *args, **kwargs):
        # Singleton so every component shares one handler set
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, log_dir: str = "logs", log_file: str = "actions.log"):
        if self._initialized:
            return
        self._initialized = True

        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, log_file)

        self._logger = logging.getLogger("ai_assistant")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False

        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        fh = logging.FileHandler(path, encoding="utf-8")
        fh.setFormatter(fmt)
        fh.setLevel(logging.DEBUG)

        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        sh.setLevel(logging.INFO)

        # Avoid duplicate handlers on re-init
        if not self._logger.handlers:
            self._logger.addHandler(fh)
            self._logger.addHandler(sh)

    def log(self, msg: str, level: str = "info") -> None:
        getattr(self._logger, level.lower(), self._logger.info)(msg)

    def info(self, msg: str) -> None:
        self._logger.info(msg)

    def debug(self, msg: str) -> None:
        self._logger.debug(msg)

    def warning(self, msg: str) -> None:
        self._logger.warning(msg)

    def error(self, msg: str) -> None:
        self._logger.error(msg)


def get_logger() -> "Logger":
    return Logger()
