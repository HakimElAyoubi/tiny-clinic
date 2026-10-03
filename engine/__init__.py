"""Tiny Clinic rule engine: IMCI general danger signs, decided from a compact case record.

    from engine import Case, decide, load_pack, load_templates, render
    pack = load_pack()
    case = Case.from_record("A24 F | C:FEV D2 T38.9 | DRK? VOM1 CNV0 LTH? CNN0", pack)
    decision = decide(case, pack)            # REFER_URGENT: vomits everything
    render(decision, load_templates()["ary-Latn"])["text"]
"""

from .decide import NEED_INFO, NO_DANGER_SIGN, REFER_URGENT, UNSURE, Case, Decision, Observation, decide
from .grammar import GRAMMAR_PATH, gbnf
from .record import format_record, parse
from .rulepack import AGE, RULES_DIR, load_pack, load_templates
from .templates import check, question, render

__all__ = [
    "AGE", "GRAMMAR_PATH", "NEED_INFO", "NO_DANGER_SIGN", "REFER_URGENT", "RULES_DIR", "UNSURE",
    "Case", "Decision", "Observation", "check", "decide", "format_record", "gbnf", "load_pack",
    "load_templates", "parse", "question", "render",
]
