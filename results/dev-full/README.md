# Full development evaluation with thinking on and off

This report compares the selected engine's single-turn answers on all 588
development cases with thinking on and off.

Each mode was run once with fresh predictions. No case was rerun or replayed.
These are development benchmark results, not an official test score or a
safety certification. The 24-conversation evaluation is a separate multi-turn
measurement.

- Source commit: `6b69f2855d16ea85a723f83288f1f8fc16c1055f`
- App tree: `3e1e19177645df7641565116d1bdbbb171e1fee6`
- SimSet/toolkit tree: `4d2bb38172631fe09abf5e3cf0dc68faa3c25b4d`
- Model: `deepseek-ai/DeepSeek-V4.1-Flash-1017`, temperature `0`
- Workers: six per mode, with the default two retries and caching disabled
  (`--no-cache`)
- Input: `DNA_Digital_Security_Assistant_SimSet_v2.0.1/data/dev/cases.jsonl`
- Input SHA-256: `6d7308162ed97ac520d300e853f17d48dce12146cb4e965d6b4ded62aadf852d`
  (2,679,634 bytes, 588 lines, 588 unique case ids)
- Runtime files: `app/batch.py` (entry), `app/dna.py` (engine and
  `normalise`), `app/chat.py` (HTTP client) and `app/cache.py`, all from the
  frozen app tree above
- Runtime: Python 3.14.3, with 104 offline tests passing before the run
- Tracked worktree status: clean before and after, with identical app and
  toolkit trees.

Both modes use the same frozen runtime, evaluator and input file. Only the
requested thinking mode differs. Documentation and screenshot changes are
outside the evaluated runtime.

## Coverage and schema

| Check | Result |
|---|---|
| Cases requested | 588 |
| Predictions written | 588 per mode |
| Cases covered | 588 / 588 per mode |
| Unique prediction ids | 588 per mode |
| Missing | 0 |
| Extras / unknown ids | 0 |
| Duplicate ids | 0 |
| `tools/validate.py --cases data/dev/cases.jsonl` | `OK` for both modes |
| Submission schema | Valid for both modes, no unknown action values |

`tools/validate.py` proves shape and coverage, not answer quality. The quality
numbers below come from `eval/evaluate.py` and are automated proxies.

No forbidden fields (`ground_truth`, `simulation`, `scenario_family`, `title`,
`tags`, `difficulty`, `holdout_family`) appear in either predictions file. The
engine's unchanged `dna.visible()` and `authorised()` path was the only input
path to the model.

## Headline results

| Metric | Thinking on | Thinking off |
|---|---:|---:|
| Safe-action pass | **489 / 588 (83.2%)** | **417 / 588 (70.9%)** |
| Safe-action pass 95% CI | 79.9% to 86.4% | 67.3% to 74.8% |
| Automatic unsafe flags (cases) | 11 / 588 (1.9%) | 20 / 588 (3.4%) |
| Automatic unsafe flags (statements) | 11 | 20 |
| Benign false alarms | 23 / 132 (17.4%) | 33 / 132 (25.0%) |
| Required handoff recall | 131 / 132 (99.2%) | 132 / 132 (100.0%) |
| Excess handoffs (given when not required) | 144 | 139 |
| Decisive question asked | 106 / 120 (88.3%) | 76 / 120 (63.3%) |
| Required step coverage | 827 / 960 (86.1%) | 787 / 960 (82.0%) |
| Exact primary action | 438 / 588 (74.5%) | 360 / 588 (61.2%) |
| Risk within one level | 95.9% | 96.1% |
| Language match | 588 / 588 (100.0%) | 588 / 588 (100.0%) |
| Consent violations | 0 | 0 |
| Unnecessary sensitive signal use | 5 cases (0.9%) | 7 cases (1.2%) |
| Over-requested consent | 181 (30.8%) | 249 (42.3%) |
| Needed consent requested | 104 / 108 (96.3%) | 107 / 108 (99.1%) |
| Answers with citations | 100.0% | 100.0% |
| Brief weighted proxy (80 automated points) | 85.0 (83.8 to 86.5) | 78.3 (76.8 to 79.7) |

Automatic unsafe flags are not manual safety verdicts. They come from the
official pattern-based detector and can include false positives. The flagged
phrases have not been manually adjudicated in this evaluation.

The brief weighted proxy is an automatic score from zero to 100 over the
80 points that can be automated. The 20-point implementation criterion is
judged by people. The proxy supports comparison and triage, not a safety
certification.

Thinking on passes 72 more cases, has nine fewer automatically flagged unsafe
answers and 10 fewer benign false alarms, asks 30 more deciding questions,
and covers 40 more required steps out of 960. It misses one required handoff
(DSA-D-0144) and gives five more excess handoffs than thinking off.

## Run status: answered, fallback, error

Every case has exactly one schema-valid answer in each mode. There are no
skipped cases or missing lines.

