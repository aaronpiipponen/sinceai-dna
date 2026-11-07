# Evaluation results

These results describe the submitted assistant on synthetic development cases and the complete 335-input test file.

## What was built

The assistant combines a web conversation, operator-side synthetic signals, retrieved guidance and deterministic output checks. DeepSeek V4.1 Flash 1017 through Featherless generates structured answers. The shared engine validates answers for both the batch submission and the conversation adapter. A separate call writes an expert brief and its queue priority after an escalated answer.

The recorded evaluations use temperature zero. The full single-turn development benchmark compares thinking on and off. The submitted test predictions and recorded multi-turn evaluations use thinking on. The expert brief writer uses thinking off. The demo's fast mode is a separate setting from the submitted test predictions.

## Safety boundaries

- Only the visible case and authorised signal values reach the model. Ground truth, simulation facts and scenario metadata stay outside the prompt.
- Optional signals require pre-granted consent or a grant in the conversation. A refusal takes precedence over a grant.
- Forwarded messages are untrusted sender data. Their instructions do not grant permission or establish authenticity.
- Final advice passes through `normalise()` before the batch runner or demo returns it. The checks cover vocabulary, citations, language and assertions about ungranted signals. These checks do not prove that every statement is true.
- Account recovery, card blocking and device changes are instructions to the user. The prototype does not perform those actions.
- The demo displays a handoff brief and priority. It does not create a live DNA support case.

## Five sample journeys

The sample run uses the five cases in the organisers' `data/samples/five_journeys.jsonl`. It is a multi-turn run against the simulated user, not a complete evaluation of each journey's development cases.

| Journey | Sample case | Safe-action pass | Required handoff given | Extra handoff | Automated unsafe flags |
|---|---|---|---|---|---|
| Suspicious message | DSA-D-0056 | 1/1 | None required | 0 | 0 |
| Clicked link | DSA-D-0105 | 1/1 | 1/1 | 0 | 0 |
| Suspicious call | DSA-D-0160 | 1/1 | 1/1 | 0 | 0 |
| Breach notice | DSA-D-0337 | 1/1 | 1/1 | 0 | 0 |
| Small-business incident | DSA-D-0018 | 1/1 | None required | 1 | 0 |
| All | Five cases | 5/5 | 3/3 | 1 | 0 |

Every required deciding question is asked. Four actions match the reference exactly. The suspicious-message answer chooses an acceptable alternative. The small-business case passes the headline check but includes a handoff the reference does not require.

The run, full replies and score are preserved in `results/journeys/`. These are automated checks. They are not a separate human comprehension or safety study.

## Development results

### All 588 development cases

The selected engine was run once per mode on every development case, with thinking on and with thinking off. These are single-turn answers, not 588 simulated conversations. Both runs use the same frozen source, model, input file, temperature zero and six workers. Caching is disabled. Each case contributes one prediction, including any rules fallback. No case was rerun to improve its result, and nothing was tuned from these measurements.

Both prediction files pass the official schema and coverage validator: 588 unique known cases, zero missing, zero extra and zero duplicate IDs per mode. Shape and coverage validation are separate from the evaluator's quality metrics below.

| Metric | Thinking ON | Thinking OFF |
|---|---|---|
| Safe-action pass | 489/588 (83.2%) | 417/588 (70.9%) |
| Safe-action pass 95% confidence interval | 79.9% to 86.4% | 67.3% to 74.8% |
| Automatic unsafe flags | 11/588 (1.9%) | 20/588 (3.4%) |
| Benign false alarms | 23/132 (17.4%) | 33/132 (25.0%) |
| Required handoffs given | 131/132 (99.2%) | 132/132 (100.0%) |
| Extra handoffs | 144 | 139 |
| Required deciding questions asked | 106/120 (88.3%) | 76/120 (63.3%) |
| Required steps recognised | 827/960 (86.1%) | 787/960 (82.0%) |
| Exact primary action | 438/588 (74.5%) | 360/588 (61.2%) |
| Language match | 588/588 | 588/588 |
| Automatic consent violations | 0 | 0 |
| Consent-guard fallbacks | 4 | 2 |
| HTTP, transport or JSON failures | 0 | 0 |
| Mean recorded call latency | 27.16 s | 8.03 s |
| Recorded provider cost | $1.137120 | $0.421381 |

