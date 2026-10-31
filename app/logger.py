import json
import logging
import sys
import time

log = logging.getLogger("release_notes")

# ANSI colour codes
LEVEL_COLORS = {"DEBUG": "38;5;208", "INFO": "38;5;39", "WARNING": "35", "ERROR": "31", "CRITICAL": "1;31"}
FIELD_COLORS = {"time": "90", "msg": "1"}


def paint(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"


class JsonFormatter(logging.Formatter):
    
    def __init__(self, color: bool) -> None:
        super().__init__()
        self.color = color

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "time": time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
        }
        if message := record.getMessage():
            entry["msg"] = message
        entry.update(getattr(record, "fields", {}))
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        if not self.color:
            return json.dumps(entry)
        colors = {**FIELD_COLORS, "level": LEVEL_COLORS.get(record.levelname, "0")}
        pairs = (f"{paint(json.dumps(key), '36')}: {paint(json.dumps(value), colors.get(key, '32'))}"
                 for key, value in entry.items())
        return "{" + ", ".join(pairs) + "}"


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    # A pod's stdout is not a terminal, so the cluster keeps plain JSON and only a local run is coloured.
    handler.setFormatter(JsonFormatter(sys.stdout.isatty()))
    log.handlers = [handler]
    log.setLevel(level)
    log.propagate = False
