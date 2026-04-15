import json
import logging

from django.utils.log import ServerFormatter


RESERVED_RECORD_ATTRS = set(logging.makeLogRecord({}).__dict__.keys()) | {
    "asctime",
    "message",
    "server_time",
}


class LogfmtServerFormatter(ServerFormatter):
    """ServerFormatter that appends non-reserved record attributes as logfmt."""

    @staticmethod
    def _to_logfmt_value(value):
        if isinstance(value, (dict, list, tuple, set)):
            value = json.dumps(value, sort_keys=True, default=str)
        else:
            value = str(value)

        if value == "":
            return '""'

        needs_quotes = any(ch.isspace() for ch in value) or any(
            ch in value for ch in ('"', "=", "\\")
        )
        if not needs_quotes:
            return value

        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    def format(self, record):
        base_message = super().format(record)

        fields = []
        for key in sorted(record.__dict__.keys()):
            if key in RESERVED_RECORD_ATTRS or key.startswith("_"):
                continue

            value = record.__dict__[key]
            if value is None:
                continue

            fields.append(f"{key}={self._to_logfmt_value(value)}")

        if not fields:
            return base_message

        return f"{base_message} {' '.join(fields)}"
