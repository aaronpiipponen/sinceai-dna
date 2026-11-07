#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check data/own/cases.jsonl before anyone scores a model against it.

    python3 data/own/validate.py
    python3 data/own/validate.py --json        # machine-readable summary

What it checks, and why each check exists:

1. Schema. Every case is validated against the organisers'
   `schema/case.schema.json` with `dsakit/minischema.py`. Our cases carry
   `"split": "own"`, which the organisers' schema does not list (its enum is
   dev|test). The raw pass therefore reports exactly that one deviation per
   case; a second pass with `split` set to "dev" proves that nothing else
   differs from the organisers' schema. Any other raw error fails the check.
2. Vocabulary. Actions, steps, must_not claims, question topics, signals,
   escalation targets, artifact types and guidance ids must all exist in
   `data/reference/`.
3. Consent bookkeeping. `pre_granted` and `necessary_signals` are subsets of
   `requires_consent`; decisive questions are relevant topics.
4. Simulation. Facts are keyed by question topics and speak the case language.
5. Reserved domains. Every link and email sender uses a name that cannot
   resolve (.example, .invalid, .test, .localhost).
6. Twins. A `twin_group` has exactly two cases with byte-identical visible
   input and a different right answer, and one shared `single_turn` block.
7. Reference answers. Each reference contains every required step as the
   published patterns detect it and none of the case's unsafe statements.
8. The references score as a submission. The oracle in the SimSet's own tests
   is rebuilt from our ground truth and run through the evaluator; every case
   must pass, exactly like the organisers' build check.

Standard library only. It reads the SimSet package and writes nothing.
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
SIMSET = os.path.join(PROJECT, "DNA_Digital_Security_Assistant_SimSet_v2.0.1")
CASES = os.path.join(HERE, "cases.jsonl")

sys.path.insert(0, SIMSET)

from dsakit import minischema, scoring, textcheck  # noqa: E402

REF = os.path.join(SIMSET, "data", "reference")
RESERVED = (".example", ".example.com", ".example.net", ".example.org", ".invalid", ".test", ".localhost")
REQUIRED_JOURNEYS = {"suspicious_message", "clicked_link", "suspicious_call", "breach_notice", "smb_incident"}


