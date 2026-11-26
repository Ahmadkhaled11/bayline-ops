"""My own cases for the extraction parser."""

import pytest

from bayline.assist.extract import ParseError, parse_extraction


def test_lower_case_number_with_spaces_is_normalised_and_wrong_check_digit_is_kept_as_written():
    raw = ('```json\n{"primary_topic": "status_question", "topics": [], '
           '"tracking_numbers": ["byl 2604-11871", "BYL 260411872"]}\n```')
    result = parse_extraction(raw)
    assert result.topics == ("status_question",)
    assert result.tracking_numbers == ("BYL260411871",)
    assert result.invalid_tracking_mentions == ("BYL 260411872",)


def test_reply_cut_short_inside_a_fence_is_a_parse_error():
    with pytest.raises(ParseError):
        parse_extraction('```json\n{"primary_topic": "delay", "topics": ["delay"]')
