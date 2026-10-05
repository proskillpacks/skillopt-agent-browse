# Training a browsing skill with SkillOpt

A worked example of training an agent skill instead of hand-writing it. The skill teaches Claude to browse the web with the [`agent-browser`](https://github.com/vercel-labs/agent-browser) CLI. The method is a scaled-down version of Microsoft's SkillOpt paper ([arXiv 2605.23904](https://arxiv.org/abs/2605.23904)).

**Result in one line:** the trained skill made Opus 5.5 about 14% cheaper per browsing task on unseen tasks, with no change in accuracy, because Opus already solved every task without a skill. Two of the three edit sets I proposed made things worse and were caught by the validation gate.

## What is in this directory

| Path | Contents |
|---|---|
| `skill/agent-browse/SKILL.md` | The trained skill, ready to copy into `~/.claude/skills/` |
| [arXiv 2605.23904](https://arxiv.org/abs/2605.23904) | The SkillOpt paper (not redistributed here) |
| `tests/` | The harness (`run.py`), 32 auto-checked tasks (`tasks.json`), and three local test pages (`fixtures/`) |
| `training/candidates/` | Every skill version: the seed, the accepted one, and the two rejected ones |
| `training/runs/` | Scores (`summary.json`) and a compact trajectory (`traj.txt`) for every rollout |

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

## Running it yourself

Needs `agent-browser`, the `claude` CLI, and Python 3. From `tests/`:

```bash
python3 -m http.server 8791 --bind 127.0.0.1 -d fixtures &

# score a skill on a split (train | sel | test), or on named tasks
python3 run.py --skill ../training/candidates/s1-accepted.md --tasks sel --reps 2 --tag my_run
python3 run.py --skill none --tasks x03,x07 --tag baseline
```

`--skill` takes the skill body as plain markdown; the text is appended to the student's system prompt. Results go to `tests/runs/<tag>/`. A rollout costs about $0.05 with Opus; the whole experiment was roughly $15.

To train further: run the train split, read the `traj.txt` files of the most expensive rollouts, write a candidate with a few edits, score it on `sel`, and keep it only if the score beats the current best (0.9687).

## Licence and credits

MIT for the skill, the harness and the data (see `LICENSE`). The skill drives [`agent-browser`](https://github.com/vercel-labs/agent-browser), which is the work of its authors at Vercel Labs.
