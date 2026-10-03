"""Run the shared test vectors in rules/tests/cases.yaml."""

import pytest
import yaml

from engine import RULES_DIR, Case, decide, load_pack

PACK = load_pack()
VECTORS = yaml.safe_load((RULES_DIR / "tests" / "cases.yaml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("vector", VECTORS, ids=[v["name"] for v in VECTORS])
def test_vector(vector):
    case = Case.from_record(vector["record"], PACK, vector.get("confidence"))
    for slot, value in (vector.get("answers") or {}).items():
        case.answer(slot, value)
    decision = decide(case, PACK)
    expect = vector["expect"]
    assert decision.outcome == expect["outcome"]
    for key in ("present", "questions", "pending"):
        if key in expect:
            assert getattr(decision, key) == expect[key], key
    if "reasons" in expect:
        assert [rid for rid, _ in decision.reasons] == expect["reasons"]
    if "warnings" in expect:
        assert [wid for wid, _ in decision.warnings] == expect["warnings"]
