#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Re-run normalise() over model output without spending an API call.

Two sources:

    # an existing predictions file: treat each line as the raw model reply
    python3 app/replay.py --from-predictions results/dev_predictions_run1.jsonl

    # the raw reply cache: every case must hit, misses fall back (no network)
    python3 app/replay.py --from-cache

The output is a submission file, so an engine change can be rescored in
seconds. Predictions are only sent through dna.visible(); ground truth and
simulation facts never enter normalise().
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
SIMSET = os.path.join(PROJECT, "DNA_Digital_Security_Assistant_SimSet_v2.0.1")
DEFAULT_CASES = os.path.join(SIMSET, "data", "dev", "cases.jsonl")
DEFAULT_OUT = os.path.join(PROJECT, "results", "dev_predictions_replay.jsonl")

sys.path.insert(0, HERE)

import dna  # noqa: E402


def load_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_trace(fh, case_id, trace):
    if fh is not None:
        fh.write(json.dumps(dict({"case_id": case_id}, **trace), ensure_ascii=False) + "\n")


def replay_predictions(cases, pred_path, trace_fh):
    """Feed each old prediction back through normalise(), as if it were a fresh reply."""
    preds = {}
    for p in load_jsonl(pred_path):
        preds[p.get("case_id")] = p
    out = []
    fallback = missing = 0
    rules_fired = 0
    for case in cases:
        trace = {"raw_text": None, "raw": None, "rules": [],
                 "meta": {"source": "predictions", "path": pred_path},
                 "fallback": False, "error": None}
        pred = preds.get(case["case_id"])
        if pred is None:
            missing += 1
            fallback += 1
            trace.update(fallback=True, error="missing prediction")
            answer = dna.fallback(case, "missing prediction")
        else:
            trace["raw"] = pred
            trace["raw_text"] = json.dumps(pred, ensure_ascii=False)
            answer = dna.normalise(dna.visible(case), pred, trace["rules"])
        rules_fired += len(trace["rules"])
        out.append(answer)
        write_trace(trace_fh, case["case_id"], trace)
    return out, {"fallback": fallback, "missing": missing, "rules_fired": rules_fired}


def replay_cache(cases, trace_fh):
    """Call dna.run with cache_only=True: a miss is a rules fallback, never a request."""
    out = []
    fallback = misses = hits = rules_fired = 0
    for case in cases:
        answer, trace = dna.run(case, cache_only=True)
        meta = trace.get("meta") or {}
        hits += bool(meta.get("cached"))
        misses += trace.get("error") == "cache miss"
        fallback += bool(trace.get("fallback"))
        rules_fired += len(trace.get("rules") or [])
        out.append(answer)
        write_trace(trace_fh, case["case_id"], trace)
    return out, {"fallback": fallback, "cache_hits": hits, "cache_misses": misses,
                 "rules_fired": rules_fired}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", default=DEFAULT_CASES, help="cases with ground truth")
    ap.add_argument("--out", default=DEFAULT_OUT, help="replayed predictions (JSONL)")
    ap.add_argument("--trace", default=None, help="optional sidecar trace JSONL")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-predictions", metavar="PATH", help="existing predictions to replay")
    src.add_argument("--from-cache", action="store_true", help="replay the raw model reply cache")
    a = ap.parse_args()

    cases = load_jsonl(a.cases)
    if not cases:
        sys.exit("no cases in %s" % a.cases)

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    trace_fh = open(a.trace, "w", encoding="utf-8") if a.trace else None
    try:
        if a.from_predictions:
            out, stats = replay_predictions(cases, a.from_predictions, trace_fh)
            source = "predictions %s" % a.from_predictions
        else:
            out, stats = replay_cache(cases, trace_fh)
            source = "raw cache (offline)"
    finally:
        if trace_fh is not None:
            trace_fh.close()

    with open(a.out, "w", encoding="utf-8") as fh:
        for answer in out:
            fh.write(json.dumps(answer, ensure_ascii=False) + "\n")

    extra = "  ".join("%s %d" % kv for kv in stats.items())
    print("replayed %d cases from %s" % (len(out), source))
    print("  %s" % extra)
    print("  wrote %s" % a.out)
    if a.trace:
        print("  wrote %s" % a.trace)
    return 0


if __name__ == "__main__":
    sys.exit(main())