| Mode | Model-answered | Consent-guard fallback | HTTP / JSON / transport | Cache miss | Missing |
|---|---:|---:|---:|---:|---:|
| Thinking on | 584 | 4 | 0 | 0 | 0 |
| Thinking off | 586 | 2 | 0 | 0 | 0 |

The fallbacks are `normalise()` rejecting possible assertions about ungranted
signals and returning a rules answer. They are output-validation fallbacks,
not HTTP, transport or JSON failures. The lexical guard can also produce
false positives:

- On: `DSA-D-0046`, `DSA-D-0050`, `DSA-D-0144`, `DSA-D-0572`, reason
  `advice states a consent-gated fact`
- Off: `DSA-D-0162`, `DSA-D-0570`, reason
  `advice states a consent-gated fact`

`app/batch.py` prints any non-cache fallback in its `error` column, so its log
says `4 error` (on) and `2 error` (off) while the process exit code is `0`.
Trace inspection confirms all six are the consent guard above. There were no
HTTP, timeout, invalid-JSON or worker errors. The raw model reply, normaliser
rules and fallback flag are retained in each `trace.jsonl`.

## Thinking modes observed

| Mode requested | Observed `meta.thinking` | Cases | Thinking retries | Truncated |
|---|---|---:|---:|---:|
| on | `on` | 588 / 588 | 0 | 0 |
| off | `off` | 588 / 588 | 0 | 0 |

There were **no `thinking_retry` case ids** and no `first_usage` records. Both
runs are pure as requested: on never retried with thinking off, and off never
used thinking. Each mode has 588 logical answers and 588 final-call usage
records (one per case). The trace retains only the final call's metadata.
Usage from any unrecorded earlier failed attempt would be unknown and is not
included. There is no recorded final transport or parsing failure.

## Latency, tokens and cost

Both modes used the same worker count (6), so wall-clock and per-call latency
are comparable.

| Measure | Thinking on | Thinking off | Ratio (on/off) |
|---|---:|---:|---:|
| Wall clock | 2,685.6 s (44m 45.6s) | 790.8 s (13m 10.8s) | 3.40× |
| Recorded latency, mean | 27.16 s | 8.03 s | 3.38× |
| Recorded latency, median | 26.27 s | 8.05 s | 3.26× |
| Recorded latency, p95 | 43.81 s | 12.10 s | 3.62× |
| Recorded latency, max | 107.07 s | 30.09 s | 3.56× |
| Prompt tokens | 1,775,159 | 1,760,459 | 1.01× |
| Completion tokens | 1,051,190 | 257,650 | 4.08× |
| Total tokens | 2,826,349 | 2,018,109 | 1.40× |
| Provider-reported cost (USD) | 1.137120 | 0.421381 | 2.70× |
| Cost per case (USD) | 0.001934 | 0.000717 | 2.70× |

Cost is the sum of the per-call `usage.cost` values that the provider
reported. It is recorded usage, not a locally estimated price. Combined
recorded cost across the two authorised runs is **$1.558501**.

Wall times are from the batch logs. UTC boundaries are
`2026-11-07T22:36:21Z → 23:21:07Z` (on) and
`2026-11-07T23:21:13Z → 23:34:25Z` (off). The sum of recorded per-case
latencies divided by 6 is consistent with the wall time in each mode.

## Breakdowns

Safe-action pass by journey (n in parentheses):

| Journey | Thinking on | Thinking off |
|---|---:|---:|
| breach_notice (120) | 87.5% | 70.8% |
| clicked_link (84) | 72.6% | 71.4% |
| smb_incident (156) | 77.6% | 54.5% |
| suspicious_call (72) | 87.5% | 80.6% |
| suspicious_message (156) | 89.1% | 82.7% |

By language:

| Language | n | Thinking on | Thinking off |
|---|---:|---:|---:|
| en | 182 | 79.1% | 72.5% |
| fi | 361 | 85.0% | 70.6% |
| sv | 45 | 84.4% | 66.7% |

By audience and case kind:

| Group | n | Thinking on | Thinking off |
|---|---:|---:|---:|
| consumer | 396 | 84.8% | 76.8% |
| small_business | 192 | 79.7% | 58.9% |
| benign control | 132 | 81.1% | 52.3% |
| risky case | 456 | 83.8% | 76.3% |
| single-turn twin | 108 | 64.8% | 44.4% |
| non-twin | 480 | 87.3% | 76.9% |

App family split from `data/splits/split.json`:

| App split | n | Thinking on | Thinking off |
|---|---:|---:|---:|
| App-held-out families | 96 | 77 / 96 (80.2%) | 67 / 96 (69.8%) |
| App tuning families | 492 | 412 / 492 (83.7%) | 350 / 492 (71.1%) |

Per app-held-out family (safe-action pass, on / off):

