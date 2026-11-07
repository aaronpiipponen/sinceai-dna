#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Score a predictions file against tune, holdout and the five sample journeys.

    python3 app/score.py results/dev_predictions_replay.jsonl --label replay_run1
    python3 app/score.py results/dev_predictions_run1.jsonl --label run1 --trace results/dev.trace.jsonl
    python3 app/score.py results/dev_predictions_run1.jsonl --label dev_run1 --per-case
    python3 app/score.py results/dev_predictions_run1.jsonl --extra-cases data/own/cases.jsonl

Calls the SimSet evaluator as a library and prints a compact side-by-side
table. Writes results/reports/<UTC timestamp>_<label>.json with provenance:
git commit, model, temperature and prompt hashes (when a trace is given).

`--per-case` also writes results/runs/<label>.scored.json: the same report plus
one row per dev case, which is the only thing the lab's Runs view reads. Each
row carries our answer, the reference, the evaluator verdict and the failure
details, and its split comes from data/splits/split.json. The reference answer
is in the case language (fi / en); Swedish cases fall back to Finnish.

Holdout families are locked. Their numbers are printed for gates only; the
one-line reminder says so.
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
SIMSET = os.path.join(PROJECT, "DNA_Digital_Security_Assistant_SimSet_v2.0.1")
SPLITS = os.path.join(PROJECT, "data", "splits")
REPORTS = os.path.join(PROJECT, "results", "reports")
RUNS = os.path.join(PROJECT, "results", "runs")

sys.path.insert(0, SIMSET)
sys.path.insert(0, HERE)

from dsakit import scoring  # noqa: E402
import chat as llm  # noqa: E402  (default model id only)

SETS = (
    ("tune", os.path.join(SPLITS, "tune.jsonl")),
    ("holdout", os.path.join(SPLITS, "holdout.jsonl")),
    ("five journeys", os.path.join(SIMSET, "data", "samples", "five_journeys.jsonl")),
)


def _rel(path):
    """Project-relative when inside the repo, absolute otherwise."""
    try:
        rel = os.path.relpath(path, PROJECT)
    except ValueError:
        return path
    return path if rel.startswith("..") else rel


