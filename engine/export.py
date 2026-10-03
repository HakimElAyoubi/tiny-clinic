"""Bundle the rules for the phone app: one JSON asset, plus the shared test vectors.

    python -m engine export

android/app/src/main/assets/tinyclinic_rules.json   rule pack, templates, grammar, prompt
android/app/src/test/resources/cases.json            rules/tests/cases.yaml, for the Kotlin tests
"""

import json
from pathlib import Path

import yaml

from .grammar import gbnf
from .prompt import system_prompt, user_message
from .rulepack import RULES_DIR, load_pack, load_templates

ANDROID_APP = RULES_DIR.parent / "android" / "app" / "src"
ASSET_PATH = ANDROID_APP / "main" / "assets" / "tinyclinic_rules.json"
VECTORS_PATH = ANDROID_APP / "test" / "resources" / "cases.json"


def bundle():
    pack = load_pack()
    raw_pack = yaml.safe_load((RULES_DIR / "danger_signs.yaml").read_text(encoding="utf-8"))
    return {
        "pack": raw_pack,
        "templates": load_templates(),
        "grammar": gbnf(pack),
        "prompt": {"system": system_prompt(pack), "user_prefix": user_message("")},
    }


def vectors():
    return yaml.safe_load((RULES_DIR / "tests" / "cases.yaml").read_text(encoding="utf-8"))


def render(data):
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"


def write():
    for path, data in ((ASSET_PATH, bundle()), (VECTORS_PATH, vectors())):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(data), encoding="utf-8")
    return [ASSET_PATH, VECTORS_PATH]


def is_current():
    return all(path.exists() and path.read_text(encoding="utf-8") == render(data)
               for path, data in ((ASSET_PATH, bundle()), (VECTORS_PATH, vectors())))
