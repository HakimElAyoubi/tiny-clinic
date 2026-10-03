"""Turn decisions and questions into the fixed strings of one language (rules/templates/)."""

import string

from .rulepack import AGE

# Every template the engine can use, with the placeholders each one must accept.
REQUIRED = {
    "outcomes": {"REFER_URGENT": {"signs"}, "NO_DANGER_SIGN": set(), "UNSURE": {"reason"}},
    "reasons": {"not_checked": {"signs"}, "age_unknown": set(), "age_out_of_scope": set()},
    "warnings": {"overridden": {"signs"}, "temperature_implausible": {"value"}},
}
SIGN_KEYS = ("name", "question", "present", "absent")


def placeholders(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def check(templates, pack):
    """Problems in the template bank, as readable strings; an empty list means complete."""
    required = {**REQUIRED, "warnings": {**REQUIRED["warnings"], **{c.warning: set() for c in pack.consistency}}}
    problems = []
    for lang, t in templates.items():
        for key in ("list_separator", "answers", "questions"):
            if key not in t:
                problems.append(f"{lang}: missing {key}")
        if "not_sure" not in t.get("answers", {}):
            problems.append(f"{lang}: missing answers.not_sure")
        if AGE not in t.get("questions", {}):
            problems.append(f"{lang}: missing questions.age")
        for sign in pack.sign_ids:
            for key in SIGN_KEYS:
                text = t.get("signs", {}).get(sign, {}).get(key)
                if not text:
                    problems.append(f"{lang}: missing signs.{sign}.{key}")
                elif placeholders(text):
                    problems.append(f"{lang}: signs.{sign}.{key} must not have placeholders")
        for section, entries in required.items():
            for key, expected in entries.items():
                text = t.get(section, {}).get(key)
                if text is None:
                    problems.append(f"{lang}: missing {section}.{key}")
                elif placeholders(text) != expected:
                    problems.append(f"{lang}: {section}.{key} has {sorted(placeholders(text))}, "
                                    f"expected {sorted(expected)}")
    return problems


def _signs(ids, t, key):
    return t["list_separator"].join(t["signs"][i][key] for i in ids)


def _fill(text, params, t):
    return text.format(**{k: _signs(v, t, "name") if k == "signs" else v for k, v in params.items()})


def render(decision, t):
    """{"outcome", "text", "warnings"} for a final decision, in the language of `t`."""
    outcomes = t["outcomes"]
    if decision.outcome == "REFER_URGENT":
        text = outcomes["REFER_URGENT"].format(signs=_signs(decision.present, t, "present"))
    elif decision.outcome == "UNSURE":
        reason = " ".join(_fill(t["reasons"][rid], params, t) for rid, params in decision.reasons)
        text = outcomes["UNSURE"].format(reason=reason)
    elif decision.outcome == "NO_DANGER_SIGN":
        text = outcomes["NO_DANGER_SIGN"]
    else:
        raise ValueError(f"{decision.outcome} has questions, not a message: use question()")
    warnings = [_fill(t["warnings"][wid], params, t) for wid, params in decision.warnings]
    return {"outcome": decision.outcome, "text": text, "warnings": warnings}


def question(slot, t):
    """One question as the app shows it: the text and its answer options."""
    not_sure = {"value": None, "label": t["answers"]["not_sure"]}
    if slot == AGE:
        return {"slot": slot, "kind": "months", "text": t["questions"][AGE], "options": [not_sure]}
    sign = t["signs"][slot]
    return {"slot": slot, "kind": "choice", "text": sign["question"],
            "options": [{"value": True, "label": sign["present"]},
                        {"value": False, "label": sign["absent"]}, not_sure]}
