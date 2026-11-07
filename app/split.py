#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic held-out split of the dev cases by scenario_family.

    python3 app/split.py

Holds out 8 whole families, stratified so every journey is represented, and
guarantees at least one held-out family with benign controls and one with
twins. The tune and holdout files are the original dev lines, unchanged, so
the evaluator sees exactly the cases it shipped.

Held-out families are locked: score them at gates only, never tune on them.
"""

import json
import os
import random
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
SIMSET = os.path.join(PROJECT, "DNA_Digital_Security_Assistant_SimSet_v2.0.1")
DEV_CASES = os.path.join(SIMSET, "data", "dev", "cases.jsonl")
OUT_DIR = os.path.join(PROJECT, "data", "splits")

SEED = 20261107          # fixed: an event date, and a record of this split
HOLDOUT_FAMILIES = 8     # ~8 whole families, as the roadmap asks


def load_dev():
    """Return (cases, raw_lines) in file order."""
    cases, lines = [], []
    with open(DEV_CASES, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            lines.append(line if line.endswith("\n") else line + "\n")
            cases.append(json.loads(line))
    return cases, lines


def family_facts(cases):
    """Per family: journey, size, and whether it owns benign/twin cases."""
    facts = {}
    for case in cases:
        fam = case["scenario_family"]
        gt = case.get("ground_truth") or {}
        f = facts.setdefault(fam, {"journey": case["journey"], "cases": 0,
                                   "benign": False, "twin": False})
        f["cases"] += 1
        f["benign"] = f["benign"] or bool(gt.get("is_benign_control"))
        f["twin"] = f["twin"] or bool(gt.get("twin_group"))
    return facts


def quotas(facts):
    """Hold out at least one family per journey, then the largest journeys.

    Deterministic: ties break on the journey name, so the split does not move
    when the interpreter, hash seed or file order changes.
    """
    by_journey = defaultdict(list)
    for fam, f in facts.items():
        by_journey[f["journey"]].append(fam)
    if HOLDOUT_FAMILIES < len(by_journey):
        sys.exit("cannot hold out %d families and cover %d journeys"
                 % (HOLDOUT_FAMILIES, len(by_journey)))
    out = {j: 1 for j in by_journey}
    order = sorted(by_journey, key=lambda j: (-len(by_journey[j]), j))
    for i in range(HOLDOUT_FAMILIES - len(out)):
        out[order[i % len(order)]] += 1
    return out


def choose(facts, quota):
    """Pick whole families, retrying deterministically until the constraints hold."""
    by_journey = defaultdict(list)
    for fam in sorted(facts):
        by_journey[facts[fam]["journey"]].append(fam)
    for attempt in range(500):
        rng = random.Random(SEED + attempt)
        chosen = set()
        for journey in sorted(by_journey):
            pool = list(by_journey[journey])
            rng.shuffle(pool)
            chosen.update(pool[:quota[journey]])
        if (any(facts[f]["benign"] for f in chosen)
                and any(facts[f]["twin"] for f in chosen)):
            return chosen, attempt
    sys.exit("no stratified split satisfies the benign/twin constraints")


def counts(cases):
    by_journey = defaultdict(int)
    benign = twin = 0
    for case in cases:
        by_journey[case["journey"]] += 1
        gt = case.get("ground_truth") or {}
        benign += bool(gt.get("is_benign_control"))
        twin += bool(gt.get("twin_group"))
    return {"cases": len(cases), "by_journey": dict(sorted(by_journey.items())),
            "benign_controls": benign, "twin_cases": twin}


def write_jsonl(path, lines):
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(lines)


def main():
    cases, lines = load_dev()
    if not cases:
        sys.exit("no dev cases in %s" % DEV_CASES)
    facts = family_facts(cases)
    quota = quotas(facts)
    chosen, attempt = choose(facts, quota)

    tune_lines, holdout_lines = [], []
    tune_cases, holdout_cases = [], []
    for case, line in zip(cases, lines):
        if case["scenario_family"] in chosen:
            holdout_lines.append(line)
            holdout_cases.append(case)
        else:
            tune_lines.append(line)
            tune_cases.append(case)

    os.makedirs(OUT_DIR, exist_ok=True)
    write_jsonl(os.path.join(OUT_DIR, "tune.jsonl"), tune_lines)
    write_jsonl(os.path.join(OUT_DIR, "holdout.jsonl"), holdout_lines)

    meta = {
        "seed": SEED,
        "attempt": attempt,
        "holdout_families": sorted(chosen),
        "quotas": dict(sorted(quota.items())),
        "family_count": len(facts),
        "counts": {"tune": counts(tune_cases), "holdout": counts(holdout_cases)},
    }
    with open(os.path.join(OUT_DIR, "split.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")

    print("split seed %d: held out %d of %d families (%d cases); tune %d cases"
          % (SEED, len(chosen), len(facts), len(holdout_cases), len(tune_cases)))
    print("")
    print("  %-20s %8s %6s" % ("journey", "holdout", "tune"))
    for journey in sorted(set(c["journey"] for c in cases)):
        print("  %-20s %8d %6d" % (
            journey,
            meta["counts"]["holdout"]["by_journey"].get(journey, 0),
            meta["counts"]["tune"]["by_journey"].get(journey, 0)))
    print("")
    print("  held-out families:")
    for fam in sorted(chosen):
        f = facts[fam]
        marks = "".join([" benign" if f["benign"] else "", " twin" if f["twin"] else ""])
        print("    %-32s %-18s %2d cases%s" % (fam, f["journey"], f["cases"], marks))
    print("")
    print("  wrote %s" % os.path.join(OUT_DIR, "tune.jsonl"))
    print("  wrote %s" % os.path.join(OUT_DIR, "holdout.jsonl"))
    print("  wrote %s" % os.path.join(OUT_DIR, "split.json"))
    print("  Holdout is locked: gates only, never tune on it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
