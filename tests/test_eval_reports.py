"""Committed reports must reproduce from their saved replies."""

import pytest

from bayline.assist import extract
from bayline.config import ROOT
from bayline.sample.authored import load_messages
from evals.kit import check_report, labels


@pytest.mark.parametrize("path", sorted((ROOT / "evals/reports").glob("*.md")))
def test_report(path):
    assert hasattr(extract, "parse_extraction"), "Report exists but parse_extraction is missing"
    try:
        check_report(path, load_messages(), labels(), extract.parse_extraction)
    except ValueError as exc:
        pytest.fail(str(exc))
