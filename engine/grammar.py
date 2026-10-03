"""GBNF grammar for the case record, generated from the rule pack.

llama.cpp uses it to constrain decoding, so the model can only write a valid record.
Regenerate after changing rules/danger_signs.yaml: python -m engine grammar --write
"""

from .rulepack import RULES_DIR

GRAMMAR_PATH = RULES_DIR / "record.gbnf"


def gbnf(pack):
    complaint = " | ".join(f'"{code}"' for code in pack.complaints)
    complaints = "complaint" + ' ("," complaint)?' * (pack.max_complaints - 1)
    signs = ' " " '.join(f'"{s.code}" sign' for s in pack.danger_signs)
    return "\n".join([
        f"# Case record for {pack.id} {pack.version}. Generated from rules/danger_signs.yaml",
        "# by `python -m engine grammar --write`; edit the YAML, not this file.",
        'root        ::= "A" number " " sex " | C:" complaints " D" number " T" temperature " | " signs',
        'number      ::= [0-9] | [1-9] [0-9] | "?"',
        'sex         ::= "M" | "F" | "?"',
        f'complaints  ::= {complaints} | "?"',
        f"complaint   ::= {complaint}",
        'temperature ::= [34] [0-9] "." [0-9] | "?"',
        f"signs       ::= {signs}",
        'sign        ::= "1" | "0" | "?"',
        "",
    ])
