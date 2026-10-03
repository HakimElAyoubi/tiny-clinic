"""Safety properties, checked over every combination of what the model can read."""

import itertools

import pytest

from engine import NEED_INFO, NO_DANGER_SIGN, REFER_URGENT, Case, decide, load_pack

PACK = load_pack()
SIGNS = PACK.sign_ids
READINGS = list(itertools.product([True, False, None], repeat=len(SIGNS)))  # 243 model readings
TRUTHS = list(itertools.product([True, False], repeat=len(SIGNS)))          # 32 real children
CONFIDENCES = [None, 0.5, 0.95]


def model_case(reading, confidence, age=24):
    case = Case.empty(PACK)
    case.obs["age"].model, case.obs["age"].confidence = age, confidence
    for sign, value in zip(SIGNS, reading):
        case.obs[sign].model, case.obs[sign].confidence = value, confidence
    return case


def visit(truth, reading, confidence, age=24):
    """Follow the app: ask whatever the engine asks, answer truthfully, until it decides."""
    case, asked = model_case(reading, confidence, age), set()
    while True:
        decision = decide(case, PACK)
        if decision.outcome != NEED_INFO:
            return decision
        assert not asked & set(decision.questions), "a question was asked twice"
        asked |= set(decision.questions)
        for slot in decision.questions:
            case.answer(slot, age if slot == "age" else truth[SIGNS.index(slot)])


@pytest.mark.parametrize("confidence", CONFIDENCES)
def test_refers_if_and_only_if_a_sign_reads_present(confidence):
    for reading in READINGS:
        outcome = decide(model_case(reading, confidence), PACK).outcome
        assert (outcome == REFER_URGENT) == (True in reading), reading


@pytest.mark.parametrize("confidence", CONFIDENCES)
def test_no_danger_sign_needs_every_sign_settled(confidence):
    for reading in READINGS:
        if decide(model_case(reading, confidence), PACK).outcome == NO_DANGER_SIGN:
            assert all(v is False for v in reading)
            assert confidence is not None and confidence >= PACK.model_absent_min_confidence


def test_checklist_mode_never_misses_a_danger_sign():
    """With no model confidence, every absent reading is confirmed by the health worker, so
    a real danger sign is always found, whatever the model read."""
    for truth, reading in itertools.product(TRUTHS, READINGS):
        outcome = visit(truth, reading, confidence=None).outcome
        if True in truth:
            assert outcome == REFER_URGENT, (truth, reading)
        elif True not in reading:
            assert outcome == NO_DANGER_SIGN, (truth, reading)


def test_not_sure_never_gives_no_danger_sign():
    for reading in READINGS:
        case = model_case(reading, None)
        for _ in range(3):
            decision = decide(case, PACK)
            if decision.outcome != NEED_INFO:
                break
            for slot in decision.questions:
                case.answer(slot, None)
        assert decision.outcome != NO_DANGER_SIGN, reading
