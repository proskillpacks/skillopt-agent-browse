# Training a browsing skill with SkillOpt

## Start here if you want to train your own skill

Open [`starter/`](starter/). It is a small training loop you can run in ten minutes and then change. It needs no browser and no paid model: just Python 3 and either the `claude` command or any local or hosted model with an OpenAI-style endpoint (Ollama, llama.cpp, LM Studio, vLLM). It has 18 toy tasks with automatic checks, a scoring script, a reflection step, a gate that keeps a change only if the score goes up, and a real example run with its numbers. The tutorial walks through the six steps with the command for each: [`starter/README.md`](starter/README.md).

The rest of this page is the write-up of the browsing-skill experiment: Part 1 on Claude Opus, and Part 2 on a local model.

---

A worked example of training an agent skill instead of hand-writing it. The skill teaches Claude to browse the web with the [`agent-browser`](https://github.com/vercel-labs/agent-browser) CLI. The method is a scaled-down version of Microsoft's SkillOpt paper ([arXiv 2605.23904](https://arxiv.org/abs/2605.23904)).

**Result in one line:** the trained skill made Opus 5.5 about 14% cheaper per browsing task on unseen tasks, with no change in accuracy, because Opus already solved every task without a skill. Two of the three edit sets I proposed made things worse and were caught by the validation gate.

**Part 2 in one line:** the same skill was then retargeted at a local model, Qwen3.8-27B driven by the `pi` coding agent. The Opus-trained skill transferred well (selection accuracy 87.5% → 97.9%, tokens down 38%), and one further accepted step tuned for Qwen reached 100% on the selection split with 14% fewer tokens. See [Part 2](#part-2-retargeting-the-skill-at-a-local-model-qwen38-27b).

## What is in this directory

| Path | Contents |
|---|---|
| `skill/agent-browse/SKILL.md` | The skill trained against Opus 5.5, ready to copy into `~/.claude/skills/` |
| `skill/agent-browse-qwen/SKILL.md` | The variant tuned for Qwen3.8-27B (Part 2) |
| [arXiv 2605.23904](https://arxiv.org/abs/2605.23904) | The SkillOpt paper (not redistributed here) |
| `tests/` | The harnesses (`run.py` for Claude, `run_pi.py` for a local model through pi), 32 auto-checked tasks (`tasks.json`), and three local test pages (`fixtures/`) |
| `training/candidates/` | Every skill version: the seed, accepted and rejected ones. `s*` are the Opus run, `q*` the Qwen run |
| `training/runs/` | Scores (`summary.json`) and a compact trajectory (`traj.txt`) for every rollout. Qwen runs are under `training/runs/qwen/` |

## The method

The paper treats a skill like model weights: you train it against data and only keep changes that measurably help.

1. **Freeze the student.** The model that does the tasks never changes. Here it is Opus 5.5 running headless (`claude -p`) with only a Bash tool.
2. **Split the tasks** into train, selection and test. Train tasks supply evidence, selection tasks decide whether an edit is kept, test tasks are touched once at the end.
3. **Roll out.** Run the student on the train tasks with the current skill and record what it did and how it scored.
4. **Reflect.** A separate optimizer model reads the trajectories in batches and proposes edits for patterns that recur across several tasks, not one-off fixes.
5. **Bound the update.** Apply at most a few edits per step (4, then 3, then 2 here). The paper calls this the textual learning rate.
6. **Gate.** Run the candidate skill on the selection tasks. Keep it only if the score is strictly higher. Rejected edits are remembered so they are not proposed again.

### What I scaled down

| | Paper | Here |
|---|---|---|
| Tasks | hundreds per benchmark | 13 train, 8 selection, 11 test |
| Optimizer | a pipeline of analyst, merge and ranking calls | one model (Claude Fable 5.1) reading the trajectories directly |
| Length | 4 epochs | 3 steps, stopped after two rejections in a row |
| Slow/meta update across epochs | yes | not used |
| Score | accuracy | accuracy, plus efficiency credit (see below) |

### The score

Opus got every task right with no skill at all, so accuracy alone gave the gate nothing to measure. Each rollout scores 0 if the answer is wrong; if right, `0.7 + 0.3 × (1 − weighted tokens / 200k)`. Weighted tokens are all input tokens across turns plus five times the output tokens, which tracks what the run costs.

Every candidate was scored on the selection split twice (16 rollouts) to dampen run-to-run noise.

## Results

### Training (selection split, 8 tasks × 2 runs)

| Step | Skill | Edits | Score | Tokens per task | Turns | Decision |
|---|---|---|---|---|---|---|
| 0 | `s0-seed` | 150-word starting skill | 0.9435 | 37.7k | 5.2 | start |
| 1 | `s1` | 4 | 0.9687 | 20.8k | 3.0 | **accepted** |
| 2 | `s2` | 3 more | 0.9644 | 23.8k | 3.2 | rejected |
| 3 | `s3` | 1 more | 0.9632 | 24.5k | 3.0 | rejected |

All runs were 100% correct, so the score differences are entirely efficiency.

### Held-out test (11 unseen tasks × 2 runs)

| Condition | Correct | Tokens per task | Turns per task |
|---|---|---|---|
| No skill | 22/22 | 34.2k | 5.0 |
| Vendor's bundled `core` skill | 22/22 | 109.4k | 5.5 |
| Seed skill | 22/22 | 33.3k | 5.1 |
| **Trained skill** | 22/22 | **29.4k** | **4.1** |

The vendor skill is not in this directory; reproduce it with `agent-browser skills get core`.

## Observations

**The gate did the real work.** All three edit sets came from real trajectories and read as sensible advice. Only the first helped. Without the selection check, the shipped skill would have included both rejected sets and been worse.

**The edits that helped removed waste the student could not have known about.** The four accepted edits:
- batch several commands into one call, and close the browser in the last one;
- do not chain work to `open` with `&&`, because `open` can time out on a stalled load while the page is still usable;
- a recipe for JavaScript dialogs and right-click, which the student otherwise found by grepping `--help`;
- a short command list, so the student stops calling `--help` at all.

**The edit that hurt was a prevention rule.** "Never guess selectors on a page you have not seen" added a snapshot call to tasks where guessing was already working. Advice that sounds prudent can cost more than the failure it prevents.

**A long skill is expensive.** The vendor skill is about 9k tokens and cost roughly three times more per task than no skill, with no accuracy benefit on these tasks. The trained skill is about 700 tokens. Note that I put the vendor skill in the system prompt in full, which is harsher than loading it on demand.

**A strong student leaves little to train.** The paper reports gains of 20 points or more, on benchmarks where the model starts at 30–80%. Here the starting point was 100%. The method is likely worth more for a weaker model or for tasks the model actually fails.

**Fix the harness before trusting any score.** The first baseline looked terrible, and none of it was about browsing:
- five browsers launching at once crashed snap Chromium, which needs a private profile directory per instance;
- students then ran `agent-browser close --all` and closed each other's browsers;
- one test site returned 503 errors on its scripts under parallel load.

The harness now gives each rollout its own namespace, session and profile, and warms the browser up before the student starts.

**Test-set gains were smaller than selection-set gains.** The trained skill cut tokens 45% against the seed on selection but only 12% on test. Some of that is the selection split being the one the gate optimised for, and with two runs per task the test figure is indicative, not precise.

## Limits of this run

- Small task set, mostly public practice sites plus three local pages. No logins to real services, no bot detection, no consent walls beyond one local imitation.
- One student model. Whether the skill helps Sonnet or Haiku is untested.
- The `Setup` section at the end of `SKILL.md` (use a named session, never `close --all`, the snap profile fix) was added by hand from the harness problems above. It did not go through the gate, because the harness handled those things for the student.
- `training/runs/noskill_trsel/summary.json` was scored with an earlier 400k token cap; its token and turn counts are comparable, its `score` field is not.

## Part 2: retargeting the skill at a local model (Qwen3.8-27B)

Part 1 ended on "a strong student leaves little to train". Part 2 swaps in a weaker student to see how much more the method gives.

### Setup

| Role | Part 1 | Part 2 |
|---|---|---|
| Student (does the browsing, never edits the skill) | Opus 5.5 via `claude -p` | Qwen3.8-27B on a local OpenAI-compatible endpoint, via `pi -p` |
| Optimizer (reads trajectories, writes edits) | Claude Fable 5.1 | Claude Fable 5.1 |
| Judge | regex check in the harness | the same |
| Starting skill | 150-word seed | `s1`, the skill accepted in Part 1 |

`tests/run_pi.py` is `run.py` with the student swapped. Same tasks, prompt, splits and score. Differences forced by pi:
- pi has no `--max-turns`, so each rollout has a 15-minute wall-clock limit instead; a timeout scores 0.
- pi cannot block `curl`/`wget` at the tool layer, so a rollout that uses them is scored wrong.
- Tokens are summed from pi's per-message usage. Turn counts are assistant messages, which is close to but not identical to Claude Code's `num_turns`.

The model is registered in `~/.pi/agent/models.json` as provider `ignis`:

```json
"ignis": {
  "baseUrl": "http://<host>:8000/v1", "api": "openai-completions", "apiKey": "<key>",
  "models": [{ "id": "qwen3.8-27b", "reasoning": true, "input": ["text", "image"],
    "contextWindow": 131072, "maxTokens": 32768,
    "compat": { "thinkingFormat": "qwen", "requiresAssistantAfterToolResult": true } }]
}
```

### Results on the selection split

Rollouts are free on a local model, so every candidate got 6 runs per task (48 rollouts) instead of 2.

| Skill | Edits | Correct | Score | Tokens per task | Turns | Decision |
|---|---|---|---|---|---|---|
| No skill (24 rollouts) | | 21/24 | 0.7887 | 68.7k | 13.9 | |
| `s1` (Opus-trained) | | 47/48 | 0.9177 | 42.3k | 9.2 | start |
| `q1` | 4 | 43/48 | 0.8367 | 42.0k | 8.3 | rejected |
| `q2` | `q1` with one edit swapped | 48/48 | **0.9454** | **36.4k** | 8.5 | **accepted** |
| `q3` | 4 more | 47/48 | 0.9215 | 39.4k | 8.1 | rejected |
| `q4` | 2 of the `q3` edits | 44/48 | 0.8542 | 47.0k | 9.1 | see note |

`q4` note: three of its four failures were 15-minute timeouts on the 50-page catalogue crawl (`s08`), after `books.toscrape.com` began answering 403 under four concurrent crawls. That is the benchmark throttling, not the skill. A serial re-run of `s08` for `q2` and `q4` is recorded under [Held-out test](#held-out-test-qwen).

For reference, Opus with `s1` on the same split: 16/16 correct, 0.9687, 20.8k tokens, 3.0 turns. The tuned skill brings Qwen level with Opus on accuracy here, but Qwen still needs nearly three times the turns and about 75% more tokens.

On the train split `q2` and `s1` were level (0.9436 vs 0.9484, both 39/39), so the selection gain is not confirmed there.

### Held-out test (Qwen)

_The test-split runs (no skill, `s1`, `q2`; 11 tasks × 3 runs, one rollout at a time) and the serial `s08` re-run were still in progress when this section was written._

### What the edits were

Accepted in `q2`, all on top of `s1`:
- **Never invent what you have not seen.** Qwen made up deep URLs that returned 404 and ids and classes that did not exist (`#hogwarts`, `select.tag_search`), then spent turns recovering. The rule: start from the given URL, follow the site's links, and look at the page before writing a selector.
- **Selector syntax.** It kept using Playwright-style `text=` and `:has-text()`, which `agent-browser` rejects. The skill names `find text "…" click` instead.
- **Pass longer JavaScript on stdin.** Shell quoting around `eval` cost two or three turns in several rollouts.
- **Pagination check.** The one recurring wrong answer: Qwen looked for a pager with a guessed selector, found nothing, and reported a 26-book category as 20. The rule: compare what you collected with the page's own total, and find the next link by its text.
- **Do not `close` early.** It chained `close` onto commands whose output it still needed.

Rejected:
- **"When the output contains the answer, reply at once."** (`q1`) Meant to stop re-verification. The candidate carrying it failed the pagination task more often, and it was the one edit swapped out to make `q2`.
- **Retry `open` in a loop until it succeeds.** (`q3`) Aimed at loads where the page arrives without its scripts. The candidate carrying it made the 50-page crawl about 50% more expensive.
- **Custom dropdowns: `select` only works on a real `<select>`.** (`q3`) Qwen hit this on every run of one train task, but no selection task exercises it, so the gate could not reward it.
- **Always quote selectors; wrap `eval` scripts in a function.** (`q3`, `q4`) Both prevent real errors seen in trajectories (`click #go` loses its argument to a shell comment; top-level `const` persists between evals). Neither moved the selection score.

Edits were gated in bundles, so the per-edit attributions above are my reading of the trajectories, not measured effects.

### Observations

**A skill is tuned to the model that reads it.** The clearest case is one rule that changed sign. "Never guess selectors on a page you have not seen" was rejected in Part 1: Opus's guesses were usually right, so the rule only added a snapshot call. Qwen's guesses are often wrong, and the accepted Qwen skill contains a version of that rule. Advice that is waste for one model is error prevention for another.

**The failure modes differ in kind.** Every accepted Opus edit removed waste from runs that already succeeded. The Qwen edits prevent errors: wrong selector dialect, broken shell quoting, concluding a list is complete when it is not.

**Most of the value transferred.** The Opus-trained skill alone took Qwen from 87.5% to 97.9% correct and cut tokens by 38%, a far larger effect than it had on Opus. The Qwen-specific step added a smaller increment on top. That argues for a shared core plus a thin model-specific layer, not a separate skill per model.

**A skill helps a weaker model more.** On selection, training moved Opus's score by 0.025 (seed 0.944 → trained 0.969, accuracy unchanged at 100%). For Qwen, no skill to tuned skill is 0.157 (0.789 → 0.945), with accuracy going from 87.5% to 100%. The baselines differ (seed vs no skill), so this is a rough comparison, but it matches the paper's claim that gains are largest where the model starts lower.

**Noise limits how far you can tune.** Three of four Qwen candidates were rejected. The `q2` margin over `s1` (0.945 vs 0.918) is one failed rollout in 48 plus a 14% token saving, and a second batch of `s1` runs alone scored 0.941. After the first accepted step, the remaining gains were smaller than the run-to-run variation of this benchmark.

**The benchmark sites were the bottleneck, not the model.** Qwen answers in under a second per turn; almost all wall time was page loads and 25-second `wait` timeouts. Four rollouts at once made `the-internet.herokuapp.com` return 503 on its scripts and `books.toscrape.com` return 403. The selection numbers above were measured at four-way concurrency and carry that noise; the test split was run one rollout at a time.

### Limits of Part 2

- The cross-check was not run: `q2` on Opus. If the Qwen-tuned skill makes Opus slower than `s1` does, that would be direct evidence for model-specific tuning. Until then the sign-flip above rests on two separately gated bundles.
- One local model, one quantisation, one harness (pi). Thinking was left at pi's default.
- Selection scores were measured under site throttling (see above).
- `skill/agent-browse-qwen/SKILL.md` is `q2` plus the same hand-added `Setup` section as the Opus skill; that section did not go through the gate.

## Running it yourself

Needs `agent-browser`, the `claude` CLI, and Python 3. From `tests/`:

```bash
python3 -m http.server 8791 --bind 127.0.0.1 -d fixtures &

# score a skill on a split (train | sel | test), or on named tasks
python3 run.py --skill ../training/candidates/s1-accepted.md --tasks sel --reps 2 --tag my_run
python3 run.py --skill none --tasks x03,x07 --tag baseline
```

For a local model through pi (needs `pi` with the model registered, see Part 2):

```bash
python3 run_pi.py --skill ../training/candidates/q2-qwen-accepted.md --tasks sel --reps 6 --par 1 --tag my_qwen_run
python3 run_pi.py --skill none --tasks test --reps 3 --par 1 --model ignis/qwen3.8-27b --tag qwen_baseline
```

Use `--par 1` or `2`; higher concurrency gets the practice sites to throttle. Start the fixture server detached (`setsid nohup python3 -m http.server ... &`) so it survives the shell that launched it.

`--skill` takes the skill body as plain markdown; the text is appended to the student's system prompt. Results go to `tests/runs/<tag>/`. A rollout costs about $0.05 with Opus; the whole experiment was roughly $15.

To train further: run the train split, read the `traj.txt` files of the most expensive rollouts, write a candidate with a few edits, score it on `sel`, and keep it only if the score beats the current best (0.9687).

## Licence and credits

MIT for the skill, the harness and the data (see `LICENSE`). The skill drives [`agent-browser`](https://github.com/vercel-labs/agent-browser), which is the work of its authors at Vercel Labs.
