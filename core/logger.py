import logging
import sys
from pathlib import Path

LOG_DIR = Path.home() / ".kaal" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

def setup_logger(name: str, level=logging.DEBUG, console_level=logging.INFO) -> logging.Logger:
    """Configure a logger with file and console handlers."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # File handler – always DEBUG
    fh = logging.FileHandler(LOG_DIR / f"{name}.log")
    fh.setLevel(logging.DEBUG)

    # Console handler – configurable level
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(console_level)

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger
