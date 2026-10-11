"""
logutil.py
----------
Tiny logging helper. Modules call `get_logger(__name__)`; the CLI calls
`setup_logging()` once. Console output stays as plain, readable lines
(INFO shows the message only; WARNING/ERROR get a prefix), and an optional
log file gets full timestamps. Used as a library, nothing is configured, so
importing the modules never touches your logging setup.
"""

from __future__ import annotations

import logging
import sys

ROOT_NAME = "mfshortlister"


def get_logger(name: str | None = None) -> logging.Logger:
    name = (name or "").replace("__main__", "main")
    return logging.getLogger(f"{ROOT_NAME}.{name}" if name else ROOT_NAME)


class _ConsoleFormatter(logging.Formatter):
    def format(self, record):
        msg = record.getMessage()
        if record.levelno >= logging.ERROR:
            return f"ERROR: {msg}"
        if record.levelno >= logging.WARNING:
            return f"WARNING: {msg}"
        return msg


def setup_logging(verbose: bool = False, quiet: bool = False, log_file: str | None = None) -> logging.Logger:
    """Configures the package logger. verbose -> DEBUG, quiet -> warnings only."""
    logger = logging.getLogger(ROOT_NAME)
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.DEBUG)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if verbose else (logging.WARNING if quiet else logging.INFO))
    console.setFormatter(_ConsoleFormatter())
    logger.addHandler(console)

    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(fh)
    return logger
