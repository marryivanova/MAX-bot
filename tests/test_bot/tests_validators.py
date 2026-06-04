import pytest

from app.api.endpoints.helper import _validate_and_process_text


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("Hello__World", "Hello\nWorld"),
        ("__Start", "\nStart"),
        ("End__", "End\n"),
        ("__", "\n"),
        ("a__b__c", "a\nb\nc"),
    ],
)
def test_validate_and_process_text_valid_inputs(input_text, expected):
    result = _validate_and_process_text(input_text)
    assert result == expected


def test_validate_and_process_text_whitespace_trimming():
    result = _validate_and_process_text("  a__b  ")
    assert result == "a\nb"