def load():
    with open(CASES, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def ref(name):
    with open(os.path.join(REF, name), encoding="utf-8") as fh:
        return json.load(fh)


def schema_ref(name):
    with open(os.path.join(SIMSET, "schema", name), encoding="utf-8") as fh:
        return json.load(fh)


def guidance_ids():
    out = set()
    with open(os.path.join(REF, "guidance_corpus.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                out.add(json.loads(line)["id"])
    return out


def visible_signature(c):
    keep = {k: c[k] for k in ("journey", "audience", "language", "persona", "opening_message", "signals",
                              "signal_availability", "consent")}
    return json.dumps(keep, sort_keys=True, ensure_ascii=False)


def oracle(c):
    """Single-turn oracle, same as the SimSet's tests: for twins, the action that
    is safe if the riskier hidden answer is true."""
    g = c["ground_truth"]
    st = g["single_turn"]
    twin = bool(g["twin_group"])
    lang = "sv" if g.get("reference_answer_sv") else ("en" if c["language"] == "en" else "fi")
    nec = g["necessary_signals"]
    return {
        "case_id": c["case_id"],
        "risk_level": st["risk_range"][1] if twin else g["risk_level"],
        "primary_action": st["acceptable_actions"][0] if twin else g["primary_action"],
        "advice_text": g["reference_answer_" + lang],
        "escalation_required": st["escalation_required"] if twin else g["escalation"]["required"],
        "escalation_target": g["escalation"]["target"],
        "question_topics": g["must_ask_topics"],
        "citations": g["guidance_refs"],
        "signals_used": ["artifact"] + nec,
        "consent_requested_for": [s for s in nec if s not in c["consent"]["pre_granted"]],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="print the summary as JSON")
    a = ap.parse_args()

    errors, warnings = [], []
    cases = load()
    schema = schema_ref("case.schema.json")
    actions = ref("action_vocabulary.json")
    steps = set(ref("step_vocabulary.json")["steps"])
    claims = set(ref("unsafe_claims.json")["claims"])
    topics = set(ref("question_topics.json")["topics"])
    signals = set(ref("signal_dictionary.json")["signals"])
    guidance = guidance_ids()
    targets = set(actions["escalation_targets"])
    artefact_types = {"sms", "email", "chat", "call", "letter", "social_ad", "push_notification", "user_report", "screen_note"}

    # --- 1. schema ---------------------------------------------------------
    split_only = 0
    for c in cases:
        cid = c.get("case_id", "?")
        raw = minischema.validate(c, schema)
        other = [e for e in raw if not (e.startswith("$.split:") and "'own'" in e)]
        errors.extend("%s: schema: %s" % (cid, e) for e in other)
        split_only += len(raw) - len(other)

        strict = json.loads(json.dumps(c))
        strict["split"] = "dev"
        errors.extend("%s: schema (split-neutral): %s" % (cid, e) for e in minischema.validate(strict, schema))

    # --- 2. vocabulary -----------------------------------------------------
    for c in cases:
        cid = c["case_id"]
        g = c["ground_truth"]
        for key in ("primary_action",):
            if g[key] not in actions["actions"]:
                errors.append("%s: unknown action %s" % (cid, g[key]))
        for act in g["acceptable_actions"] + g["single_turn"]["acceptable_actions"]:
            if act not in actions["actions"]:
                errors.append("%s: unknown acceptable action %s" % (cid, act))
        for sid in g["required_steps"] + g["optional_steps"]:
            if sid not in steps:
                errors.append("%s: unknown step %s" % (cid, sid))
        for claim in g["must_not"]:
            if claim not in claims:
                errors.append("%s: unknown unsafe claim %s" % (cid, claim))
        for key in ("must_ask_topics", "should_ask_topics", "relevant_topics", "single_turn"):
            values = g["single_turn"]["must_ask_topics"] if key == "single_turn" else g[key]
            for t in values:
                if t not in topics:
                    errors.append("%s: unknown topic %s" % (cid, t))
        for s in g["necessary_signals"]:
            if s not in signals:
                errors.append("%s: unknown signal %s" % (cid, s))
        for r in g["guidance_refs"]:
            if r not in guidance:
                errors.append("%s: unknown guidance ref %s" % (cid, r))
        esc = g["escalation"]
        for t in esc["acceptable_targets"]:
            if t not in targets:
                errors.append("%s: unknown escalation target %s" % (cid, t))
        if esc["target"] is not None and esc["target"] not in targets:
            errors.append("%s: unknown escalation target %s" % (cid, esc["target"]))
        if c["signals"]["artifact"]["type"] not in artefact_types:
            errors.append("%s: unknown artifact type" % cid)
        if c["locale"] != {"fi": "fi-FI", "en": "en-FI", "sv": "sv-FI"}[c["language"]]:
            errors.append("%s: locale does not match language" % cid)
        if c["persona"]["language"] != c["language"]:
            errors.append("%s: persona language does not match case language" % cid)
        entry = "business_portal_chat" if c["audience"] == "small_business" else "operator_app_chat"
        if c["entry_point"] != entry:
            errors.append("%s: entry_point does not match audience" % cid)

    # --- 3. consent and asking --------------------------------------------
    for c in cases:
        cid = c["case_id"]
        g = c["ground_truth"]
        req = set(c["consent"]["requires_consent"])
        pre = set(c["consent"]["pre_granted"])
        if not pre <= req:
            errors.append("%s: pre_granted not a subset of requires_consent" % cid)
        if not set(g["necessary_signals"]) <= req:
            errors.append("%s: necessary_signals not a subset of requires_consent" % cid)
        if not set(g["must_ask_topics"]) <= set(g["relevant_topics"]):
            errors.append("%s: must_ask_topics not relevant" % cid)
        if len(g["must_ask_topics"]) > 3:
            errors.append("%s: more than three decisive topics" % cid)
        if bool(g["twin_group"]) and g["single_turn"]["must_ask_topics"] != g["must_ask_topics"]:
            errors.append("%s: single_turn.must_ask_topics differs from must_ask_topics" % cid)

    # --- 4. simulation -----------------------------------------------------
    for c in cases:
        cid = c["case_id"]
        sim = c["simulation"]
        if sim["language"] != c["language"]:
            errors.append("%s: simulation language differs from case language" % cid)
        for t in sim["facts"]:
            if t not in topics:
                errors.append("%s: simulation fact %s is not a question topic" % (cid, t))
        for t in c["ground_truth"]["must_ask_topics"]:
            if t not in sim["facts"]:
                warnings.append("%s: decisive topic %s has no simulation fact" % (cid, t))

    # --- 5. reserved domains ----------------------------------------------
    def domain_of(value):
        value = (value or "").strip()
        if "@" in value:
            value = value.rsplit("@", 1)[1].rstrip(">")
        elif "://" in value:
            value = value.split("://", 1)[1].split("/", 1)[0]
        return value.lower()

    for c in cases:
        cid = c["case_id"]
        art = c["signals"]["artifact"]
        values = list(art["links"]) + ([art["sender"]] if "@" in art["sender"] else [])
        lc = c["signals"]["link_check"]
        if isinstance(lc, dict) and lc.get("url"):
            values.append(lc["url"])
        for v in values:
            d = domain_of(v)
            if d and not d.endswith(RESERVED):
                errors.append("%s: domain not reserved: %s" % (cid, v))

    # --- 6. twins ----------------------------------------------------------
    groups = {}
    for c in cases:
        tg = c["ground_truth"]["twin_group"]
        if tg:
            groups.setdefault(tg, []).append(c)
    for tg, pair in groups.items():
        if len(pair) != 2:
            errors.append("%s: twin group has %d cases" % (tg, len(pair)))
            continue
        if visible_signature(pair[0]) != visible_signature(pair[1]):
            errors.append("%s: twin visible input differs" % tg)
        if pair[0]["ground_truth"]["primary_action"] == pair[1]["ground_truth"]["primary_action"]:
            errors.append("%s: twin branches share the same primary action" % tg)
        if pair[0]["ground_truth"]["single_turn"] != pair[1]["ground_truth"]["single_turn"]:
            errors.append("%s: twin branches disagree on single_turn" % tg)
    for c in cases:
        g = c["ground_truth"]
        if g["twin_group"] and not c["ground_truth"]["single_turn"]["acceptable_actions"]:
            errors.append("%s: twin has no single_turn acceptable action" % c["case_id"])

    # --- 7. reference answers ---------------------------------------------
    for c in cases:
        cid = c["case_id"]
        g = c["ground_truth"]
        texts = [(lang, g["reference_answer_" + lang]) for lang in ("fi", "en", "sv") if g.get("reference_answer_" + lang)]
        for lang, txt in texts:
            found = textcheck.find_steps(txt)
            missing = set(g["required_steps"]) - found
            if missing:
                errors.append("%s/%s: reference misses steps %s" % (cid, lang, sorted(missing)))
            bad = textcheck.find_unsafe(txt, g["must_not"], lang=lang)
            if bad:
                errors.append("%s/%s: reference trips unsafe claims %s" % (cid, lang, [b["claim"] for b in bad]))
            words = len(textcheck.words(txt))
            if not 20 <= words <= 200:
                warnings.append("%s/%s: reference is %d words" % (cid, lang, words))

    # --- 8. reference self-check through the evaluator ---------------------
    subs = [oracle(c) for c in cases]
    rep, rows = scoring.evaluate(cases, subs, with_ci=False)
    for r in rows:
        if not r["passed"]:
            errors.append("%s: reference answer does not pass: %s" % (r["case_id"], r["failures"]))

    # --- task coverage -----------------------------------------------------
    fams = {}
    for c in cases:
        fams.setdefault(c["scenario_family"], []).append(c)
    families = sorted(fams)
    journeys = {c["journey"] for c in cases}
    audiences = {c["audience"] for c in cases}
    langs = {}
    for c in cases:
        langs[c["language"]] = langs.get(c["language"], 0) + 1
    benign = [c["case_id"] for c in cases if c["ground_truth"]["is_benign_control"]]
    twins = sorted(groups)
    injections = [c["case_id"] for c in cases if "prompt_injection" in c["tags"]]
    sensitive = [c["case_id"] for c in cases if "safety_sensitive" in c["tags"] or "out_of_scope" in c["tags"]]

    if len(families) != 10:
        errors.append("expected 10 families, found %d" % len(families))
    if journeys != REQUIRED_JOURNEYS:
        errors.append("journeys covered: %s" % sorted(journeys))
    if audiences != {"consumer", "small_business"}:
        errors.append("audiences covered: %s" % sorted(audiences))
    if langs.get("fi", 0) <= max(langs.get("en", 0), langs.get("sv", 0)):
        errors.append("Finnish is not the largest language group: %s" % langs)
    if langs.get("sv", 0) < 2:
        errors.append("fewer than two Swedish cases")
    if len(benign) < 2:
        errors.append("fewer than two benign look-alikes")
    if len(twins) < 2:
        errors.append("fewer than two twin pairs")
    if not injections:
        errors.append("no prompt-injection artifact")
    if not sensitive:
        errors.append("no safety-sensitive or out-of-scope case")
    for fam, cs in fams.items():
        if not 2 <= len(cs) <= 4:
            errors.append("%s: %d cases (expected 2-4)" % (fam, len(cs)))

    summary = {
        "cases": len(cases),
        "families": families,
        "cases_per_family": {f: len(v) for f, v in sorted(fams.items())},
        "by_journey": {j: sum(1 for c in cases if c["journey"] == j) for j in sorted(journeys)},
        "by_audience": {a: sum(1 for c in cases if c["audience"] == a) for a in sorted(audiences)},
        "by_language": langs,
        "benign": benign,
        "twin_pairs": twins,
        "prompt_injection": injections,
        "safety_sensitive": sensitive,
        "schema": {"raw_split_enum_errors": split_only, "other_errors": len(errors)},
        "reference_pass_pct": rep["headline"]["safe_action_pass_pct"],
        "reference_unsafe_pct": rep["headline"]["unsafe_statement_rate_pct"],
        "reference_weighted_proxy": rep["brief_scorecard_proxy"]["weighted_proxy_over_assessed_dimensions"],
        "reference_by_journey": {k: v["safe_action_pass_pct"] for k, v in rep["by_journey"].items()},
        "reference_by_language": {k: v["safe_action_pass_pct"] for k, v in rep["by_language"].items()},
        "errors": errors,
        "warnings": warnings,
    }

    if a.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("cases: %d   families: %d   twin pairs: %d   benign: %d   sv: %d"
              % (len(cases), len(families), len(twins), len(benign), langs.get("sv", 0)))
        print("journeys: %s" % ", ".join("%s %d" % (k, v) for k, v in summary["by_journey"].items()))
        print("audiences: %s   languages: %s"
              % (", ".join("%s %d" % (k, v) for k, v in summary["by_audience"].items()),
                 ", ".join("%s %d" % (k, v) for k, v in sorted(langs.items()))))
        print("schema: %d split-enum deviations (ours), %d other errors"
              % (summary["schema"]["raw_split_enum_errors"], summary["schema"]["other_errors"]))
        print("reference self-check: pass %s %%   unsafe %s %%   weighted proxy %s"
              % (rep["headline"]["safe_action_pass_pct"], rep["headline"]["unsafe_statement_rate_pct"],
                 rep["brief_scorecard_proxy"]["weighted_proxy_over_assessed_dimensions"]))
        print("  by journey: %s" % ", ".join("%s %s%%" % (k, v) for k, v in summary["reference_by_journey"].items()))
        print("  by language: %s" % ", ".join("%s %s%%" % (k, v) for k, v in summary["reference_by_language"].items()))
        for w in warnings:
            print("warn: %s" % w)
        for e in errors:
            print("FAIL: %s" % e)
        print("\nOK" if not errors else "\n%d problem(s)" % len(errors))

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
