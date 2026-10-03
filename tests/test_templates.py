"""The template bank: every language complete, every message renders."""

import pytest

from engine import NO_DANGER_SIGN, REFER_URGENT, UNSURE, check, load_pack, load_templates, question, render
from engine.decide import Decision

PACK = load_pack()
TEMPLATES = load_templates()
ALL_REASONS = [("not_checked", {"signs": PACK.sign_ids}), ("age_unknown", {}), ("age_out_of_scope", {})]
ALL_WARNINGS = [("overridden", {"signs": PACK.sign_ids}), ("temperature_implausible", {"value": 48.0}),
                *[(rule.warning, {}) for rule in PACK.consistency]]


def test_languages():
    assert set(TEMPLATES) == {"en", "fr", "ary-Arab", "ary-Latn", "sw"}


def test_template_bank_is_complete():
    assert check(TEMPLATES, PACK) == []


@pytest.mark.parametrize("lang", sorted(TEMPLATES))
def test_every_message_renders(lang):
    t = TEMPLATES[lang]
    refer = render(Decision(REFER_URGENT, present=PACK.sign_ids, warnings=ALL_WARNINGS), t)
    assert all(t["signs"][s]["present"] in refer["text"] for s in PACK.sign_ids)
    assert len(refer["warnings"]) == len(ALL_WARNINGS)
    unsure = render(Decision(UNSURE, reasons=ALL_REASONS), t)["text"]
    assert all(t["reasons"][rid].split("{")[0] in unsure for rid, _ in ALL_REASONS)
    assert render(Decision(NO_DANGER_SIGN), t)["text"] == t["outcomes"]["NO_DANGER_SIGN"]
    for slot in ["age", *PACK.sign_ids]:
        q = question(slot, t)
        assert q["text"] and all(option["label"] for option in q["options"])
