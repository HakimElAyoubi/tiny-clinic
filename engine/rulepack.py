"""Load the rule pack (rules/danger_signs.yaml) and the template bank (rules/templates/)."""

from dataclasses import dataclass
from pathlib import Path

import yaml

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"
AGE = "age"


@dataclass(frozen=True)
class DangerSign:
    id: str
    code: str
    check: str  # "ask" or "look", as on the chart


@dataclass(frozen=True)
class Consistency:
    if_present: str
    expect_present: str
    warning: str


@dataclass(frozen=True)
class RulePack:
    id: str
    version: str
    cite: str
    min_age_months: int
    max_age_months: int
    model_absent_min_confidence: float
    danger_signs: tuple
    consistency: tuple
    complaints: tuple  # complaint codes, in record order
    max_complaints: int
    temperature_plausible_c: tuple

    @property
    def sign_ids(self):
        return [s.id for s in self.danger_signs]


def load_pack(path=RULES_DIR / "danger_signs.yaml"):
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    signs = tuple(DangerSign(**s) for s in raw["danger_signs"])
    ids, codes = [s.id for s in signs], [s.code for s in signs]
    if len(set(ids)) != len(ids) or len(set(codes)) != len(codes):
        raise ValueError("danger sign ids and codes must be unique")
    consistency = tuple(Consistency(**c) for c in raw.get("consistency", []))
    for rule in consistency:
        if rule.if_present not in ids or rule.expect_present not in ids:
            raise ValueError(f"consistency rule names an unknown sign: {rule}")
    record = raw["record"]
    low, high = record["temperature_plausible_c"]
    return RulePack(
        id=raw["id"],
        version=raw["version"],
        cite=raw["classification"]["cite"],
        min_age_months=int(raw["scope"]["min_age_months"]),
        max_age_months=int(raw["scope"]["max_age_months"]),
        model_absent_min_confidence=float(raw["policy"]["model_absent_min_confidence"]),
        danger_signs=signs,
        consistency=consistency,
        complaints=tuple(record["complaints"]),
        max_complaints=int(record["max_complaints"]),
        temperature_plausible_c=(float(low), float(high)),
    )


def load_templates(directory=RULES_DIR / "templates"):
    """{language code: templates} for every rules/templates/*.yaml."""
    templates = {}
    for path in sorted(Path(directory).glob("*.yaml")):
        t = yaml.safe_load(path.read_text(encoding="utf-8"))
        templates[t["language"]] = t
    return templates
