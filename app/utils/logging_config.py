from loguru import logger
import sys

def setup_logging(debug: bool = False):
    logger.remove()
    level = "DEBUG" if debug else "INFO"
    logger.add(sys.stderr, level=level, format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}")
    logger.add("logs/healthlens_{time:YYYY-MM-DD}.log", rotation="00:00", retention="30 days", level=level, encoding="utf-8")