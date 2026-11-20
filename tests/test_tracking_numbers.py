import pytest

from bayline.tracking_numbers import is_valid, make_tracking_number, normalise

ANCHORS = (
    "BYL260411871", "BYL260415328", "BYL260439062", "BYL260442157", "BYL260444716",
    "BYL260448907", "BYL260451265", "BYL260453097", "BYL260455803", "BYL260459136",
    "BYL260462072", "BYL260464888", "BYL260467527", "BYL260470315", "BYL260473640",
)


@pytest.mark.parametrize("number", ANCHORS + ("BYL260480009",))
def test_valid(number):
    assert is_valid(number)
    assert make_tracking_number(int(number[5:-1])) == number


@pytest.mark.parametrize("number", ["BYL260411872", "BYL26041187", "", "BYL26041187x"])
def test_invalid(number):
    assert not is_valid(number)


def test_normalise():
    assert normalise("byl 2604-11871") == "BYL260411871"


def test_serial_bounds():
    for serial in (-1, 1000000, 1.5):
        with pytest.raises(ValueError):
            make_tracking_number(serial)
