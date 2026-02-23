import logging
import sys
from pathlib import Path

LOG_DIR = Path.home() / ".kaal" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

def setup_logger(name: str, level=logging.DEBUG, console_level=logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if logger.handlers:
        return logger
    
    # File Handler
    fh = logging.FileHandler(LOG_DIR / f"{name}.log")
    fh.setLevel(logging.DEBUG)
    
    # Console Handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(console_level)
    
    # Formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    return logger
