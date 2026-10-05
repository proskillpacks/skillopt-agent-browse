# Train your own skill: a ten-minute starter

This folder is a small, working training loop for an agent skill. It needs no browser, no paid model and nothing outside Python 3. You can run it against Claude, or against any model on your own machine (Ollama, llama.cpp, LM Studio, vLLM) or a hosted API.

It is a scaled-down version of the method in Microsoft's SkillOpt paper ([arXiv 2605.23904](https://arxiv.org/abs/2605.23904)). The bigger worked example in this repo (a browsing skill) is in the main [README](../README.md). This one is built to be run, read and changed.

## What a skill is

A skill is a short markdown file of instructions. A model reads it before it does a task. It might say "dates go in this format" or "check the totals before you answer". Most people write skills by hand and try them on a few examples. The problem: advice that sounds sensible can make results worse, and without a score you never notice.

Training a skill means treating the file like something you tune. You keep the model fixed, you score the model on a set of tasks, you change the file, and you keep the change only if the score goes up on tasks the change was not made from.

## Try it in ten minutes

You need Python 3.8 or newer, and one of these:

- the `claude` command line tool (default; the example below uses `claude -p --model haiku`), or
- any OpenAI-compatible chat server: `export STUDENT_MODEL=<name> OPENAI_BASE_URL=http://localhost:11434/v1` (Ollama's default) and add `--adapter openai` to every command below.

```bash
cd starter
python3 tasks/make_tasks.py            # optional: rebuilds tasks/tasks.json from the reference solvers
python3 run.py --skill none --split sel --tag baseline --model haiku
```

You should see mostly `FAIL`. The toy tasks ask for our "house style" (date formats, id padding, file names) and never say what it is. A model cannot guess it. That is the point: the skill is where you write your conventions down, and training is how you find out which lines of the skill actually carry weight.

## The six steps, with the command for each

**1. Freeze the student.** The student is the model that does the tasks. Pick one and never change it during training. `run.py` takes `--adapter claude|openai` and `--model`. Everything below uses the same student.

**2. Split the tasks.** `tasks/tasks.json` has 18 tasks: three families (invoice note to JSON, rewrite a note in house format, build a document filename), six each, two per family in each split. `train` is for learning, `sel` (selection) decides what is kept, `test` is touched once at the end. Do not look at selection or test answers while you write the skill.

**3. Roll out.** Score the current skill on the train split:

```bash
python3 run.py --skill skill/seed.md --split train --tag seed-train --model haiku
```

Each rollout runs in a fresh empty working directory, and its prompt, reply and a compact `traj.txt` (task, expected, got) are saved under `runs/<tag>/`. The checker is plain code (`check.py`), so the same reply always gets the same score.

**4. Reflect.** Look at what failed. Either read it yourself:

```bash
python3 reflect.py runs/seed-train
```

or ask an optimizer model for at most N edits (any adapter, and it can be a stronger model than the student):

```bash
python3 reflect.py runs/seed-train --skill skill/seed.md --ask --max-edits 4 --model sonnet
```

It prints every failure plus the most expensive successes, then the proposal. It also saves `runs/seed-train/proposal.md`. A person or a script saves the revised skill into `candidates/`. Only use train runs here: the trajectories show the expected answers.

**5. Bound the update.** The `--max-edits` number is the "textual learning rate". Few edits per step means that when the gate says no, you know which idea to blame. Ask for rules that explain a pattern across several failures, not a fix for one task, and keep the examples out of the skill.

**6. Gate.** Run the candidate on the selection split, more than once, and compare with the best skill so far:

```bash
python3 gate.py candidates/c1.md --best skill/seed.md --reps 2 --model haiku
```

It prints the two scores and `ACCEPT` (strictly higher) or `REJECT`. A rejected candidate has its added lines appended to `rejected.md`, and `reflect.py --ask` shows that file to the optimizer so it does not suggest the same thing again. Accepting records the candidate as the new best in `best.json`. Then loop: roll out the new best on train, reflect, gate. When you stop, run the test split once:

```bash
python3 run.py --skill candidates/c1.md --split test --reps 2 --tag test-c1 --model haiku
```

## The example run (real numbers)

Student: `claude -p --model haiku`. Optimizer: `claude -p --model sonnet`. The files are in `example-run/`.

| Skill | Selection (6 tasks x 2) | Test (6 tasks x 2) |
|---|---|---|
| No skill | 0 of 6 (one run) | 0 of 12 |
| Seed (two lines: reply with only the answer, follow house conventions) | 0 of 12 | 0 of 12 |
| Candidate `c1` (215 words, one reflection step, 4 edits) | **10 of 12** (accepted) | **10 of 12** |

Reading it honestly:

- The seed scored zero. Without the conventions in front of it, the model either asked "what is your house style?" or guessed. The seed was too thin to give the gate a gradient, so this run has one step from 0 to 83%, not a climb.
- The optimizer wrote almost all the rules from six training trajectories. The gate accepted it because the rules carried over to tasks it had not seen: 10 of 12 on selection and the same on test.
- Four failures out of 24 held-out runs, each a small slip: a trailing full stop dropped, "2 April" kept instead of "02 Apr", the word "final" dropped from a file name, "sg" instead of "sgreene". The date one is a rule the skill does state, and the model still slipped.
- There was only one candidate. We did not show a rejection here, because none happened. The browsing example in the main README has two.
- Optimizer note: the proposal pasted some training examples (`Jane Smith -> jsmith`, `Acme Widgets Ltd`) into the skill, against our own instruction. None of them is a selection or test input, but it is a leak risk you should watch for in your own runs.
- Small numbers: 12 rollouts per cell. A swing of one task is 8 points. Do not read the 10 of 12 as a precise accuracy.

**Adapter (b), a real local model.** The OpenAI-compatible adapter was tested against a real local server: Ollama on this machine, model `qwen3.8:27b` (a 27B model, 4-bit), no key. With no skill it got 0 of 18 tasks right (all splits, one run each; the answers were wrong in the house-style details, not broken calls). With the same `c1` skill that was trained on Haiku, it got 5 of 6 on the test split (one run each). That is a quick check, not a second experiment: one run, 6 tasks, and the skill was never tuned for that model. Each rollout took 20 to 55 seconds on one GPU, with three running at once.

Cost: 84 Haiku rollouts and one optimizer call, about $1.50 in total with Claude Haiku and Sonnet through the CLI. About $0.015 a rollout, most of it the CLI's own system prompt. A local model costs electricity only.

## How to write a good task and checker

- **One right answer, checked by code.** Exact text, or JSON compared as an object. If you need a person to judge the result, the loop still works but is slower and noisier.
- **Make the task hard for the right reason.** Several rules at once, a strict output shape, a convention the model cannot guess. If a plain model passes everything, the gate has nothing to measure.
- **Keep the rules out of the task text.** The rules belong to the skill. The task gives the input and the output shape.
- **Make every rule show up in more than one task**, in different words, so the skill learns the rule and not the example.
- **Write a reference solver** that produces the expected answer, as `tasks/make_tasks.py` does. It proves the task can be solved, and it keeps the answers consistent when you edit the inputs.
- **Put similar tasks in every split.** The selection tasks should need the same rules as the train tasks, with new inputs.
- Be strict about output format only if a program will consume it. Here no code fences and no extra words are allowed, because pipelines break on them.

## Choosing a score when accuracy is already 100%

If the student gets every task right with no skill, accuracy cannot tell candidates apart. Then score cost as well. `--score eff` gives a wrong answer 0 and a right answer `0.7 + 0.3 x (1 - tokens / cap)`, with tokens counted as all input plus five times the output, and cap set in `run.py`. Correctness still dominates. The browsing example in the main README ran on that score: every run was correct, and the gate found a skill that did the same work with 45% fewer tokens on selection.

## How many repeats, and why

Models are not deterministic, even at low temperature. One run per task makes a coin toss look like a result. Run the selection split at least twice (`--reps 2`), more if the tasks are few. Run the same number for the best skill and the candidate, which `gate.py` does. With 6 tasks and 2 repeats, one task flipping is 8 points: treat any difference under that as noise, and prefer to repeat the gate before you accept a close one. Run the test split once at the end, and do not tune on it afterwards.

## Three mistakes the original run made

All three were in the harness, not the skill, and all three made the first baseline look terrible:

1. Five browsers launched at the same time crashed the browser. Each rollout needs its own profile, and risky start-up work should be done one at a time.
2. The student ran a "close all" command and closed the other students' browsers. Rollouts must be isolated: own directory, own session, nothing shared.
3. A test website returned 503 errors under parallel load, which looked like a skill failure. Check that a task passes alone before you blame the skill, and use local pages or a local server when you can.

The same lesson applies here: before you trust a score, read a few `traj.txt` files and check that a failure is a real failure. We do that on the first baseline and we put `FAIL` rows with an error message in `runs/*/summary.json` (`error` field) so a broken server is not mistaken for a bad skill.

## Swapping in a local model

```bash
ollama pull qwen3.8:27b                 # or any model you have
export STUDENT_MODEL=qwen3.8:27b
export OPENAI_BASE_URL=http://localhost:11434/v1   # Ollama default; LM Studio: http://localhost:1234/v1; llama.cpp: http://localhost:8080/v1
export OPENAI_API_KEY=...                           # only if your server wants one
python3 run.py --skill none --split sel --tag local-baseline --adapter openai --par 2
```

Use `--par 1` or `--par 2` on a single GPU. Optional: `STUDENT_TEMPERATURE` (default 0.2) and `STUDENT_EXTRA`, a JSON object merged into the request body (for example to switch off a thinking mode). To use another kind of model, copy `OpenAICompatible` in `adapters.py`: one class with a `complete(system, user)` method returning text and token counts.

## What this is not

This is not the paper's full pipeline. There is no separate analyst, merge and ranking stage: one optimizer call reads the trajectories directly. There is no slow or meta update across epochs. The task set is 18 toy tasks. The proposal-to-candidate step is manual on purpose, so you read every change. If you need the full method, read the paper.

## Files

| Path | What it is |
|---|---|
| `run.py` | Scores a skill on a split with a pluggable student |
| `adapters.py` | The two adapters: `claude -p` and OpenAI-compatible URL |
| `check.py` | The deterministic checkers (exact text, JSON) |
| `tasks/tasks.json`, `tasks/make_tasks.py` | The 18 tasks and the reference solvers that make them |
| `skill/seed.md`, `candidates/` | The starting skill and every later version |
| `reflect.py`, `gate.py`, `rejected.md`, `best.json` (made by the first accepted gate) | Step 4, step 6, the memory of rejected ideas, the current best |
| `example-run/` | The real run described above |
