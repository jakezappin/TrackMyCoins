from types import SimpleNamespace

import pytest

from app.schemas import LookupResult
from app.services.greysheet import _money, _pick
from app.services.lookups.base import normalize_mint_mark, parse_grade


def parsed(text):
    r = LookupResult(grading_service="PCGS", cert_number="1")
    parse_grade(text, r)
    return r


def test_parse_grade():
    r = parsed("MS64+ DMPL")
    assert (r.grade_prefix, r.grade, r.grade_plus, r.strike_designation) == ("MS", 64, True, "DMPL")
    r = parsed("MS-63 PL")
    assert (r.grade_prefix, r.grade, r.strike_designation) == ("MS", 63, "PL")
    r = parsed("PF65CAM")
    assert (r.grade_prefix, r.grade, r.strike_designation) == ("PR", 65, "CAM")
    r = parsed("66★")
    assert (r.grade, r.grade_star) == (66, True)
    assert parsed("AU58").grade_prefix == "AU"


def test_mint_mark():
    assert normalize_mint_mark("") == "P"
    assert normalize_mint_mark(None) == "P"
    assert normalize_mint_mark("cc") == "CC"


def test_money():
    assert str(_money("$1,234.50")) == "1234.50"
    assert _money("") is None and _money(None) is None


def test_pick_prefers_cac_and_plus():
    rows = [
        {"Grade": 65, "GradeLabel": "65", "IsCac": False, "CpgVal": "200"},
        {"Grade": 65, "GradeLabel": "65", "IsCac": True, "CpgVal": "260"},
        {"Grade": 65, "GradeLabel": "65+", "IsCac": False, "CpgVal": "300"},
        {"Grade": 64, "GradeLabel": "64", "IsCac": False, "CpgVal": "100"},
    ]
    coin = SimpleNamespace(grade=65, grade_plus=False, cac=False)
    assert _pick(rows, coin)["CpgVal"] == "200"
    coin.cac = True
    assert _pick(rows, coin)["CpgVal"] == "260"
    coin.grade_plus, coin.cac = True, False
    assert _pick(rows, coin)["CpgVal"] == "300"
    coin.grade = 62
    assert _pick(rows, coin) is None


@pytest.mark.parametrize("facts,want", [
    ({"Name": "1895 $1, DCAM", "Grade": "PR65DC", "Designation": "DC"}, "DCAM"),
    ({"Name": "1895 $1, CAM", "Grade": "PR64CA", "Designation": "CA"}, "CAM"),
    ({"Name": "1895-O $1, DMPL", "Grade": "MS62DM", "Designation": "DM"}, "DMPL"),
    ({"Name": "1937 1C, CAM", "Grade": "PR65RD", "Designation": "RD"}, "RD CAM"),  # color in one field, cameo in the name
    ({"Name": "1895 $1", "Grade": "PR65+DC", "Designation": ""}, "DCAM"),  # only in the grade
    ({"Name": "1878 8TF $1, VAM-14.8 FS-401", "Grade": "MS63", "Designation": ""}, None),  # variety numbers aren't designations
])
def test_pcgs_cert_designations(monkeypatch, facts, want):
    """PCGS writes designations as codes (CA, DC, DM) and spreads them over the Designation field, the grade and the name."""
    from contextlib import nullcontext

    from app.services.lookups import pcgs

    data = {"PCGSNo": "7330", "Year": 1895, "MintMark": "", **facts}
    monkeypatch.setattr(pcgs, "_client", lambda: nullcontext())
    monkeypatch.setattr(pcgs, "_get", lambda c, path, **k: data if "Facts" in path else {"Images": []})
    assert pcgs.lookup("12345678").strike_designation == want
