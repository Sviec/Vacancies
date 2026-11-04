"""Текст failed-прогона: 403, 429 и 503 различимы без тела ответа и секретов."""

from app.services.parsing import _failure_text
from app.utils.errors import ExternalServiceError


def test_status_errors_keep_safe_details_and_differ() -> None:
    forbidden = ExternalServiceError(
        "External service call failed",
        details={"service": "hh", "status_code": 403, "hh_error_type": "forbidden", "attempts": 1},
    )
    limited = ExternalServiceError(
        "External service call failed",
        details={
            "hh_error_type": "too_many_requests",
            "status_code": 429,
            "service": "hh",
        },
    )
    unavailable = ExternalServiceError(
        "External service call failed",
        details={"status_code": 503, "service": "hh"},
    )

    forbidden_text = _failure_text(forbidden)
    limited_text = _failure_text(limited)
    unavailable_text = _failure_text(unavailable)

    assert forbidden_text == (
        "ExternalServiceError: External service call failed "
        "(status_code=403, hh_error_type=forbidden, service=hh)"
    )
    assert limited_text == (
        "ExternalServiceError: External service call failed "
        "(status_code=429, hh_error_type=too_many_requests, service=hh)"
    )
    assert unavailable_text == (
        "ExternalServiceError: External service call failed (status_code=503, service=hh)"
    )
    assert len({forbidden_text, limited_text, unavailable_text}) == 3
    assert "attempts" not in forbidden_text


def test_reason_without_status_and_plain_exception() -> None:
    timeout = ExternalServiceError(
        "External service call failed",
        details={"reason": "timeout", "service": "hh"},
    )
    assert _failure_text(timeout) == (
        "ExternalServiceError: External service call failed (reason=timeout, service=hh)"
    )
    assert _failure_text(RuntimeError("boom")) == "RuntimeError: boom"
    assert _failure_text(ExternalServiceError("External service call failed")) == (
        "ExternalServiceError: External service call failed"
    )


def test_unsafe_details_are_omitted() -> None:
    class TaggedError(Exception):
        def __init__(self) -> None:
            self.details: object = "status_code=403 token=secret"
            super().__init__("boom")

    leaked = ExternalServiceError(
        "External service call failed",
        details={
            "status_code": 403,
            "hh_error_type": "forbidden",
            "service": "hh",
            "reason": "https://api.hh.ru/vacancies?access_token=secret",
            "body": '{"errors":[{"type":"forbidden","value":"secret-token"}]}',
            "token": "secret-token",
            "url": "https://api.hh.ru/vacancies?access_token=secret",
        },
    )
    text = _failure_text(leaked)
    assert text == (
        "ExternalServiceError: External service call failed "
        "(status_code=403, hh_error_type=forbidden, service=hh)"
    )
    assert "secret" not in text
    assert "http" not in text
    assert "body" not in text
    assert _failure_text(TaggedError()) == "TaggedError: boom"
