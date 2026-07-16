"""Structured logging, metrics, and request-context tests."""

import json
import logging

from gerclaw_api.context import (
    bind_request_context,
    request_id_var,
    reset_request_context,
    trace_id_var,
)
from gerclaw_api.logging import JsonFormatter, configure_logging
from gerclaw_api.metrics import render_metrics
from gerclaw_api.middleware import _safe_header_id, _safe_trace_id


def test_json_logging_binds_context_and_redacts_extras() -> None:
    class SecretObject:
        def __str__(self) -> str:
            return "Authorization: Bearer object-secret-value"

    tokens = bind_request_context("request_logging_001", "trace_logging_001")
    try:
        record = logging.LogRecord(
            name="gerclaw.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="患者电话 13800138000",
            args=(),
            exc_info=None,
        )
        record.authorization = "Bearer secret"
        record.sdk_object = SecretObject()
        payload = json.loads(JsonFormatter().format(record))

        assert payload["request_id"] == "request_logging_001"
        assert payload["trace_id"] == "trace_logging_001"
        assert payload["message"] == "患者电话 [PHONE]"
        assert payload["attributes"]["authorization"] == "[REDACTED]"
        assert "object-secret-value" not in str(payload)
    finally:
        reset_request_context(tokens)

    assert request_id_var.get() == ""
    assert trace_id_var.get() == ""


def test_logging_configuration_metrics_and_header_ids() -> None:
    configure_logging("WARNING")
    assert logging.getLogger().level == logging.WARNING
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("openai").level == logging.WARNING

    body, media_type = render_metrics()
    assert b"gerclaw_http_requests_total" in body
    assert b"gerclaw_risk_alerts_total" in body
    assert "text/plain" in media_type
    assert _safe_header_id("request_valid_001", "req") == "request_valid_001"
    assert _safe_header_id("bad", "req").startswith("req_")
    assert _safe_header_id("request_13800138000", "req") != "request_13800138000"
    assert _safe_trace_id("trace_valid_001") == "trace_valid_001"
    assert _safe_trace_id("request_valid_001").startswith("trace_")
    assert _safe_trace_id("trace_13800138000") != "trace_13800138000"
