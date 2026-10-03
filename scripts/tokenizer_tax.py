#!/usr/bin/env python3
"""Measure the tokeniser tax: how many more tokens a language needs than English
for the same content, for each candidate on-device model.

Parallel data (fetch it first with scripts/fetch_data.py):
  FLORES-200 devtest, 1,012 sentences: English, French, MSA, Darija (Arabic script),
      Swahili, Central Atlas Tamazight (Tifinagh)
  DODa sentences, 48,818 rows: English, Darija in Arabizi, Darija in Arabic script

Premium = total tokens in the language / total tokens for the same English sentences.

Writes:
  data/results/tokenizer_tax.csv               every model x language
  docs/tokenizer_tax.md                        table view and caveats
  docs/figures/tokenizer_tax.png               headline: the tax per language
  docs/figures/tokenizer_tax_models.png        model choice: Darija and Swahili per model
"""

import csv
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from tokenizers import Tokenizer  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_data import RAW, TOKENIZERS  # noqa: E402
from progress import Progress  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "data" / "results"
FIGURES = ROOT / "docs" / "figures"

MODEL_LABELS = {
    "atlas-chat-2b": "Atlas-Chat 2B (Darija-tuned Gemma 2)",
    "gemma-4-e2b": "Gemma 4 E2B",
    "gemma-3-1b": "Gemma 3 1B",
    "qwen3.5-2b": "Qwen3.5 2B",
    "qwen3-1.7b": "Qwen3 1.7B",
    "llama-3.2-1b": "Llama 3.2 1B",
    "phi-4-mini": "Phi-4 mini",
    "lfm2.5-1.2b": "LFM2.5 1.2B",
    "smollm2-1.7b": "SmolLM2 1.7B",
}
# (key, label, dataset, column, one of Tiny Clinic's languages)
LANGUAGES = [
    ("fra", "French", "flores", "fra_Latn", False),
    ("arb", "Arabic (MSA)", "flores", "arb_Arab", False),
    ("ary_flores", "Darija, Arabic script (FLORES)", "flores", "ary_Arab", True),
    ("ary_doda_ar", "Darija, Arabic script (DODa)", "doda", "darija_ar", True),
    ("ary_doda_latn", "Darija, Arabizi (DODa)", "doda", "darija", True),
    ("swh", "Swahili", "flores", "swh_Latn", True),
    ("tzm", "Tamazight, Tifinagh", "flores", "tzm_Tfng", False),
]
# The three variants the model must read in the app; used to rank models.
TARGETS = ["ary_doda_latn", "ary_doda_ar", "swh"]

# Reference palette (dataviz skill), light mode.
SURFACE, INK, INK_2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, BASELINE = "#e1e0d9", "#c3c2b7"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]  # validated all-pairs, light
PX = 72 / 150  # one pixel in points at 150 dpi
plt.rcParams.update({"font.family": "sans-serif",
                     "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"]})
CHART_LABELS = {**MODEL_LABELS, "atlas-chat-2b": "Atlas-Chat 2B (Darija-tuned)"}


def load_data():
    flores = {}
    for lang in ["eng_Latn"] + [col for _, _, ds, col, _ in LANGUAGES if ds == "flores"]:
        path = RAW / "flores200" / "devtest" / f"{lang}.devtest"
        flores[lang] = path.read_text(encoding="utf-8").splitlines()
    with open(RAW / "doda" / "sentences.csv", encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if all(r[c].strip() for c in ("eng", "darija", "darija_ar"))]
    doda = {col: [r[col].strip() for r in rows] for col in ("eng", "darija", "darija_ar")}
    return {"flores": (flores, "eng_Latn"), "doda": (doda, "eng")}


def count_tokens(tokenizer, texts):
    return sum(len(enc.ids) for enc in tokenizer.encode_batch(texts, add_special_tokens=False))


def measure(data):
    rows = []
    bar = Progress("tokenizer-tax", total=len(TOKENIZERS), label="starting")
    for i, model in enumerate(TOKENIZERS):
        bar.update(i, model)
        tokenizer = Tokenizer.from_file(str(RAW / "tokenizers" / model / "tokenizer.json"))
        vocab = tokenizer.get_vocab_size()
        english = {ds: count_tokens(tokenizer, texts[eng]) for ds, (texts, eng) in data.items()}
        for key, label, ds, col, ours in LANGUAGES:
            texts, _ = data[ds]
            tokens = count_tokens(tokenizer, texts[col])
            rows.append({"model": model, "model_label": MODEL_LABELS[model], "vocab": vocab,
                         "language": key, "language_label": label, "dataset": ds,
                         "sentences": len(texts[col]), "tokens": tokens, "english_tokens": english[ds],
                         "premium": round(tokens / english[ds], 4), "tiny_clinic_language": ours})
    bar.finish(f"{len(TOKENIZERS)} tokenizers x {len(LANGUAGES)} languages")
    return rows


