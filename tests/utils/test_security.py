import logging

from utu.utils.log import RedactingFormatter, SensitiveDataFilter
from utu.utils.security import REDACTED, redact_sensitive_data, redact_sensitive_text


def test_redact_sensitive_data_handles_nested_credentials_without_mutating_input():
    raw = {
        "model": {
            "api_key": "model-secret",
            "base_url": "https://internal.example/v1",
            "max_tokens": 4096,
        },
        "headers": {"Authorization": "Bearer header-secret"},
        "items": ["UTU_LLM_API_KEY=inline-secret", {"password": "db-secret"}],
    }

    safe = redact_sensitive_data(raw)

    assert safe == {
        "model": {"api_key": REDACTED, "base_url": REDACTED, "max_tokens": 4096},
        "headers": {"Authorization": REDACTED},
        "items": ["UTU_LLM_API_KEY=***", {"password": REDACTED}],
    }
    assert raw["model"]["api_key"] == "model-secret"


def test_redact_sensitive_text_removes_bearer_and_database_urls():
    safe = redact_sensitive_text(
        "Authorization: Bearer abc.def DB_URL=postgresql://user:pass@db/name "
        "fallback=postgresql://admin:another-secret@db/other "
        "details={'api_key': 'traceback-secret'}"
    )

    assert "abc.def" not in safe
    assert "user:pass" not in safe
    assert "another-secret" not in safe
    assert "traceback-secret" not in safe
    assert "Authorization: ***" in safe
    assert "DB_URL=***" in safe


def test_redact_sensitive_data_covers_provider_specific_keys():
    safe = redact_sensitive_data(
        {
            "github_access_token": "github-secret",
            "provider_client_secret": "client-secret",
            "service_base_url": "https://internal.example",
            "max_tokens": 2048,
        }
    )

    assert safe["github_access_token"] == REDACTED
    assert safe["provider_client_secret"] == REDACTED
    assert safe["service_base_url"] == REDACTED
    assert safe["max_tokens"] == 2048


def test_logging_redaction_covers_structured_arguments_and_traceback_text():
    record = logging.LogRecord(
        name="utu.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="request failed: %s",
        args=({"api_key": "log-secret", "max_tokens": 32},),
        exc_info=None,
    )
    record.exc_text = "DB_URL=postgresql://user:password@db/name"

    assert SensitiveDataFilter().filter(record)
    rendered = RedactingFormatter("%(message)s %(exc_text)s").format(record)

    assert "log-secret" not in rendered
    assert "password" not in rendered
    assert "max_tokens" in rendered
