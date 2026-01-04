import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

def setup_logging(
    log_dir: str = "logs",
    log_file: str = "monitor.log",
    level: int = logging.INFO,
):
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    # ---- file handler (rotating) ----
    file_handler = RotatingFileHandler(
        filename=Path(log_dir) / log_file,
        maxBytes=5 * 1024 * 1024,   # 5 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    # ---- console handler ----
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    # Avoid duplicate handlers if main() is reloaded
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
