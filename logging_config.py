"""
Shared logging setup for AutoLab. All output goes to stderr so Docker Compose
prefixes every line with the service name (autolab  |).
"""
import logging
import sys


def setup_logging(service_name: str, level: int = logging.INFO) -> logging.Logger:
    """Configure and return a logger that writes to stderr with a consistent format."""
    logger = logging.getLogger(service_name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    logger.propagate = False

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(fmt)
    logger.addHandler(handler)

    return logger
