import pytest

from bayline import cli, repository
from bayline.db import connect


@pytest.mark.parametrize("pieces,piece_word", [(1, "piece"), (2, "pieces"), (3, "pieces")])
@pytest.mark.parametrize("late_days,day_word", [(0, "days"), (1, "day"), (2, "days")])
def test_shipment_text_uses_singular_and_plural_counts(
    seeded_db, pieces, piece_word, late_days, day_word
):
    with connect(seeded_db) as connection:
        summary = repository.shipment_summary(
            connection, "BYL260442157", repository.snapshot_time(connection)
        )
    summary.update(pieces=pieces, late_business_days=late_days, events=[])

    lines = cli._shipment_text(summary).splitlines()

    assert (
        f"Goods: {summary['goods_description']} "
        f"({pieces} {piece_word}, {summary['weight_kg']} kg)"
    ) in lines
    assert (
        f"Delay: {summary['delay_class']} ({late_days} business {day_word} late)"
    ) in lines
