import pytest

from bayline.assist.extract import ParseError, parse_extraction


def test_number_inside_text_with_wrong_check_digit_is_invalid():
    raw = 'Sure! {"primary_topic": "delay", "topics": ["delay"], "tracking_numbers": ["BYL260411872"]}'
    result = parse_extraction(raw)
    assert result.tracking_numbers == []
    assert result.invalid_tracking_mentions == ["BYL260411872"]


def test_reply_cut_short_says_so():
    with pytest.raises(ParseError, match="cut short"):
        parse_extraction('{"primary_topic": "delay", "topics": ["del')
