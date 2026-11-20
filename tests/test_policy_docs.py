from pathlib import Path

import pytest

from bayline import policies
from bayline.business_days import HOLIDAYS_2026
from bayline.config import ROOT
from bayline.rules.pricing import RATES
from bayline.timeutil import format_day

FACTS = {
    "returns-policy": [
        "Returns are accepted within 30 calendar days after delivery.",
        "Day 1 is the calendar day after delivery.",
        "Days are counted in the time zone of the delivery address.",
        "Perishable goods, batteries and hazardous goods cannot be returned.",
        "Bayline Returns is available only for merchants on the Bayline Returns plan.",
        "A shipment can have only one open return at a time.",
    ],
    "claims-policy": [
        "Damage claims must be made within 14 calendar days after delivery.",
        "Without insurance, we pay up to the declared value, and at most 3,000 EGP.",
        "With insurance, we pay up to the declared value.",
        "A shipment can be claimed as lost 10 business days after the promised delivery date.",
        "Express shipments delivered one or more business days late get their shipping fee back.",
    ],
    "service-levels": ["Our business days are Sunday to Thursday.",
        "Shipments picked up after 16:00 Cairo time count from the next business day."],
    "prices-2026": ["Insurance costs 1% of the declared value, at least 20 EGP."],
    "delivery-and-address-changes": ["An address can be changed before the shipment is out for delivery.",
        "An address can be changed only within the same city.", "An address can be changed once per shipment.",
        "Address changes are not possible while a shipment is held at customs."],
    "international-shipping": ["We deliver to Dubai, Riyadh and Amman through partner carriers.",
        "Customs checks can add days that we cannot control."],
    "support-desk-manual": ["A shipment with no tracking scan for 7 days is treated as possibly lost."],
    "reply-style-guide": ["Saturday 24 October 2026", "3,000 EGP", "Bayline Cargo Customer Service"],
    "escalation-guide": [], "glossary": [],
}


@pytest.mark.parametrize("slug,facts", FACTS.items())
def test_required_facts(slug, facts):
    text = policies.get_document(slug)
    assert text.startswith("# ")
    for fact in facts:
        assert fact in text


def test_all_documents_discovered():
    documents = policies.list_documents()
    assert set(FACTS) <= {d["slug"] for d in documents}
    assert "message-tags" in {d["slug"] for d in documents}
    assert len({d["slug"] for d in documents}) == len(documents)
    for path in (ROOT / "docs").rglob("*.md"):
        assert path.read_text(encoding="utf-8").startswith("# "), path


def test_prices_and_calendar_facts():
    prices = policies.get_document("prices-2026")
    for lane, services in RATES.items():
        for service, (base, extra) in services.items():
            assert f"{service.title()} {lane}: {base} EGP for the first 5 kg and {extra} EGP for each kg over 5 kg." in prices
    calendar = policies.get_document("service-levels")
    for holiday in HOLIDAYS_2026:
        weekday, day = format_day(holiday).split(" ", 1)
        assert f"| {day} | {weekday} |" in calendar


def test_reading_cannot_escape_docs(tmp_path):
    from bayline.repository import NotFoundError

    (tmp_path / "policies").mkdir()
    for slug in ("../secret", "missing", "/etc/passwd"):
        with pytest.raises(NotFoundError):
            policies.get_document(slug, tmp_path)


def test_rule_and_client_boundaries():
    import ast

    source = ROOT / "src/bayline"
    for path in (source / "rules").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in {"db", "repository", "llm", "sample"}
    for path in source.rglob("*.py"):
        if "llm" in path.parts or path.name == "cli.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert "llm" not in (node.module or "").split(".")
    # Parse using the oldest supported grammar even on a newer interpreter.
    for folder in (source, ROOT / "tests"):
        for path in folder.rglob("*.py"):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(Path(path.name)), feature_version=(3, 11))
