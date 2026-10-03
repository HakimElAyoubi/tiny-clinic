# Tiny Clinic

Offline referral and documentation support for community health workers, in Swahili, on a phone they already have.

Built for the **Hack-Nation × World Bank Small AI for Development Hackathon**, Track A: Health (3–4 October 2026).

## The problem

Community health workers triage sick children with the WHO IMCI paper chart. The charts wear out, steps get skipped, and record-keeping eats the time they have for each patient. Connectivity is weak or absent, and phones are low-end.

AI could help, but small models handle low-resource languages poorly. Tokenisers are trained mostly on English, so the same sentence in Swahili costs several times more tokens. On a small, offline model, that means slower answers, more battery drain and worse reasoning, all in the language that needs support most. We call this the **tokeniser tax**.

## How it works

Tiny Clinic splits the work so the small model never reasons about medicine:

1. **The model understands.** A small quantised model reads the health worker's free-text note (Swahili, English or a mix) and fills typed slots in a compact case record. Grammar-constrained decoding guarantees the output is always valid.
2. **The engine decides.** A deterministic rule engine runs the IMCI protocol, compiled into rules. It is exact and auditable, and every result cites the protocol step behind it.
3. **Templates speak.** Questions and advice come from a fixed list of pre-translated templates. The model never writes medical advice.

If information is missing, unclear or contradictory, the result is **UNSURE: ask a clinician**. The health worker always makes the final call.

Each case is saved on the phone as one short, de-identified line and sent to DHIS2 by SMS when a signal appears (store-and-forward).

## Status

Work in progress. See the build order below.

## Layout

| Folder | What goes there |
|---|---|
| `scripts/` | Tokeniser-tax measurement on FLORES-200, setup helpers |
| `rules/` | IMCI rule packs (cough/breathing, fever, diarrhoea; 2 months to 5 years) |
| `engine/` | Rule interpreter and missing-slot question loop |
| `extract/` | Small-model slot extraction with constrained decoding |
| `app/` | Web UI served locally on the device |
| `eval/` | Test cases, baselines, metrics |
| `docs/` | Pitch notes, video script, data statement |
| `data/` | Small committed data; large downloads are ignored |

Model weights are side-loaded and never committed (`models/` is git-ignored).

## Build order

1. Tokeniser-tax measurement script (first chart)
2. Case-record grammar and vocabulary
3. Hand-encoded IMCI rule pack
4. Engine plus missing-slot question loop, with the UNSURE outcome
5. Model extraction with constrained decoding
6. Evaluation: Tiny Clinic vs. a naive small model vs. small model + plain JSON schema
7. SMS payload, DHIS2 mapping, UI polish

## Data

Every dataset is listed with source, license, size and **what it does not cover**.

| Dataset | Use | License | Size | Does not cover |
|---|---|---|---|---|
| FLORES-200 (Meta) | Tokeniser-tax measurement | CC-BY-SA 4.0 | TBD | Clinical vocabulary; spoken or informal text |
| World Bank Service Delivery Indicators | Problem evidence | TBD | TBD | TBD |
| WHO Global Health Observatory | Health-worker density | TBD | TBD | TBD |
| GSMA Mobile Gender Gap Report | Device ownership | TBD | TBD | TBD |
| Synthetic IMCI vignettes (ours, labelled synthetic) | Evaluation | MIT | TBD | Real speech, typos, dialects, comorbidities |

## Safety and privacy

- Referral and documentation support, not diagnosis. Every output traces to an IMCI protocol step.
- The model only fills slots. All advice comes from a fixed, reviewed template list.
- An UNSURE outcome sends the case to a person instead of guessing.
- Case records hold no names, only a local ID. Data is encrypted on the phone, and nothing identifying is sent over SMS.

## License

MIT
