#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch runner: one answer per input case, written as JSONL.

    python3 app/batch.py --inputs DNA_.../data/test/inputs.jsonl --out test_predictions.jsonl
    python3 app/batch.py --inputs DNA_.../data/dev/cases.jsonl --out dev_predictions.jsonl --limit 40
    python3 app/batch.py ... --no-llm          # rules baseline, no API calls
    python3 app/batch.py ... --resume          # keep answers already in --out
    python3 app/batch.py ... --no-cache        # always call the model
    python3 app/batch.py ... --cache-only      # replay cached replies, never call
    python3 app/batch.py ... --trace t.jsonl   # one trace line per case

Ordered output is not guaranteed; the evaluator matches on case_id.
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

import dna

LOCK = Lock()


def load_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def done_ids(path):
    if not os.path.exists(path):
        return set()
    out = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                try:
                    out.add(json.loads(line)["case_id"])
                except (json.JSONDecodeError, KeyError):
                    pass
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0, help="first N cases only (0 = all)")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--model", default=None)
    ap.add_argument("--temperature", type=float, default=0)
    ap.add_argument("--thinking", choices=("on", "off"), default=None,
                    help="model reasoning: on or off (default: DNA_THINKING, else on)")
    ap.add_argument("--no-llm", action="store_true", help="use the deterministic rules baseline only")
    ap.add_argument("--no-cache", action="store_true", help="bypass the raw reply cache")
    ap.add_argument("--cache-only", action="store_true", help="use cached replies only; a miss is a rules fallback")
    ap.add_argument("--trace", default=None, help="write a per-case trace JSONL sidecar")
    ap.add_argument("--resume", action="store_true", help="skip case_ids already present in --out")
    a = ap.parse_args()
    if a.no_cache and a.cache_only:
        ap.error("--no-cache and --cache-only are mutually exclusive")

    cases = load_jsonl(a.inputs)
    if a.offset:
        cases = cases[a.offset:]
    if a.limit:
        cases = cases[:a.limit]
    if not cases:
        sys.exit("no cases selected")

    skip = done_ids(a.out) if a.resume else set()
    if skip:
        cases = [c for c in cases if c["case_id"] not in skip]
    if not cases:
        print("nothing to do: all cases already in %s" % a.out)
        return 0

    if not a.no_llm and not a.cache_only and not dna.llm.API_KEY:
        sys.exit(dna.llm.missing_key_hint())

    mode = "rules only" if a.no_llm else ("model %s" % (a.model or dna.llm.MODEL))
    if not a.no_llm:
        mode += " | thinking %s" % ("on" if dna.thinking_flag(a.thinking) else "off")
    if a.cache_only:
        mode += " | cache only"
    elif a.no_cache:
        mode += " | no cache"
    print("%d cases | %s | workers %d | out %s" % (len(cases), mode, a.workers, a.out), file=sys.stderr)

    started = time.time()
    ok = fallback = failed = hits = misses = 0

    def run(case):
        """Return (answer, trace). A cache miss is a fallback, not an error."""
        if a.no_llm:
            trace = {"raw_text": None, "raw": None, "rules": [], "meta": None,
                     "fallback": True, "error": None}
            return dna.fallback(case), trace
        try:
            return dna.run(case, model=a.model, temperature=a.temperature, retries=a.retries,
                           use_cache=not a.no_cache, cache_only=a.cache_only,
                           thinking=a.thinking)
        except Exception as exc:  # defensive: one bad case must not kill the run
            trace = {"raw_text": None, "raw": None, "rules": [], "meta": None,
                     "fallback": True, "error": "%s: %s" % (type(exc).__name__, str(exc)[:120])}
            return dna.fallback(case, trace["error"]), trace

    trace_fh = open(a.trace, "a" if a.resume else "w", encoding="utf-8") if a.trace else None
    try:
        with open(a.out, "a" if a.resume else "w", encoding="utf-8") as fh, \
                ThreadPoolExecutor(max_workers=max(1, a.workers)) as pool:
            futures = {pool.submit(run, c): c for c in cases}
            for i, fut in enumerate(as_completed(futures), 1):
                case = futures[fut]
                try:
                    out, trace = fut.result()
                except Exception as exc:
                    out = dna.fallback(case, "worker: %s" % exc)
                    trace = {"raw_text": None, "raw": None, "rules": [], "meta": None,
                             "fallback": True, "error": "worker: %s" % exc}
                meta = trace.get("meta") or {}
                err = trace.get("error")
                hits += bool(meta.get("cached"))
                misses += err == "cache miss"
                if trace.get("fallback"):
                    if err and err != "cache miss":
                        failed += 1
                    else:
                        fallback += 1
                else:
                    ok += 1
                with LOCK:
                    fh.write(json.dumps(out, ensure_ascii=False) + "\n")
                    fh.flush()
                    if trace_fh is not None:
                        trace_fh.write(json.dumps(dict({"case_id": case["case_id"]}, **trace),
                                                  ensure_ascii=False) + "\n")
                        trace_fh.flush()
                if i % 10 == 0 or i == len(cases):
                    rate = i / max(1e-9, time.time() - started)
                    eta = (len(cases) - i) / rate if rate else 0
                    print("  %d/%d  %.1f/s  eta %ds  (answered %d, fallback %d, error %d, cache %d hit, %d miss)" % (
                        i, len(cases), rate, eta, ok, fallback, failed, hits, misses), file=sys.stderr)
    finally:
        if trace_fh is not None:
            trace_fh.close()

    print("done in %.1fs: %d answered, %d fallback, %d error, %d cache hit, %d miss -> %s" % (
        time.time() - started, ok, fallback, failed, hits, misses, a.out), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
