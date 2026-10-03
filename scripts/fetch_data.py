#!/usr/bin/env python3
"""Download the data for the tokeniser-tax measurement into data/raw/ (git-ignored).

- FLORES-200 devtest (Meta, CC-BY-SA 4.0), selected languages only
- DODa sentences (Darija Open Dataset, CC BY-NC 4.0): Arabizi, Arabic script, English
- tokenizer.json of each candidate on-device model (Hugging Face, ungated repos)

Progress: data/progress.nosync/fetch-data.txt (live page: python3 scripts/progress.py serve).
"""

import io
import sys
import tarfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from progress import Progress  # noqa: E402

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
FLORES_URL = "https://dl.fbaipublicfiles.com/nllb/flores200_dataset.tar.gz"
FLORES_LANGS = [
    "eng_Latn",  # English
    "fra_Latn",  # French
    "arb_Arab",  # Modern Standard Arabic
    "ary_Arab",  # Moroccan Arabic (Darija), Arabic script
    "swh_Latn",  # Swahili
    "tzm_Tfng",  # Central Atlas Tamazight, Tifinagh
]
DODA_URL = "https://raw.githubusercontent.com/darija-open-dataset/dataset/main/sentences/sentences.csv"
# Candidate on-device models; repos are ungated (unsloth mirrors where the original is gated).
TOKENIZERS = {
    "atlas-chat-2b": "MBZUAI-Paris/Atlas-Chat-2B",
    "gemma-4-e2b": "google/gemma-4-E2B-it",
    "gemma-3-1b": "unsloth/gemma-3-1b-it",
    "qwen3.5-2b": "Qwen/Qwen3.5-2B",
    "qwen3-1.7b": "Qwen/Qwen3-1.7B",
    "llama-3.2-1b": "unsloth/Llama-3.2-1B-Instruct",
    "phi-4-mini": "microsoft/Phi-4-mini-instruct",
    "lfm2.5-1.2b": "LiquidAI/LFM2.5-1.2B-Instruct",
    "smollm2-1.7b": "HuggingFaceTB/SmolLM2-1.7B-Instruct",
}


def get(url):
    with urllib.request.urlopen(url, timeout=120) as resp:
        return resp.read()


def fetch_flores():
    out = RAW / "flores200"
    if all((out / "devtest" / f"{lang}.devtest").exists() for lang in FLORES_LANGS):
        return
    with tarfile.open(fileobj=io.BytesIO(get(FLORES_URL)), mode="r:gz") as tar:
        for member in tar.getmembers():
            name = Path(member.name)
            if name.suffix in (".dev", ".devtest") and name.stem in FLORES_LANGS:
                target = out / name.parent.name / name.name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(tar.extractfile(member).read())
    missing = [l for l in FLORES_LANGS if not (out / "devtest" / f"{l}.devtest").exists()]
    if missing:
        raise RuntimeError(f"FLORES-200 tarball has no devtest for {missing}")


def fetch_doda():
    target = RAW / "doda" / "sentences.csv"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(get(DODA_URL))


def fetch_tokenizer(name, repo):
    folder = RAW / "tokenizers" / name
    folder.mkdir(parents=True, exist_ok=True)
    for filename in ("tokenizer.json", "tokenizer_config.json"):
        target = folder / filename
        if not target.exists():
            target.write_bytes(get(f"https://huggingface.co/{repo}/resolve/main/{filename}"))
    (folder / "SOURCE").write_text(f"https://huggingface.co/{repo}\n")


def main():
    tasks = [("FLORES-200", fetch_flores), ("DODa sentences", fetch_doda)]
    tasks += [(f"tokenizer {name}", lambda n=name, r=repo: fetch_tokenizer(n, r)) for name, repo in TOKENIZERS.items()]
    bar = Progress("fetch-data", total=len(tasks), label="starting")
    failed = []
    for i, (label, task) in enumerate(tasks):
        bar.update(i, label)
        try:
            task()
        except Exception as exc:  # keep going; report every failure at the end
            failed.append(f"{label}: {exc}")
            print(f"FAILED {label}: {exc}", file=sys.stderr)
    if failed:
        bar.fail(f"{len(failed)} failed: " + "; ".join(failed))
        return 1
    bar.finish(f"FLORES-200 ({len(FLORES_LANGS)} languages), DODa, {len(TOKENIZERS)} tokenizers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