def write_csv(rows):
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / "tokenizer_tax.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def premiums(rows):
    """{model: {language: premium}}"""
    table = {}
    for r in rows:
        table.setdefault(r["model"], {})[r["language"]] = r["premium"]
    return table


def rank_models(table):
    return sorted(table, key=lambda m: statistics.mean(table[m][k] for k in TARGETS))


def style_axes(ax, xmax):
    ax.set_facecolor(SURFACE)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xlim(0.8, xmax)  # nothing is cheaper than English; start just below 1×
    ticks = list(range(1, int(xmax) + 1))
    ax.set_xticks(ticks, [f"{t}×" for t in ticks])
    ax.xaxis.grid(True, color=GRID, linewidth=PX)
    ax.yaxis.grid(False)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", length=0, colors=INK_2, labelsize=12, pad=10)
    ax.axvline(1, color=BASELINE, linewidth=2 * PX, zorder=1)


def header(fig, title, subtitle, source):
    fig.text(0.04, 0.935, title, fontsize=22, fontweight="bold", color=INK, va="baseline")
    fig.text(0.04, 0.89, subtitle, fontsize=13, color=INK_2, va="baseline")
    fig.text(0.04, 0.03, source, fontsize=10, color=MUTED, va="baseline")


def dot(ax, x, y, color, size=8.5):
    ax.plot([x], [y], "o", color=color, markersize=size, markeredgecolor=SURFACE,
            markeredgewidth=2 * PX * 1.5, zorder=4)


