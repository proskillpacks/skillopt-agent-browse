#!/usr/bin/env python3
"""Run a candidate skill on the selection split R times and compare with the current best.
usage: gate.py candidates/c1.md [--reps 2] [--best skill/seed.md] [--adapter ... --model ...]
Accepts only if the mean score is strictly higher than the best's on the same split and repeats.
The state lives in best.json (best skill and the run that scored it). Rejected ideas go to rejected.md."""
import argparse, difflib, json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run import run_split

STATE = HERE / "best.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate"); ap.add_argument("--reps", type=int, default=2); ap.add_argument("--best")
    ap.add_argument("--adapter", default="claude"); ap.add_argument("--model"); ap.add_argument("--par", type=int, default=4)
    ap.add_argument("--score", default="acc", choices=["acc", "eff"])
    a = ap.parse_args()
    state = json.load(open(STATE)) if STATE.exists() else {}
    best = a.best or state.get("skill")
    if not best:
        sys.exit("no best skill yet: pass --best skill/seed.md for the first gate")
    stem = lambda p: pathlib.Path(p).stem
    if state.get("skill") == best and state.get("reps") == a.reps and state.get("score_mode") == a.score:
        bs = json.load(open(HERE / "runs" / state["tag"] / "summary.json"))
    else:
        bs = run_split(best, "sel", a.reps, f"gate-best-{stem(best)}", a.adapter, a.model, a.par, a.score)
    cs = run_split(a.candidate, "sel", a.reps, f"gate-{stem(a.candidate)}", a.adapter, a.model, a.par, a.score)
    print(f"best      {best}: score={bs['score']} acc={bs['acc']} wtok={bs['wtok']} (n={bs['n']})")
    print(f"candidate {a.candidate}: score={cs['score']} acc={cs['acc']} wtok={cs['wtok']} (n={cs['n']})")
    if cs["score"] > bs["score"]:
        print("ACCEPT: strictly higher. Make it the new best.")
        STATE.write_text(json.dumps(dict(skill=a.candidate, tag=f"gate-{stem(a.candidate)}", reps=a.reps, score_mode=a.score, score=cs["score"]), indent=1))
    else:
        print("REJECT: not strictly higher. Logged to rejected.md.")
        old = pathlib.Path(best).read_text().splitlines(); new = pathlib.Path(a.candidate).read_text().splitlines()
        added = [l[1:] for l in difflib.unified_diff(old, new, lineterm="", n=0) if l.startswith("+") and not l.startswith("+++")]
        with open(HERE / "rejected.md", "a") as f:
            f.write(f"\n## {a.candidate} (score {cs['score']} vs best {bs['score']})\n" + "\n".join(f"- {l}" for l in added if l.strip()) + "\n")
        if not STATE.exists():  # keep the first best, so repeated gates do not re-run it
            STATE.write_text(json.dumps(dict(skill=best, tag=f"gate-best-{stem(best)}", reps=a.reps, score_mode=a.score, score=bs["score"]), indent=1))


if __name__ == "__main__":
    main()
