import pytest

from bayline.money import egp_to_piastres, format_egp
from bayline.rules.pricing import shipping_fee


@pytest.mark.parametrize("value,expected", [(300000, "3,000 EGP"), (4550, "45.50 EGP"),
                                          (0, "0 EGP"), (-101, "-1.01 EGP")])
def test_money(value, expected):
    assert format_egp(value) == expected
    assert egp_to_piastres(expected.replace(" EGP", "").replace(",", "")) == value


@pytest.mark.parametrize("value", ["1.001", "bad", "NaN", "Infinity"])
def test_invalid_money(value):
    with pytest.raises(ValueError):
        egp_to_piastres(value)


@pytest.mark.parametrize("lane,service,base,extra", [
    ("domestic", "express", 75, 12), ("domestic", "standard", 45, 8),
    ("domestic", "economy", 35, 6), ("international", "express", 650, 60),
    ("international", "standard", 420, 40), ("international", "economy", 300, 30),
])
def test_all_prices(lane, service, base, extra):
    assert shipping_fee(lane, service, 0.1, False, 0) == base * 100
    assert shipping_fee(lane, service, 5, False, 0) == base * 100
    assert shipping_fee(lane, service, 5.1, False, 0) == (base + extra) * 100
    assert shipping_fee(lane, service, 5, True, 1) == base * 100 + 2000
    assert shipping_fee(lane, service, 5, True, 300001) == base * 100 + 3001


@pytest.mark.parametrize("weight", [0, -1, float("nan"), float("inf")])
def test_invalid_weight(weight):
    with pytest.raises(ValueError):
        shipping_fee("domestic", "standard", weight, False, 100)


@pytest.mark.parametrize("declared", [-1, 0.5, float("nan")])
def test_declared_money_is_whole_piastres(declared):
    with pytest.raises(ValueError):
        shipping_fee("domestic", "standard", 2, True, declared)
