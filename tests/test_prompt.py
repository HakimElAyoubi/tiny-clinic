"""The extraction prompt and its worked examples."""

from engine import load_pack, parse
from engine.export import is_current
from engine.prompt import load_extraction, system_prompt, user_message

PACK = load_pack()


def test_examples_are_valid_records():
    for example in load_extraction()["examples"]:
        parse(example["record"], PACK)  # raises if the grammar would not allow it


def test_prompt_names_every_code():
    prompt = system_prompt(PACK)
    for code in [*PACK.complaints, *(s.code for s in PACK.danger_signs)]:
        assert code in prompt
    assert "{" not in prompt.split("Examples:")[0]  # every placeholder filled


def test_user_message():
    assert user_message("  lbent fiha skhana ") == "Note: lbent fiha skhana"


def test_android_bundle_is_current():
    assert is_current(), "run: python -m engine export"