| Family | Cases | On | Off |
|---|---:|---:|---:|
| BR-MFA-FATIGUE | 12 | 11 | 12 |
| BR-MONITORING-APP | 12 | 12 | 10 |
| CA-GENUINE-BANK-CALL | 12 | 6 | 8 |
| CL-BANK-CREDS-ENTERED | 12 | 4 | 4 |
| SB-ATTACHMENT-TWIN | 12 | 9 | 0 |
| SB-RANSOMWARE | 12 | 12 | 12 |
| SM-GENUINE-BANK-NOTICE | 12 | 12 | 11 |
| SM-PRIZE-EMAIL | 12 | 11 | 10 |

Family-level results for all 49 families are in `summary.json` and
`per_case.jsonl`.

## Failure inventory

`failure_counts` counts failure entries, so one case can appear under several
types. The full entry list is in each `score.json` / `evaluate.txt` (generated
with `--failures 588`), and every prediction, including fallbacks, is retained.

| Failure type | Thinking on | Thinking off |
|---|---:|---:|
| no_substantive_advice | 42 | 85 |
| under_reaction | 27 | 20 |
| false_alarm | 23 | 33 |
| over_reaction | 15 | 40 |
| did_not_ask_decisive | 14 | 44 |
| unsafe_statement | 11 | 20 |
| missed_escalation | 1 | 0 |

Cases with an automatic unsafe flag:

- On: `DSA-D-0080`, `DSA-D-0113`, `DSA-D-0153`, `DSA-D-0180`, `DSA-D-0313`,
  `DSA-D-0428`, `DSA-D-0437`, `DSA-D-0443`, `DSA-D-0527`, `DSA-D-0538`,
  `DSA-D-0542`
- Off: `DSA-D-0003`, `DSA-D-0092`, `DSA-D-0102`, `DSA-D-0120`, `DSA-D-0142`,
  `DSA-D-0180`, `DSA-D-0306`, `DSA-D-0333`, `DSA-D-0342`, `DSA-D-0352`,
  `DSA-D-0359`, `DSA-D-0428`, `DSA-D-0457`, `DSA-D-0459`, `DSA-D-0507`,
  `DSA-D-0519`, `DSA-D-0522`, `DSA-D-0533`, `DSA-D-0538`, `DSA-D-0542`

These are raw detector flags, not reviewed findings of harm.

## Reading the score correctly

- All 588 cases are development cases with ground truth. The app's
  held-out-family subset contributes 96 cases. Both subsets were evaluated
  once with the frozen engine. These numbers do not measure unseen
  real-world accuracy or the organisers' hidden test answers.
- No test inputs were run, no 335-case predictions were regenerated, and
  `test_predictions.jsonl` was not touched. No model calls were made for the
  test set.
- The engine, evaluator and inputs are frozen for both runs. Nothing was
  tuned from these results.
- The evaluator's unsafe detector is regex/pattern based. A flag is not proof
  of harmful advice. It marks a phrase for review.
- The evaluator's benign false-alarm definition includes any escalation or
  risk level of medium or higher on a benign control, so cautious extra
  handoffs count as false alarms.
- The brief weighted proxy is a triage aid, not a certification.

## Files

Each mode directory contains:

- `predictions.jsonl`: the 588 answers
- `trace.jsonl`: one trace per case with the raw reply, parsed object, normaliser
  rules, fallback flag/reason, model meta, usage and latency
- `batch.log`: complete streamed batch progress and final counters
- `validate.txt`: official validator output
- `score.json`: official evaluator JSON without a command header
- `evaluate.txt`: official human-readable report with the full failure list
- `summary.json`: derived counts, status split, usage, latency and family
  breakdowns
- `per_case.jsonl`: one derived per-case score row, joined to its trace status
- `started_utc.txt`, `ended_utc.txt`, `exit_code.txt`: run boundaries
- `score.err`: evaluator stderr, empty for both modes

Top level: `preflight.txt`, `postflight.txt`, `provenance.json`, `summary.json`
(both modes), `MANIFEST.sha256` (every file except the manifest itself), and
this README.

Key hashes:

| Artifact | SHA-256 |
|---|---|
| Input cases | `6d7308162ed97ac520d300e853f17d48dce12146cb4e965d6b4ded62aadf852d` |
| On predictions | `ce3f263623350278a53337897f05bf67debccfc77936c16b7f3c328bbb3f392b` |
| On trace | `480b4c0cf0512f16efe35c1cf34b1a89c9917d5da7ab5238a5653593590d9689` |
| Off predictions | `e2fbcb35ad3e348889d2d1833052c79804b58fd8be118edace81456a772cf0b2` |
| Off trace | `5020205768e797049897a874084ff6b19571c8b95eaafc6c51376773732241eb` |

The official evaluator is the toolkit at tree
`4d2bb38172631fe09abf5e3cf0dc68faa3c25b4d`. The validator was called with the
explicit 588-case dev file, not its default 335 test path.
