"""The compact case record and its grammar."""

import pytest

from engine import GRAMMAR_PATH, format_record, gbnf, load_pack, parse

PACK = load_pack()
VALID = [
    "A24 F | C:FEV D2 T38.9 | DRK0 VOM1 CNV? LTH0 CNN0",
    "A? ? | C:? D? T? | DRK? VOM? CNV? LTH? CNN?",
    "A2 M | C:CGH,FEV,DIA,EAR D14 T40.1 | DRK1 VOM1 CNV1 LTH1 CNN1",
    "A59 M | C:OTH D0 T36.5 | DRK0 VOM0 CNV0 LTH0 CNN0",
]
INVALID = [
    "",
    "the child is sick",
    "A24 F | C:FEV D2 T38.9 | DRK0 VOM1 CNV? LTH0",            # a sign missing
    "A24 F | C:FEV D2 T38.9 | VOM1 DRK0 CNV? LTH0 CNN0",       # signs out of order
    "A24 F | C:XYZ D2 T38.9 | DRK0 VOM1 CNV? LTH0 CNN0",       # unknown complaint
    "A124 F | C:FEV D2 T38.9 | DRK0 VOM1 CNV? LTH0 CNN0",      # age over 99
    "A05 F | C:FEV D2 T38.9 | DRK0 VOM1 CNV? LTH0 CNN0",       # leading zero
    "A24 F | C:FEV D2 T389 | DRK0 VOM1 CNV? LTH0 CNN0",        # no decimal point
    "A24 F | C:FEV,FEV,FEV,FEV,FEV D2 T38.9 | DRK0 VOM1 CNV? LTH0 CNN0",  # too many complaints
    "A24 F | C:FEV D2 T38.9 | DRK2 VOM1 CNV? LTH0 CNN0",       # bad sign value
]


@pytest.mark.parametrize("line", VALID)
def test_round_trip(line):
    assert format_record(parse(line, PACK), PACK) == line


@pytest.mark.parametrize("line", INVALID)
def test_rejects(line):
    with pytest.raises(ValueError):
        parse(line, PACK)


def test_parse_values():
    values = parse(VALID[0], PACK)
    assert values["age"] == 24 and values["sex"] == "F" and values["complaints"] == ["FEV"]
    assert values["duration"] == 2 and values["temperature"] == 38.9
    assert [values[s] for s in PACK.sign_ids] == [False, True, None, False, False]


def test_format_refuses_values_that_do_not_fit():
    with pytest.raises(ValueError):
        format_record({"age": 150}, PACK)
    with pytest.raises(ValueError):
        format_record({"temperature": 51.0}, PACK)


def test_grammar_file_is_current():
    assert GRAMMAR_PATH.read_text(encoding="utf-8") == gbnf(PACK), "run: python -m engine grammar --write"


def test_grammar_names_every_code():
    grammar = gbnf(PACK)
    for code in [*PACK.complaints, *(s.code for s in PACK.danger_signs)]:
        assert f'"{code}"' in grammar