def chart_languages(table, n_flores, n_doda, path):
    """Each language: median model (dot) and best-to-worst range (line)."""
    langs = [(k, label, ours) for k, label, _, _, ours in LANGUAGES]
    stats = {k: (statistics.median(table[m][k] for m in table), min(table[m][k] for m in table),
                 max(table[m][k] for m in table)) for k, _, _ in langs}
    langs.sort(key=lambda l: stats[l[0]][0])
    order = [("eng", "English (reference)", False)] + langs
    stats["eng"] = (1.0, 1.0, 1.0)
    xmax = max(hi for _, _, hi in stats.values()) * 1.08

    fig = plt.figure(figsize=(12.8, 7.2), dpi=150, facecolor=SURFACE)
    ax = fig.add_axes([0.25, 0.125, 0.71, 0.655])
    style_axes(ax, xmax)
    for i, (key, label, ours) in enumerate(order):
        y = len(order) - 1 - i
        med, lo, hi = stats[key]
        color = SERIES[0] if ours else MUTED
        if hi > lo:
            ax.plot([lo, hi], [y, y], color=color, alpha=0.35, linewidth=4 * PX,
                    solid_capstyle="round", zorder=2)
        dot(ax, med, y, color)
        ax.text(med, y + 0.3, f"{med:.1f}×", ha="center", va="bottom", fontsize=12,
                color=INK if ours else INK_2, fontweight="bold" if ours else "normal")
    ax.set_yticks(range(len(order)), [label for _, label, _ in reversed(order)])
    ax.set_ylim(-0.6, len(order) - 0.2)
    for tick, (_, _, ours) in zip(ax.get_yticklabels(), reversed(order)):
        tick.set_color(INK if ours else INK_2)
    ax.legend(handles=[
        Line2D([], [], marker="o", linestyle="", color=SERIES[0], markersize=8, label="Tiny Clinic languages"),
        Line2D([], [], marker="o", linestyle="", color=MUTED, markersize=8, label="Other languages, for comparison"),
    ], loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, frameon=False, fontsize=12, labelcolor=INK_2,
        handletextpad=0.3, columnspacing=1.6, borderaxespad=0.2)
    header(fig, "Same sentence, more tokens: the tokeniser tax",
           f"Tokens needed relative to English for the same sentences, across {len(table)} small open models. "
           "Dot: median model. Line: best to worst model.",
           f"Sources: FLORES-200 devtest ({n_flores:,} sentences, CC-BY-SA 4.0); DODa Darija Open Dataset "
           f"({n_doda:,} sentences, CC BY-NC 4.0); tokenizers from Hugging Face.")
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def chart_models(table, rows, path):
    """Each model: Darija (Arabizi), Darija (Arabic script) and Swahili premiums."""
    vocab = {r["model"]: r["vocab"] for r in rows}
    series = [("ary_doda_latn", "Darija, Arabizi"), ("ary_doda_ar", "Darija, Arabic script"), ("swh", "Swahili")]
    offsets = [0.24, 0.0, -0.24]  # dodge the three series so equal values never hide each other
    order = rank_models(table)
    xmax = max(table[m][k] for m in order for k, _ in series) * 1.08

    fig = plt.figure(figsize=(12.8, 7.2), dpi=150, facecolor=SURFACE)
    ax = fig.add_axes([0.31, 0.125, 0.65, 0.655])
    style_axes(ax, xmax)
    for i, model in enumerate(order):
        y = len(order) - 1 - i
        for (key, _), color, dy in zip(series, SERIES, offsets):
            dot(ax, table[model][key], y + dy, color, size=8)
    ax.set_yticks(range(len(order)),
                  [f"{CHART_LABELS[m]}  ·  {vocab[m] // 1000}k vocab" for m in reversed(order)])
    ax.set_ylim(-0.6, len(order) - 0.4)
    ax.legend(handles=[Line2D([], [], marker="o", linestyle="", color=c, markersize=8, label=name)
                       for (_, name), c in zip(series, SERIES)],
              loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, frameon=False, fontsize=12,
              labelcolor=INK_2, handletextpad=0.3, columnspacing=1.6, borderaxespad=0.2)
    header(fig, "Which small model pays the least tax on Darija and Swahili?",
           "Tokens relative to English for the same sentences. Lower is cheaper and faster on the phone. "
           "Sorted by the average of the three.",
           "Sources: DODa Darija Open Dataset (CC BY-NC 4.0) for both Darija scripts; FLORES-200 devtest (CC-BY-SA 4.0) "
           "for Swahili. Full table: docs/tokenizer_tax.md.")
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def write_markdown(table, rows, n_flores, n_doda, path):
    vocab = {r["model"]: r["vocab"] for r in rows}
    order = rank_models(table)
    keys = [k for k, *_ in LANGUAGES]
    short = {"fra": "French", "arb": "MSA", "ary_flores": "Darija ar (FLORES)", "ary_doda_ar": "Darija ar (DODa)",
             "ary_doda_latn": "Darija Arabizi (DODa)", "swh": "Swahili", "tzm": "Tamazight"}
    lines = [
        "# Tokeniser tax",
        "",
        "Tokens a language needs relative to English for the same sentences (English = 1.00).",
        "Generated by `scripts/tokenizer_tax.py`; raw counts in `data/results/tokenizer_tax.csv`.",
        "",
        "![The tokeniser tax per language](figures/tokenizer_tax.png)",
        "",
        "![Darija and Swahili premium per model](figures/tokenizer_tax_models.png)",
        "",
        "Models are sorted by the average of Darija Arabizi, Darija Arabic script (both DODa) and Swahili.",
        "",
        "| Model | Vocab | " + " | ".join(short[k] for k in keys) + " | Avg (ours) |",
        "|---|---:|" + "---:|" * (len(keys) + 1),
    ]
    for m in order:
        avg = statistics.mean(table[m][k] for k in TARGETS)
        lines.append(f"| {MODEL_LABELS[m]} | {vocab[m]:,} | " + " | ".join(f"{table[m][k]:.2f}" for k in keys)
                     + f" | **{avg:.2f}** |")
    twins = [(a, b) for i, a in enumerate(order) for b in order[i + 1:] if table[a] == table[b]]
    lines += [f"\n{MODEL_LABELS[a]} and {MODEL_LABELS[b]} give identical counts on every language: "
              "they share a tokenizer." for a, b in twins]
    lines += [
        "",
        "## Data and what it does not cover",
        "",
        f"- **FLORES-200 devtest** (Meta, CC-BY-SA 4.0): {n_flores:,} sentences, professionally translated from "
        "English Wikipedia-style text. Formal register; no clinical or spoken language.",
        f"- **DODa sentences** (Darija Open Dataset, CC BY-NC 4.0): {n_doda:,} short conversational sentences with "
        "English, Arabizi and Arabic-script versions. Arabizi spelling varies a lot between writers; DODa uses "
        "one convention (3 = ع, 7 = ح, 9 = ق), so real notes may tokenise differently. The license is "
        "non-commercial, so DODa is used only to count tokens, never as training data.",
        "- FLORES and DODa are different sentences, so compare premiums within a dataset, not across them.",
        "- Neither covers health-worker notes, French code-switching inside Darija, or typos.",
        "- A premium measures cost (tokens, latency, context), not how well the model understands the language.",
        "- Gemma 3 1B and Llama 3.2 1B are gated upstream, so their tokenizers come from unsloth's ungated "
        "mirrors (`unsloth/gemma-3-1b-it`, `unsloth/Llama-3.2-1B-Instruct`). The rest come from the original repos.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    data = load_data()
    n_flores = len(data["flores"][0]["eng_Latn"])
    n_doda = len(data["doda"][0]["eng"])
    rows = measure(data)
    csv_path = write_csv(rows)
    table = premiums(rows)
    chart_languages(table, n_flores, n_doda, FIGURES / "tokenizer_tax.png")
    chart_models(table, rows, FIGURES / "tokenizer_tax_models.png")
    write_markdown(table, rows, n_flores, n_doda, ROOT / "docs" / "tokenizer_tax.md")
    print(f"wrote {csv_path.relative_to(ROOT)}, docs/tokenizer_tax.md, docs/figures/*.png\n")
    print((ROOT / "docs" / "tokenizer_tax.md").read_text().split("\n## ")[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
