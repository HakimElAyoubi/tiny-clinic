"""The compact case record: what the model writes, and what the phone stores and syncs.

    A24 F | C:FEV,CGH D2 T38.9 | DRK0 VOM1 CNV? LTH0 CNN0

A = age in months, then sex (M/F), C = complaints, D = days ill, T = temperature in °C,
then one value per danger sign: 1 present, 0 absent, ? unknown. Any field can be "?".
rules/record.gbnf (engine/grammar.py) allows exactly the lines this module parses.
"""

import re

NUMBER = r"(?:[0-9]|[1-9][0-9])"
TEMPERATURE = r"[34][0-9]\.[0-9]"
SIGN_VALUES = {"1": True, "0": False, "?": None}


def pattern(pack):
    code = "(?:" + "|".join(map(re.escape, pack.complaints)) + ")"
    complaints = rf"\?|{code}(?:,{code}){{0,{pack.max_complaints - 1}}}"
    signs = " ".join(rf"{s.code}(?P<{s.id}>[01?])" for s in pack.danger_signs)
    return re.compile(
        rf"A(?P<age>{NUMBER}|\?) (?P<sex>[MF?]) \| C:(?P<complaints>{complaints}) "
        rf"D(?P<duration>{NUMBER}|\?) T(?P<temperature>{TEMPERATURE}|\?) \| {signs}"
    )


def parse(line, pack):
    """Record line -> {slot: value}, with None for "?". Raises ValueError if malformed."""
    match = pattern(pack).fullmatch(line.strip())
    if not match:
        raise ValueError(f"not a case record: {line!r}")
    g = match.groupdict()

    def known(text, convert):
        return None if text == "?" else convert(text)

    values = {
        "age": known(g["age"], int),
        "sex": known(g["sex"], str),
        "complaints": known(g["complaints"], lambda t: t.split(",")),
        "duration": known(g["duration"], int),
        "temperature": known(g["temperature"], float),
    }
    values.update({s.id: SIGN_VALUES[g[s.id]] for s in pack.danger_signs})
    return values


def format_record(values, pack):
    """{slot: value} -> record line. Missing or None values become "?"."""
    def number(value):
        if value is None:
            return "?"
        if not 0 <= int(value) <= 99:
            raise ValueError(f"{value} does not fit in a case record")
        return str(int(value))

    temperature = values.get("temperature")
    if temperature is not None and not 30.0 <= temperature <= 49.9:
        raise ValueError(f"temperature {temperature} does not fit in a case record")
    complaints = values.get("complaints") or []
    unknown_codes = set(complaints) - set(pack.complaints)
    if unknown_codes or len(complaints) > pack.max_complaints:
        raise ValueError(f"complaints {complaints} do not fit in a case record")
    sign_text = {True: "1", False: "0", None: "?"}
    signs = " ".join(f"{s.code}{sign_text[values.get(s.id)]}" for s in pack.danger_signs)
    return (
        f"A{number(values.get('age'))} {values.get('sex') or '?'} | C:{','.join(complaints) or '?'} "
        f"D{number(values.get('duration'))} T{'?' if temperature is None else f'{temperature:.1f}'} | {signs}"
    )
