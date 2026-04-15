import json
import logging

from django.test import SimpleTestCase
from pythonjsonlogger.jsonlogger import JsonFormatter

from coldfront.config.log_formatters import LogfmtServerFormatter


class LogFormatterParityTests(SimpleTestCase):
    def setUp(self):
        self.logger = logging.getLogger("coldfront.core.project.tests.log_formatter")
        self.logfmt_formatter = LogfmtServerFormatter(
            fmt="[{server_time}] {name} {levelname} {message}",
            style="{",
        )
        self.json_formatter = JsonFormatter(
            "%(message)s %(requesting_user)s %(project)s %(status)s %(error)s"
        )

    def _record(self, *, message, extra):
        return self.logger.makeRecord(
            self.logger.name,
            logging.INFO,
            __file__,
            1,
            message,
            args=(),
            exc_info=None,
            extra=extra,
        )

    def test_logfmt_and_json_include_same_extra_fields(self):
        extra = {
            "requesting_user": "alice",
            "project": "my-project",
            "status": "failure",
            "error": "API timeout",
        }
        logfmt_record = self._record(message="AD user addition failed.", extra=extra)
        json_record = self._record(message="AD user addition failed.", extra=extra)

        logfmt_output = self.logfmt_formatter.format(logfmt_record)
        json_output = self.json_formatter.format(json_record)
        json_payload = json.loads(json_output)

        self.assertIn("requesting_user=alice", logfmt_output)
        self.assertIn("project=my-project", logfmt_output)
        self.assertIn("status=failure", logfmt_output)
        self.assertIn('error="API timeout"', logfmt_output)

        self.assertEqual(json_payload["requesting_user"], extra["requesting_user"])
        self.assertEqual(json_payload["project"], extra["project"])
        self.assertEqual(json_payload["status"], extra["status"])
        self.assertEqual(json_payload["error"], extra["error"])

    def test_logfmt_quotes_whitespace_and_special_characters(self):
        record = self._record(
            message="Project user update completed.",
            extra={
                "requesting_user": "alice",
                "project": 'project "alpha"',
            },
        )

        output = self.logfmt_formatter.format(record)

        self.assertIn('project="project \\"alpha\\""', output)
