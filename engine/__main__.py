"""Command line for the rule engine.

  python -m engine decide "A24 F | C:FEV D2 T38.9 | DRK? VOM0 CNV0 LTH? CNN0" --lang ary-Latn
  python -m engine decide "<record>" --ask          # answer the follow-up questions here
  python -m engine grammar [--write]                # GBNF grammar for llama.cpp
  python -m engine check                            # rule pack, templates, grammar file
"""

import argparse
import sys

from . import (GRAMMAR_PATH, NEED_INFO, Case, check, decide, format_record, gbnf, load_pack,
               load_templates, question, render)


def ask(q):
    print(f"\n{q['text']}")
    if q["kind"] == "months":
        raw = input(f"  months (blank = {q['options'][0]['label']}): ").strip()
        return int(raw) if raw.isdigit() else None
    for i, option in enumerate(q["options"], 1):
        print(f"  {i}. {option['label']}")
    while True:
        raw = input("  > ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(q["options"]):
            return q["options"][int(raw) - 1]["value"]


def run_decide(args, pack, templates):
    t = templates[args.lang]
    case = Case.from_record(args.record, pack, args.confidence)
    for slot, value in args.answer:
        case.answer(slot, value)
    decision = decide(case, pack)
    while decision.outcome == NEED_INFO and args.ask:
        for slot in decision.questions:
            try:
                case.answer(slot, ask(question(slot, t)))
            except EOFError:
                print("\nstopped: no more answers")
                return 1
        decision = decide(case, pack)
    print(f"\nrecord   {format_record(case.values(), pack)}")
    print(f"outcome  {decision.outcome}")
    if decision.outcome == NEED_INFO:
        for slot in decision.questions:
            q = question(slot, t)
            print(f"ask      {q['text']}  [{' / '.join(o['label'] for o in q['options'])}]")
        return 0
    message = render(decision, t)
    print(f"message  {message['text']}")
    for warning in message["warnings"]:
        print(f"warning  {warning}")
    if decision.pending:
        print(f"pending  {', '.join(decision.pending)} (check while preparing the referral)")
    if decision.cite:
        print(f"source   {decision.cite}")
    return 0


def main():
    parser = argparse.ArgumentParser(prog="python -m engine", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("decide", help="decide from a case record")
    d.add_argument("record")
    d.add_argument("--lang", default="en")
    d.add_argument("--confidence", type=float, default=None,
                   help="model confidence for every slot (default: none, so absent signs are confirmed)")
    d.add_argument("--ask", action="store_true", help="ask the follow-up questions interactively")
    d.add_argument("--answer", action="append", default=[], metavar="SLOT=VALUE",
                   help="a health worker answer, e.g. vomits_everything=absent or age=24 (repeatable)")
    g = sub.add_parser("grammar", help="print the GBNF grammar for the case record")
    g.add_argument("--write", action="store_true", help=f"write it to {GRAMMAR_PATH.name}")
    sub.add_parser("check", help="check the rule pack, templates and grammar file")
    args = parser.parse_args()

    pack, templates = load_pack(), load_templates()
    if args.cmd == "decide":
        if args.lang not in templates:
            parser.error(f"--lang must be one of {', '.join(sorted(templates))}")
        answers = []
        for item in args.answer:
            slot, _, value = item.partition("=")
            if slot not in ["age", *pack.sign_ids]:
                parser.error(f"--answer: unknown slot {slot!r}")
            if value.isdigit():
                answers.append((slot, int(value)))
            elif value in ("present", "absent", "not_sure"):
                answers.append((slot, value))
            else:
                parser.error(f"--answer: {item!r} needs present, absent, not_sure or a number")
        args.answer = answers
        return run_decide(args, pack, templates)
    if args.cmd == "grammar":
        if args.write:
            GRAMMAR_PATH.write_text(gbnf(pack), encoding="utf-8")
            print(f"wrote {GRAMMAR_PATH}")
        else:
            print(gbnf(pack), end="")
        return 0
    problems = check(templates, pack)
    if not GRAMMAR_PATH.exists() or GRAMMAR_PATH.read_text(encoding="utf-8") != gbnf(pack):
        problems.append(f"{GRAMMAR_PATH.name} is out of date: run python -m engine grammar --write")
    for problem in problems:
        print(problem)
    drafts = [lang for lang, t in templates.items() if t.get("status") == "draft"]
    print(f"{pack.id} {pack.version}: {len(pack.danger_signs)} danger signs, languages {', '.join(sorted(templates))}"
          + (f" (drafts needing review: {', '.join(drafts)})" if drafts else ""))
    print("OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
