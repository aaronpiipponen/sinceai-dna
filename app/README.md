# app: DNA Digital Security Assistant engine

The engine, model client, batch runner, multi-turn adapter, web demo and lab
for the Since AI 2026 DNA challenge. Python 3.10 or later, standard library
only.

Run every command from the repository root.

| File | Role |
|---|---|
| `dna.py` | Assistant engine: prompt, model call, schema normalisation, rules fallback |
| `chat.py` | Plain chat loop against Featherless |
| `batch.py` | Batch runner over a JSONL case file |
| `turns.py` | Multi-turn adapter: `step(event, state)` for the simulator and demo |
| `server.py` | Web server for `/` and `/lab` |
| `present.py` | Server-side `display` block for the demo |
| `gating.py` | Per-message stop, closed-chat and repeat gates |
| `handoff.py` | Expert brief for an escalated conversation |
| `split.py` | Deterministic tune and held-out split of dev cases |
| `replay.py` | Re-run `normalise()` over saved predictions or cached replies |
| `score.py` | Score a predictions file against tune, holdout and the five journeys |

## Setup

Create the local environment file from the template:

```bash
cp app/.env.example app/.env
```

Set `FEATHERLESS_API_KEY` in `app/.env`. The client reads the file at process
start, and a real environment variable takes precedence over the file.
`FEATHERLESS_MODEL` defaults to `deepseek-ai/DeepSeek-V4.1-Flash-1017` and
`FEATHERLESS_BASE_URL` defaults to `https://api.featherless.ai/v1`.

`app/.env` is git-ignored. Do not commit it.

## Web demo

```bash
python3 app/server.py --host 127.0.0.1 --port 8000
```

Open `http://localhost:8000`. The demo at `/` has the five sample journeys,
free text, the optional attachment form, consent cards, answer cards and the
expert brief.

Fast replies are the default. The careful-check toggle on the start screen
sets the conversation's `thinking` flag: off sends `thinking: false`, on sends
`thinking: true` and can take 25 to 60 seconds per reply. Reasoning text is
never returned to the page.

The lab at `/lab` picks dev cases, runs or steps conversations, compares the
answer with the reference and reads per-turn traces. It is available when
public mode is off, and `/` has no link to it.

## Offline tests

```bash
python3 -m unittest discover -s app -t app -p 'test_*.py'
```

The suite has 104 tests and makes no model calls.

## Validate the 335 test predictions

```bash
python3 DNA_Digital_Security_Assistant_SimSet_v2.0.1/tools/validate.py --submission results/submissions/candidate-013fde1/test_predictions.jsonl --cases DNA_Digital_Security_Assistant_SimSet_v2.0.1/data/test/inputs.jsonl
```

The saved run reports `335 lines, 335 cases covered, 0 missing` and `OK`.
Validation reads local files only.

## Score the saved 24-case dev run

```bash
python3 DNA_Digital_Security_Assistant_SimSet_v2.0.1/eval/evaluate.py --cases results/dev-conversations/cases24.jsonl --submission results/dev-conversations/predictions.jsonl
```

The saved run used `deepseek-ai/DeepSeek-V4.1-Flash-1017`, temperature 0 and
thinking on. It scored 24 cases with a 91.7 % safe-action pass and 0.0 %
unsafe statements. The command reads local files only.

The 24 cases are a broader-dev regression sample. They do not cover the 588
dev cases. The machine-readable report is `results/dev-conversations/metrics.json`.
The `eval_report.txt` and `eval_report.json` files are captured command output.
The `results/journeys/` folder holds the five-journey conversation output and
its score report.

## Score the saved 588-case development runs

Both commands read saved predictions and make no model calls:

```bash
python3 DNA_Digital_Security_Assistant_SimSet_v2.0.1/eval/evaluate.py --cases DNA_Digital_Security_Assistant_SimSet_v2.0.1/data/dev/cases.jsonl --submission results/dev-full/on/predictions.jsonl
python3 DNA_Digital_Security_Assistant_SimSet_v2.0.1/eval/evaluate.py --cases DNA_Digital_Security_Assistant_SimSet_v2.0.1/data/dev/cases.jsonl --submission results/dev-full/off/predictions.jsonl
```

Each file covers all 588 cases. ON scores 489/588 and OFF scores 417/588 on
the automatic safe-action check. These are single-turn development scores,
not the multi-turn sample or an official test score. The settings, validation,
flags and fallback cases are documented in `results/dev-full/README.md`.

## Generate predictions (paid)

> [!WARNING]
> This command calls the configured Featherless model. Each call is billed to
> that key. The example writes `/tmp/dna-predictions.jsonl` and leaves the
> submission file untouched.

```bash
python3 app/batch.py --inputs DNA_Digital_Security_Assistant_SimSet_v2.0.1/data/dev/cases.jsonl --limit 5 --thinking on --temperature 0 --out /tmp/dna-predictions.jsonl
```

`--out` receives one JSON object per case. Add `--resume` to skip case ids
already present, `--workers` to set concurrency, or `--no-llm` for the rules
baseline with no model calls.

## Sample multi-turn conversation (paid)

```bash
DNA_THINKING=on python3 DNA_Digital_Security_Assistant_SimSet_v2.0.1/sim/run_conversation.py --cases DNA_Digital_Security_Assistant_SimSet_v2.0.1/data/samples/five_journeys.jsonl --bot-py app/turns.py:step --out /tmp/dna-multiturn.jsonl --show
```

The simulator sends one event per turn and expects one reply of type
`question`, `consent_request` or `final`. `--show` prints each transcript.
The run calls the model for every assistant turn and is billed to the same
key.

## Public demo tunnel

```bash
scripts/public_up.sh
scripts/public_status.sh
scripts/public_down.sh
```

`public_up.sh` starts the demo server on loopback and publishes it through a
Cloudflare quick tunnel, then prints the `https://` URL. `public_status.sh`
reports the server, tunnel and URL, and exits 0 when both are up.
`public_down.sh` stops the processes recorded by `public_up.sh`.

`cloudflared` must be installed for the platform, or `CLOUDFLARED` must point
to the binary. The scripts look at `CLOUDFLARED`, then `PATH`, then
`~/.local/bin/cloudflared`. `PORT` defaults to 8780 and `DNA_PUBLIC_STATE`
defaults to `/tmp/opencode/public`.

`public_up.sh` starts the server with `DNA_PUBLIC=1` and refuses to publish
unless `/lab` and `/api/lab/cases` answer 404. In public mode the server
returns 404 for `/lab`, `/lab/*`, `/api/lab/*` and `/api/review`, adds no
`lab` trace to a reply, and rejects a `source: "dev"` conversation start.
The public URL accepts conversations, and each model-backed reply is billed
to the configured Featherless key.

## How an answer is produced

1. `visible()` removes `ground_truth`, `simulation`, family ids, tags and
   titles from a case. A consent-gated signal reaches the prompt only when it
   is pre-granted or granted in the conversation.
2. `prompt()` asks for one JSON object with the action vocabulary, question
   topics, escalation targets and guidance ids.
3. `normalise()` checks action, risk and urgency values, advice language,
   citations, topics and signal paths. It repairs invalid fields or uses the
   rules fallback, removes ungranted paths from `signals_used`, and rejects
   advice that asserts an ungranted protected fact.
4. If the call fails or returns no JSON, `fallback()` answers from the rules
   baseline, so a batch run always writes one answer per case.
