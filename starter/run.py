#!/usr/bin/env python3
"""Score a skill file on a task split with a pluggable student.
usage: run.py --skill skill/seed.md|none --split train|sel|test|all|id,id --reps 1 --tag NAME [--adapter claude|openai --model M]
Results: runs/<tag>/summary.json and one folder per rollout (prompt, reply, traj.txt)."""
import argparse, json, pathlib, sys, time, concurrent.futures as cf
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from adapters import get_adapter
from check import check

TASKS = json.load(open(HERE / "tasks" / "tasks.json"))
TOK_CAP = 50_000  # weighted tokens at which the efficiency credit reaches 0 (only used with --score eff)


def score(correct, wtok, mode):
    if not correct:
        return 0.0
    return 1.0 if mode == "acc" else 0.7 + 0.3 * max(0.0, 1 - wtok / TOK_CAP)


def rollout(task, skill, adapter, outdir, rep, mode):
    wd = outdir / f"{task['id']}_r{rep}"
    wd.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    r = adapter.complete(skill, task["prompt"])
    ok = check(task, r["text"]) and not r.get("error")
    wtok = r["in_tok"] + 5 * r["out_tok"]  # weighted tokens: output counts five times
    res = dict(id=f"{task['id']}_r{rep}", task=task["id"], family=task["family"], correct=bool(ok),
               score=round(score(ok, wtok, mode), 3), wtok=wtok, cost=round(r["cost"], 4), secs=round(time.time() - t0, 1),
               error=r.get("error", ""))
    (wd / "reply.txt").write_text(r["text"])
    (wd / "result.json").write_text(json.dumps(res))
    exp = task["expected"] if task["kind"] == "exact" else json.dumps(task["expected"])
    (wd / "traj.txt").write_text(f"TASK {task['id']} ({task['family']}): {task['prompt']}\n\nEXPECTED:\n{exp}\n\nGOT:\n{r['text'].strip()}\n\n"
                                 f"RESULT: {'OK' if ok else 'FAIL'} wtok={wtok} {r.get('error', '')}\n")
    return res


def run_split(skill_path, split, reps, tag, adapter_name="claude", model=None, par=4, mode="acc"):
    skill = "" if skill_path == "none" else pathlib.Path(skill_path).read_text()
    adapter = get_adapter(adapter_name, model)
    tasks = [t for t in TASKS if split == "all" or t["split"] == split] or [t for t in TASKS if t["id"] in split.split(",")]
    out = HERE / "runs" / tag
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(t, rep) for rep in range(1, reps + 1) for t in tasks]
    with cf.ThreadPoolExecutor(par) as ex:
        rs = list(ex.map(lambda j: rollout(j[0], skill, adapter, out, j[1], mode), jobs))
    n = len(rs)
    summ = dict(tag=tag, skill=str(skill_path), split=split, student=f"{adapter_name}:{getattr(adapter, 'model', '')}", reps=reps, n=n,
                acc=round(sum(r["correct"] for r in rs) / n, 3), score=round(sum(r["score"] for r in rs) / n, 4),
                wtok=round(sum(r["wtok"] for r in rs) / n), cost=round(sum(r["cost"] for r in rs), 3), results=rs)
    (out / "summary.json").write_text(json.dumps(summ, indent=1))
    return summ


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", required=True, help="skill file, or 'none'")
    ap.add_argument("--split", default="sel")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--adapter", default="claude", choices=["claude", "openai"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--par", type=int, default=4)
    ap.add_argument("--score", default="acc", choices=["acc", "eff"])
    a = ap.parse_args()
    s = run_split(a.skill, a.split, a.reps, a.tag, a.adapter, a.model, a.par, a.score)
    for r in s["results"]:
        print(f"{r['id']:8} {'OK  ' if r['correct'] else 'FAIL'} wtok={r['wtok']} {r['secs']}s {r['error']}")
    print(f"== {a.tag}: student={s['student']} n={s['n']} acc={s['acc']} score={s['score']} wtok={s['wtok']} cost=${s['cost']}")


if __name__ == "__main__":
    main()
