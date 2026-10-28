import json
import logging
import sys
from datetime import UTC, datetime

log = logging.getLogger("release_notes")


class JsonFormatter(logging.Formatter):
    """One JSON object per line, so a log collector can parse fields without regex."""

    def format(self, record):
        entry = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        entry.update(getattr(record, "fields", {}))
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    log.handlers = [handler]
    log.setLevel(level)
    log.propagate = False
