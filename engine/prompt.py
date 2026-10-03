"""The extraction prompt: instructions and worked examples from rules/extraction.yaml.

The system prompt never changes between notes, so the phone keeps its KV cache and only
pays for the note itself.
"""

from pathlib import Path

import yaml

from .rulepack import RULES_DIR

EXTRACTION_PATH = RULES_DIR / "extraction.yaml"
SIGN_LABELS = {  # English labels for the model; the app's own wording lives in rules/templates/
    "not_able_to_drink": "not able to drink or breastfeed",
    "vomits_everything": "vomits everything",
    "convulsions": "has had convulsions",
    "lethargic_or_unconscious": "lethargic or unconscious",
    "convulsing_now": "convulsing now",
}
COMPLAINT_LABELS = {
    "CGH": "cough or difficult breathing",
    "DIA": "diarrhoea",
    "FEV": "fever",
    "EAR": "ear problem",
    "OTH": "other",
}


def load_extraction(path=EXTRACTION_PATH):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def system_prompt(pack, extraction=None):
    extraction = extraction or load_extraction()
    complaints = ", ".join(f"{code} {COMPLAINT_LABELS[code]}" for code in pack.complaints)
    signs = "\n".join(f"{s.code} {SIGN_LABELS[s.id]}" for s in pack.danger_signs)
    text = extraction["instructions"].format(complaints=complaints, signs=signs).strip()
    examples = "\n\n".join(f"Note: {e['note']}\nRecord: {e['record']}" for e in extraction["examples"])
    return f"{text}\n\nExamples:\n\n{examples}"


def user_message(note):
    return f"Note: {note.strip()}"
