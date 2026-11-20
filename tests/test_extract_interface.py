"""Public contract for the message extraction helper."""

from types import SimpleNamespace

import pytest

from bayline.assist import extract as helper
from bayline.llm import ChatResponse
from bayline.models import Topic

if not all(hasattr(helper, name) for name in ("parse_extraction", "extract")):
    pytest.skip("Message extraction parser and extract are not implemented yet", allow_module_level=True)


def test_clean_fields_and_numbers():
    result = helper.parse_extraction('{"primary_topic":"delay","topics":["return","delay","delay"],'
        '"tracking_numbers":["BYL260411872","byl 2604-11871"]}')
    assert result.primary_topic == "delay"
    assert set(result.topics) <= {topic.value for topic in Topic}
    assert list(result.topics) == sorted(set(result.topics))
    assert result.primary_topic in result.topics
    assert list(result.tracking_numbers) == ["BYL260411871"]
    assert list(result.invalid_tracking_mentions) == ["BYL260411872"]
    assert list(result.tracking_numbers) == sorted(result.tracking_numbers)
    assert list(result.invalid_tracking_mentions) == sorted(result.invalid_tracking_mentions)


def test_unknown_topic():
    with pytest.raises(helper.ParseError):
        helper.parse_extraction('{"primary_topic":"refund","topics":["refund"],"tracking_numbers":[]}')


CLEAN = '{"primary_topic": "delay", "topics": ["delay"], "tracking_numbers": []}'


@pytest.mark.parametrize("raw", ["```json\n" + CLEAN + "\n```", "Here is the JSON: " + CLEAN + " Thanks."])
def test_json_is_read_out_of_fences_and_text(raw):
    result = helper.parse_extraction(raw)
    assert result.primary_topic == "delay"
    assert list(result.topics) == ["delay"]
    assert list(result.tracking_numbers) == []
    assert list(result.invalid_tracking_mentions) == []


@pytest.mark.parametrize("raw", ['{"primary_topic":"delay",}', '{"primary_topic":', ''])
def test_bad_json(raw):
    with pytest.raises(helper.ParseError) as error:
        helper.parse_extraction(raw)
    assert isinstance(error.value, ValueError)
    assert str(error.value)


def test_extract_matches_parser():
    raw = '{"primary_topic":"other","topics":["other"],"tracking_numbers":[]}'

    class Client:
        def complete(self, request):
            return ChatResponse(raw, "test", "stop")

    result = helper.extract(Client(), SimpleNamespace(id="M-1", body="Hello"))
    expected = helper.parse_extraction(raw)
    for field in ("primary_topic", "topics", "tracking_numbers", "invalid_tracking_mentions"):
        assert getattr(result, field) == getattr(expected, field)