def git_commit():
    """Short HEAD, marked -dirty when the working tree has changes."""
    try:
        head = subprocess.check_output(
            ["git", "-C", PROJECT, "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL, text=True).strip()
        status = subprocess.check_output(
            ["git", "-C", PROJECT, "status", "--porcelain"],
            stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return head + ("-dirty" if status else "")


def trace_provenance(path):
    """Model, temperature and prompt hashes recorded by batch.py / replay.py."""
    models, temperatures, hashes = set(), set(), set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            meta = (json.loads(line).get("meta") or {})
            if meta.get("model"):
                models.add(meta["model"])
            if meta.get("temperature") is not None:
                temperatures.add(meta["temperature"])
            if meta.get("prompt_hash"):
                hashes.add(meta["prompt_hash"])
    one = lambda xs: next(iter(xs)) if len(xs) == 1 else (sorted(xs) or None)
    return {"model": one(models), "temperature": one(temperatures),
            "prompt_hashes": sorted(hashes) or None}


def summarise(rep, rows):
    """The handful of numbers the table needs, plus counts for honesty."""
    h, d = rep["headline"], rep["details"]
    benign = [r for r in rows if r["benign"]]
    twins = [r for r in rows if r["twin"]]
    return {
        "cases": rep["cases"],
        "pass_pct": h["safe_action_pass_pct"],
        "unsafe_statement_pct": h["unsafe_statement_rate_pct"],
        "benign_false_alarm_pct": h["false_alarm_rate_on_benign_pct"],
        "benign_false_alarms": sum(1 for r in benign if r.get("false_alarm")),
        "benign_cases": len(benign),
        "escalation_recall_pct": h["escalation_recall_pct"],
        "escalation_false_positives": h["escalation_false_positives"],
        "decisive_question_pct": h["asked_decisive_question_pct"],
        "step_coverage_pct": d["required_step_coverage_pct"],
        "weighted_proxy": rep["brief_scorecard_proxy"]["weighted_proxy_over_assessed_dimensions"],
        "twin_pass_pct": (round(100.0 * sum(1 for r in twins if r.get("passed")) / len(twins), 1)
                          if twins else None),
        "twin_cases": len(twins),
        "by_language": {k: {"n": v["n"], "pass_pct": v["safe_action_pass_pct"]}
                        for k, v in rep["by_language"].items()},
    }


def holdout_families():
    """Families locked by app/split.py; empty when the split has not been made."""
    try:
        with open(os.path.join(SPLITS, "split.json"), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return set()
    return {f for f in data.get("holdout_families") or [] if isinstance(f, str)}


def _unique(values):
    out = []
    for value in values:
        if value not in out:
            out.append(value)
    return out


def _strings(values):
    return [v for v in values or [] if isinstance(v, str)]


def _ours(sub):
    """Our submitted answer, as the inspector shows it."""
    sub = sub if isinstance(sub, dict) else {}
    conv = sub.get("conversation") if isinstance(sub.get("conversation"), dict) else {}
    topics = _strings(sub.get("question_topics")) or _strings(conv.get("asked_topics_flat"))
    return {
        "action": sub.get("primary_action"),
        "risk": sub.get("risk_level"),
        "escalation": bool(sub.get("escalation_required")),
        "escalation_target": sub.get("escalation_target"),
        "advice_text": sub.get("advice_text") or "",
        "steps": _strings(sub.get("steps")),
        "question_topics": topics,
    }


def _expected(case):
    """The reference answer, narrowed to what the Runs table compares."""
    gt = case.get("ground_truth") or {}
    acceptable = _unique([gt.get("primary_action")] + _strings(gt.get("acceptable_actions")))
    out = {
        "primary_action": gt.get("primary_action"),
        "acceptable": [a for a in acceptable if a],
        "risk": gt.get("risk_level"),
        "escalation": gt.get("escalation") or {},
        "required_steps": _strings(gt.get("required_steps")),
        "must_ask": _strings(gt.get("must_ask_topics")),
    }
    if gt.get("twin_group") and isinstance(gt.get("single_turn"), dict):
        # Twins are judged against a wider single-turn range; say so rather
        # than pretend the strict primary action is the only acceptable one.
        single = gt["single_turn"]
        out["single_turn"] = {
            "acceptable": _strings(single.get("acceptable_actions")),
            "risk_range": _strings(single.get("risk_range")),
            "escalation_required": bool(single.get("escalation_required")),
        }
    return out


def _reference(case):
    """Reference text in the case language; Swedish falls back to Finnish."""
    gt = case.get("ground_truth") or {}
    lang = case.get("language") or "en"
    order = ["fi", "en"] if lang == "sv" else ([lang] if lang in ("fi", "en") else ["en", "fi"])
    for candidate in order:
        text = gt.get("reference_answer_" + candidate)
        if isinstance(text, str) and text.strip():
            return {"language": candidate, "text": text}
    return {"language": "en", "text": ""}


def _checks(row):
    """The evaluator booleans the lab's header and inspector need."""
    return {
        "action_ok": row.get("action_ok"),
        "risk_exact": row.get("risk_exact"),
        "risk_within_one": row.get("risk_within_one"),
        "asked_ok": row.get("asked_ok"),
        "false_alarm": row.get("false_alarm"),
        "esc_expected": row.get("esc_expected"),
        "esc_given": row.get("esc_given"),
        "steps_found": row.get("steps_found"),
        "steps_missing": row.get("steps_missing") or [],
        "unsafe": row.get("unsafe") or [],
    }


def per_case_rows(evaluated, cases_by_id, subs_by_id, holdout):
    """One honest row per dev case: ours, the reference, the verdict."""
    rows = []
    for row in evaluated:
        case = cases_by_id.get(row.get("case_id"))
        if case is None:
            continue
        ours = _ours(subs_by_id.get(row["case_id"]))
        expected = _expected(case)
        rows.append({
            "case_id": row["case_id"],
            "journey": row.get("journey") or case.get("journey"),
            "language": row.get("language") or case.get("language"),
            "audience": row.get("audience") or case.get("audience"),
            "benign": bool(row.get("benign")),
            "twin": bool(row.get("twin")),
            "split": "holdout" if case.get("scenario_family") in holdout else "tune",
            "mode": row.get("mode"),
            "passed": bool(row.get("passed")),
            "failures": row.get("failures") or [],
            "ours": ours,
            "expected": expected,
            "checks": _checks(row),
            "reference": _reference(case),
        })
    return sorted(rows, key=lambda r: r["case_id"])


def _pass_counts(rows):
    passed = sum(1 for r in rows if r.get("passed"))
    return {"cases": len(rows), "passed": passed,
            "pass_pct": round(100.0 * passed / len(rows), 1) if rows else None}


def run_summary(rows):
    """The small block /api/lab/runs reads, plus tune / holdout side by side."""
    summary = _pass_counts(rows)
    summary["by_split"] = {
        split: _pass_counts([r for r in rows if r["split"] == split])
        for split in ("tune", "holdout")
    }
    counts = {}
    for row in rows:
        for failure in row.get("failures") or []:
            kind = failure.get("type") if isinstance(failure, dict) else failure
            if isinstance(kind, str):
                counts[kind] = counts.get(kind, 0) + 1
    summary["failure_counts"] = dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
    return summary


def score(pred_path, label, trace_path=None, write=True, per_case=False, extra_cases=None):
    """Score `pred_path` against the configured sets; return the report dict.

    `extra_cases` adds a fourth "own" column for a case file outside the
    split, such as data/own/cases.jsonl. Its cases stay out of --per-case.

    The web server can call this directly. Nothing here reads the model or the
    network: the evaluator is pure standard library over the files.
    """
    sets = list(SETS)
    if extra_cases:
        sets.append(("own", extra_cases))
    for _, path in sets:
        if not os.path.exists(path):
            hint = " (run: python3 app/split.py)" if path.startswith(SPLITS) else ""
            raise FileNotFoundError("missing %s%s" % (path, hint))
    subs = scoring.load_jsonl(pred_path)
    now = datetime.datetime.now(datetime.timezone.utc)

    report = {
        "label": label,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "provenance": {
            "predictions": _rel(pred_path),
            "git_commit": git_commit(),
            "model": llm.MODEL,
            "temperature": None,
            "prompt_hashes": None,
            "trace": _rel(trace_path) if trace_path else None,
        },
        "sets": {},
    }
    if trace_path:
        prov = trace_provenance(trace_path)
        for key, value in prov.items():
            if value not in (None, []):
                report["provenance"][key] = value

    evaluated = []
    cases_by_id = {}
    for name, path in sets:
        cases = scoring.load_jsonl(path)
        rep, rows = scoring.evaluate(cases, subs, with_ci=False)
        report["sets"][name] = {
            "summary": summarise(rep, rows),
            "evaluator": {
                "headline": rep["headline"],
                "details": {k: v for k, v in rep["details"].items()},
                "brief_scorecard_proxy": rep["brief_scorecard_proxy"],
                "by_language": rep["by_language"],
                "twins_vs_single": rep["twins_vs_single"],
                "benign_vs_risky": rep["benign_vs_risky"],
                "failure_counts": rep["failure_counts"],
                "coverage": rep["coverage"],
            },
        }
        if name in ("tune", "holdout"):
            evaluated.extend(rows)
            for case in cases:
                cases_by_id[case["case_id"]] = case

    if per_case:
        subs_by_id = {s["case_id"]: s for s in subs if isinstance(s, dict) and s.get("case_id")}
        rows = per_case_rows(evaluated, cases_by_id, subs_by_id, holdout_families())
        report["rows"] = rows
        report["summary"] = run_summary(rows)

    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", label) or "score"
    if write:
        stamp = now.strftime("%Y%m%dT%H%M%SZ")
        report["report_path"] = os.path.join(REPORTS, "%s_%s.json" % (stamp, safe))
        if per_case:
            os.makedirs(RUNS, exist_ok=True)
            report["scored_path"] = os.path.join(RUNS, safe + ".scored.json")
            with open(report["scored_path"], "w", encoding="utf-8") as fh:
                json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
                fh.write("\n")
        os.makedirs(REPORTS, exist_ok=True)
        with open(report["report_path"], "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
    return report


def _cell(value):
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return "%.1f" % value
    return str(value)


def print_table(report):
    names = list(report["sets"])
    summaries = [report["sets"][n]["summary"] for n in names]
    width = 15

    print("score: %s   |   commit %s   |   model %s"
          % (report["label"], report["provenance"]["git_commit"] or "n/a",
             report["provenance"]["model"]))
    print("predictions: %s" % report["provenance"]["predictions"])
    print("")
    print("%-27s" % "metric" + "".join("%*s" % (width, n) for n in names))
    rows = [
        ("cases", [s["cases"] for s in summaries]),
        ("safe-action pass %", [s["pass_pct"] for s in summaries]),
        ("unsafe statements %", [s["unsafe_statement_pct"] for s in summaries]),
        ("benign false alarms %", [s["benign_false_alarm_pct"] for s in summaries]),
        ("  false alarms / benign", ["%d/%d" % (s["benign_false_alarms"], s["benign_cases"])
                                     for s in summaries]),
        ("escalation recall %", [s["escalation_recall_pct"] for s in summaries]),
        ("escalation false positives", [s["escalation_false_positives"] for s in summaries]),
        ("decisive question %", [s["decisive_question_pct"] for s in summaries]),
        ("step coverage %", [s["step_coverage_pct"] for s in summaries]),
        ("weighted proxy (0-100)", [s["weighted_proxy"] for s in summaries]),
        ("twin pass %", [s["twin_pass_pct"] for s in summaries]),
        ("  twin cases", [s["twin_cases"] for s in summaries]),
    ]
    langs = sorted({lang for s in summaries for lang in s["by_language"]})
    for lang in langs:
        rows.append(("pass %% (%s)" % lang,
                     [(s["by_language"].get(lang) or {}).get("pass_pct") for s in summaries]))
    for label, values in rows:
        print("%-27s" % label + "".join("%*s" % (width, _cell(v)) for v in values))
    print("")
    print("Holdout is locked: gate only, never tune on it.")
    if report.get("scored_path"):
        print("scored run: %s" % _rel(report["scored_path"]))
    if report.get("report_path"):
        print("report: %s" % _rel(report["report_path"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("predictions", help="submission JSONL to score")
    ap.add_argument("--label", default="score", help="report label and filename suffix")
    ap.add_argument("--trace", default=None, help="batch/replay trace JSONL for provenance")
    ap.add_argument("--per-case", action="store_true",
                    help="also write results/runs/<label>.scored.json for the lab")
    ap.add_argument("--extra-cases", default=None, metavar="JSONL",
                    help="extra case file, scored as an additional 'own' column")
    a = ap.parse_args()

    try:
        report = score(a.predictions, a.label, a.trace, per_case=a.per_case,
                       extra_cases=a.extra_cases)
    except (OSError, ValueError) as exc:
        sys.exit(str(exc))
    print_table(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