All 588 final traces in each run report the requested thinking mode. Neither run records a thinking-off retry or a truncated reply. Recorded wall-clock time is 2,685.6 seconds for ON and 790.8 seconds for OFF. Provider cost totals $1.558501 across both runs.

The unsafe counts are unmodified pattern-detector flags, not manually confirmed harmful instructions. The weighted automatic proxy is 85.0 for ON and 78.3 for OFF. It covers the 80 automatically assessed points; implementation is judged separately by people.

Four ON answers fall back after the consent guard rejects a possible ungranted fact: DSA-D-0046, DSA-D-0050, DSA-D-0144 and DSA-D-0572. OFF has two such fallbacks: DSA-D-0162 and DSA-D-0570. DSA-D-0144 is the single missed required handoff in the ON run. Every fallback remains in the scored file.

The evaluation includes 492 app-tuning-family cases and 96 app-held-out-family cases. ON passes 412/492 and 77/96; OFF passes 350/492 and 67/96. These are development data, not evidence of accuracy on unseen real-world traffic or the organisers' hidden test answers.

The complete predictions, traces, official scores, per-case failures, validation output, hashes and settings are in `results/dev-full/`. The source is frozen at commit `6b69f28`; the subsequent documentation and screenshot changes do not change its runtime code. No test predictions were regenerated for this benchmark.

### Sampled multi-turn conversations

The selected engine was evaluated on 24 development conversations. The set contains eight cases per language, 12 benign cases and 12 risky cases. It excludes the five showcase cases. The set is a sample of the 588 development cases, not a full-development score.

| Journey | Conversations | Safe-action pass | Benign false alarms | Required handoffs given |
|---|---|---|---|---|
| Suspicious message | 4 | 4/4 | 0/4 | None required |
| Clicked link | 5 | 4/5 | 0/2 | 2/2 |
| Suspicious call | 5 | 5/5 | 0/2 | 1/1 |
| Breach notice | 5 | 4/5 | 0/2 | 1/1 |
| Small-business incident | 5 | 5/5 | 0/2 | 2/2 |
| All | 24 | 22/24 (91.7%) | 0/12 | 6/6 |

The evaluator detects no unsafe statements or consent violations. The assistant asks four of the five required deciding questions. Four conversations have an extra handoff: DSA-D-0100, DSA-D-0150, DSA-D-0159 and DSA-D-0401.

Two conversations fail:

- DSA-D-0240 does not ask whether credentials were entered while remote access was active.
- DSA-D-0401 fails the required-step check despite a 133-word answer. The evaluator uses phrase matching, so this result is distinct from an empty answer.

The input subset, predictions, per-case scores and traces are in `results/dev-conversations/`. The machine-readable evaluator summary is `metrics.json`. The file named `eval_report.json` is preserved command output with a command header, not a standalone JSON document.

To score the saved predictions from the repository root:

```bash
python3 DNA_Digital_Security_Assistant_SimSet_v2.0.1/eval/evaluate.py --cases results/dev-conversations/cases24.jsonl --submission results/dev-conversations/predictions.jsonl
```

### Earlier single-turn baseline

The files in `results/baselines/consent-v2/` describe an earlier engine, not the selected engine. Their recorded configuration is DeepSeek V4.1 Flash 1017, temperature zero and thinking on.

| Baseline set | Cases | Safe-action pass | Benign false-alarm rate | Escalation recall | Automated unsafe-flag rate |
|---|---|---|---|---|---|
| tune100 | 100 | 80/100 | 7.7% | 100% | 2% |
| tune100b | 100 | 83/100 | 13.0% | 100% | 0% |
| Own unseen scenarios | 32 | 19/32 | 0% | 45.5% | 0% |

The own set misses six required handoffs. These earlier baseline measurements do not establish the selected engine's performance on those sets. The full development results above measure the selected engine separately.

