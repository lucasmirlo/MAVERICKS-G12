import logging
import re

_SECRET = re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+|((?:api[_-]?key|password|secret|token)\s*[=:]\s*)\S+", re.I)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        redacted = _SECRET.sub(lambda m: (m.group(1) or m.group(2)) + "[REDACTED]", msg)
        if redacted != msg:
            record.msg, record.args = redacted, ()
        return True


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    logging.getLogger("httpx").setLevel(logging.WARNING)
