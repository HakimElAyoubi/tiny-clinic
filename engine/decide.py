"""Decide what the health worker should do, from the case record and their answers.

Outcomes:
  REFER_URGENT    a danger sign is present, from the note or from the health worker
  NEED_INFO       ask `questions` first
  UNSURE          something stayed unchecked or is outside the protocol: ask a clinician
  NO_DANGER_SIGN  every danger sign checked absent, age within the protocol

Referral is never delayed: a present sign refers at once, whatever else is unknown.
"No danger sign" needs every sign, and the age, to be settled: answered by the health
worker, or read from the note with confidence at or above the rule pack's threshold.
"""

from dataclasses import dataclass, field

from .record import parse
from .rulepack import AGE

REFER_URGENT = "REFER_URGENT"
NEED_INFO = "NEED_INFO"
UNSURE = "UNSURE"
NO_DANGER_SIGN = "NO_DANGER_SIGN"
DOCUMENTATION_SLOTS = ("sex", "complaints", "duration", "temperature")
NOT_ASKED = object()  # the health worker has not answered this slot


@dataclass
class Observation:
    model: object = None             # value read from the note; None = not mentioned
    confidence: float | None = None  # the model's confidence in that value
    worker: object = NOT_ASKED       # the health worker's answer; None = "not sure"

    @property
    def asked(self):
        return self.worker is not NOT_ASKED

    @property
    def value(self):
        return self.worker if self.asked else self.model


@dataclass
class Case:
    obs: dict

    @classmethod
    def empty(cls, pack):
        return cls({slot: Observation() for slot in [AGE, *DOCUMENTATION_SLOTS, *pack.sign_ids]})

    @classmethod
    def from_record(cls, line, pack, confidence=None):
        """Case from the model's record. `confidence` is one number for every slot, or
        {slot: number, "default": number}. An unreadable record gives an empty case, so
        the app falls back to asking every question."""
        case = cls.empty(pack)
        try:
            values = parse(line, pack)
        except ValueError:
            return case
        for slot, value in values.items():
            c = confidence.get(slot, confidence.get("default")) if isinstance(confidence, dict) else confidence
            case.obs[slot] = Observation(model=value, confidence=c)
        return case

    def answer(self, slot, value):
        """Record the health worker's answer: True / False / None ("not sure") for a sign,
        also "present" / "absent" / "not_sure"; months or None for the age."""
        if isinstance(value, str):
            value = {"present": True, "absent": False, "not_sure": None}[value]
        self.obs[slot].worker = value
        return self

    def values(self):
        return {slot: o.value for slot, o in self.obs.items()}


@dataclass
class Decision:
    outcome: str
    present: list = field(default_factory=list)    # danger signs found
    questions: list = field(default_factory=list)  # slots to ask next, in protocol order
    pending: list = field(default_factory=list)    # signs still unchecked when referring; never wait for them
    reasons: list = field(default_factory=list)    # [(reason id, params)] behind UNSURE
    warnings: list = field(default_factory=list)   # [(warning id, params)]
    cite: str = ""


def _present(o):
    # "Not sure" from the health worker never cancels a sign the note reads as present.
    return o.value is True or (o.asked and o.worker is None and o.model is True)


def _settled(o, threshold):
    """Known well enough to rule a danger sign out: answered by the health worker, or read
    from the note with enough confidence."""
    if o.asked:
        return o.worker is not None
    return o.model is not None and o.confidence is not None and o.confidence >= threshold


def decide(case, pack):
    obs, signs = case.obs, pack.sign_ids
    threshold = pack.model_absent_min_confidence
    present = [s for s in signs if _present(obs[s])]
    unresolved = [s for s in signs if s not in present and not _settled(obs[s], threshold)]

    warnings = []
    overridden = [s for s in signs if obs[s].asked and None not in (obs[s].model, obs[s].worker)
                  and obs[s].worker != obs[s].model]
    if overridden:
        warnings.append(("overridden", {"signs": overridden}))
    for rule in pack.consistency:
        if _present(obs[rule.if_present]) and obs[rule.expect_present].value is False:
            warnings.append((rule.warning, {}))
    temperature = obs["temperature"].value
    low, high = pack.temperature_plausible_c
    if temperature is not None and not low <= temperature <= high:
        warnings.append(("temperature_implausible", {"value": temperature}))

    if present:
        return Decision(REFER_URGENT, present=present, pending=unresolved, warnings=warnings, cite=pack.cite)

    age = obs[AGE]
    questions = [AGE] if not age.asked and not _settled(age, threshold) else []
    questions += [s for s in unresolved if not obs[s].asked]
    if questions:
        return Decision(NEED_INFO, questions=questions, warnings=warnings)

    reasons = []
    if unresolved:
        reasons.append(("not_checked", {"signs": unresolved}))
    if age.value is None:
        reasons.append(("age_unknown", {}))
    elif not pack.min_age_months <= age.value <= pack.max_age_months:
        reasons.append(("age_out_of_scope", {}))
    if reasons:
        return Decision(UNSURE, reasons=reasons, warnings=warnings)
    return Decision(NO_DANGER_SIGN, warnings=warnings)