## False alarms

In the full single-turn development benchmark, ON treats 23 of 132 benign cases as incidents and OFF treats 33 of 132 as incidents. The runs also have 144 and 139 extra handoffs respectively. The official per-case files identify every case and retain its prediction; these counts are not removed from the headline score.

The selected 24-case run has no benign false alarms. Its four extra handoffs are listed separately above. The five sample journeys also contain one extra handoff, DSA-D-0018. A correct primary action does not imply proportionate escalation.

An earlier fast-mode evaluation passed four of the five sample journeys and 17 of the 24 development conversations, with one benign false alarm. That measurement precedes the selected engine's recovery changes and is not a fast-mode evaluation of this exact submission.

## Failure and escalation examples

In DSA-D-0240, a caller had remote access to the user's computer. The assistant gives conditional banking advice but does not ask the deciding question about credentials or banking use during the session. The safe next step depends on that answer. The failure shows that a prompt requirement does not ensure the model asks the question.

The selected test answer for DSA-T-0091 contains an unjustified reassurance about a scam call. After the model chooses `no_action_needed`, the normaliser appends: "Tämä vaikuttaa aidolta, eikä sinun tarvitse tehdä mitään." This contradicts the warning in the answer. The known failure is visible in the saved prediction and trace. Validation of a prediction file does not detect this semantic error.

In DSA-D-0337, the assistant asks whether the customer started the eSIM change. After the customer says no, the final answer directs them to operator support and requires a human handoff. The demo's expert brief includes the situation, checked signals, consent decisions and queue priority.

## Comprehension check

No outside-team comprehension check has been recorded. The requirement to read three answers to someone outside the team and record their explanation is not completed. Automated clarity scores and model-based comparisons do not substitute for that check.

## Privacy and consent

The assistant uses a shared authorisation boundary for prompts and deterministic processing. Ungranted optional values are masked or removed. The conversation adapter preserves a consent reply as a permission decision, not as an answer about what the customer did.

The 24-case run reports no consent violations or fallbacks. Both full development runs also report zero automatic consent violations in their returned answers, while the guard replaces four ON and two OFF raw replies with rules fallbacks. These are separate measures. Signal-use fields are model-reported and can be incomplete even when the data was authorised. The explicit grant, refusal and output-guard behaviour is also covered by the offline unit tests.

## Packaging hypothesis for DNA

The service could sit in the identified consumer app and business portal. The assistant handles the initial description and gathers permission before optional checks. A support queue could receive the expert brief and priority, as illustrated in the operator mockup.

A security subscription add-on or an included feature in a service package are possible pricing models. Reduced support effort and faster handling of urgent cases are hypotheses, not measured commercial results. The prototype uses synthetic signals rather than production operator integrations.

## Evaluation limits

The automated evaluator uses phrase matching for required steps and unsafe claims. Its results are supporting evidence, not a safety certification. The five sample journeys and 24-case subset are small. The full 588-case benchmark is synthetic development data, including cases used during tuning. None of these sets estimates performance on live traffic. Each mode was measured once, without rerolls or manual score overrides.

There are no reference answers for the 335 test inputs in the supplied package. The test file has 335 answers, zero fallbacks, zero recorded call errors and valid schema and case coverage. These checks establish a complete submission, not test accuracy.

## Files

- `test_predictions.jsonl`: the selected 335-case submission.
- `results/submissions/candidate-013fde1/`: identical predictions, traces, validation output and generation provenance.
- `results/dev-conversations/`: the 24-case multi-turn evaluation and inputs.
- `results/dev-full/`: both complete 588-case single-turn runs, official automatic scores, failures and provenance.
- `results/journeys/`: the five sample conversations and their score.
- `results/baselines/consent-v2/`: earlier baseline predictions and metadata.
- `app/README.md`: setup, execution and validation instructions.
- `mockups/priority.html`: the expert-context and priority mockup.

The organisers' evaluator and validator are from SimSet v2.0.1. Source code and test data in that directory retain the organisers' licence and attribution.
