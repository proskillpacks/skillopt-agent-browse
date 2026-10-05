#!/usr/bin/env python3
"""Show the failed and most expensive trajectories of a run in a compact form; optionally ask the optimizer model
for at most N edits.
usage: reflect.py runs/<tag> [--skill skill/seed.md] [--show 6] [--ask --max-edits 3 [--adapter claude --model sonnet]]
Use runs on the TRAIN split only: the trajectories include the expected answers."""
import argparse, json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from adapters import get_adapter


def pick(run, n):
    rs = json.load(open(run / "summary.json"))["results"]
    bad = [r for r in rs if not r["correct"]]
    good = sorted((r for r in rs if r["correct"]), key=lambda r: -r["wtok"])
    return (bad + good)[:max(n, len(bad))]  # every failure, then the most expensive successes up to n


def compact(run, r):
    t = (run / r["id"] / "traj.txt").read_text()
    return f"--- {r['id']} {'OK' if r['correct'] else 'FAIL'} wtok={r['wtok']}\n{t.strip()}\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run"); ap.add_argument("--skill"); ap.add_argument("--show", type=int, default=6)
    ap.add_argument("--ask", action="store_true"); ap.add_argument("--max-edits", type=int, default=3)
    ap.add_argument("--adapter", default="claude"); ap.add_argument("--model", default="sonnet")
    a = ap.parse_args()
    run = pathlib.Path(a.run)
    text = "\n".join(compact(run, r) for r in pick(run, a.show))
    print(text)
    if not a.ask:
        return
    skill = pathlib.Path(a.skill).read_text() if a.skill else ""
    rejected = (HERE / "rejected.md").read_text()
    prompt = f"""You improve a skill file: short markdown instructions that a fixed student model reads before it does a task.
Below are the current skill, trajectories from running the student on training tasks (with the expected answers), and ideas that were already tried and rejected.

Propose AT MOST {a.max_edits} edits to the skill. Rules:
- Only propose a rule that explains a pattern across two or more of the trajectories, not a one-off fix for a single task.
- Each rule must be general: do not paste task inputs or expected answers into the skill.
- Do not repeat anything in the rejected list.
- Keep the skill short. Prefer replacing a vague line to adding a new one.
Answer with the complete revised skill in one fenced markdown block, then a numbered list of the edits (one line each, say which trajectories motivate it).

CURRENT SKILL:
{skill}

REJECTED IDEAS:
{rejected}

TRAJECTORIES:
{text}"""
    r = get_adapter(a.adapter, a.model).complete("", prompt)
    if r.get("error"):
        sys.exit("optimizer call failed: " + r["error"])
    print("=" * 70 + "\nPROPOSAL (review it, then save the revised skill into candidates/):\n" + r["text"])
    (run / "proposal.md").write_text(r["text"])


if __name__ == "__main__":
    main()
