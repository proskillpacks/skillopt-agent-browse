#!/usr/bin/env python3
"""SkillOpt-style rollout harness: frozen student (claude -p, Opus) + skill -> scored trajectories.
usage: run.py --skill <file|none> --tasks <train|sel|test|id,id,...> --tag <name> [--reps 1] [--par 4]
Serve the local fixtures first:  python3 -m http.server 8791 --bind 127.0.0.1 -d fixtures
Results land in ./runs/<tag>/ (summary.json plus one compact traj.txt per rollout)."""
import argparse, json, os, re, subprocess, sys, time, pathlib, threading, concurrent.futures as cf
LAUNCH = threading.Lock()  # snap Chromium fails on concurrent launches
ROOT = pathlib.Path(__file__).resolve().parent
TASKS = json.load(open(ROOT / "tasks.json"))
MODEL = "claude-opus-5-5"
TOK_CAP = 200_000  # weighted tokens at which efficiency credit reaches 0

def score(correct, wtok):
    # correctness dominates; up to 30% of the credit is for doing it cheaply
    return 0.0 if not correct else 0.7 + 0.3 * max(0.0, 1 - wtok / TOK_CAP)

def rollout(key, skill_text, outdir):
    tid = key.split('_')[0]; t = TASKS[tid]; wd = outdir / key; wd.mkdir(parents=True, exist_ok=True)
    sess = f"so-{outdir.name}-{key}"
    prompt = (t["task"] + "\n\nDo this in a real browser using the `agent-browser` CLI through Bash "
              "(do not use curl/wget or other HTTP clients). When done, end your reply with a final line "
              "`ANSWER: <your answer>`. A private browser session is already running and preselected through "
              "environment variables, so plain `agent-browser <command>` calls use it.")
    cmd = ["claude", "-p", prompt, "--model", MODEL, "--output-format", "stream-json", "--verbose",
           "--tools", "Bash", "--allowedTools", "Bash", "--disallowedTools", "Bash(curl:*)", "Bash(wget:*)",
           "--disable-slash-commands", "--strict-mcp-config", "--setting-sources", "project",
           "--max-turns", "45", "--max-budget-usd", "3"]
    if skill_text: cmd += ["--append-system-prompt", skill_text]
    # every rollout gets its own daemon namespace, session and Chrome profile, so students cannot disturb each other
    snap = pathlib.Path.home() / "snap/chromium/common"  # snap Chromium can only write profiles under this directory
    prof = (snap if snap.is_dir() else pathlib.Path("/tmp")) / "ab-so" / sess
    env = dict(os.environ, AGENT_BROWSER_SESSION=sess, AGENT_BROWSER_NAMESPACE=sess, AGENT_BROWSER_PROFILE=str(prof)); env.pop("CLAUDECODE", None)
    with LAUNCH:  # warm the browser serially so launch flakiness never reaches the student
        for _ in range(4):
            try:
                if subprocess.run(["agent-browser", "open", "about:blank"], env=env, capture_output=True, timeout=90).returncode == 0: break
            except subprocess.TimeoutExpired: pass
            subprocess.run(["agent-browser", "close"], env=env, capture_output=True, timeout=60)
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=wd, env=env, capture_output=True, text=True, timeout=900)
        raw = p.stdout
    except subprocess.TimeoutExpired as e:
        raw = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
    try: subprocess.run(["agent-browser", "close", "--all"], env=env, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired: pass
    subprocess.run(["rm", "-rf", str(prof)])
    (wd / "raw.jsonl").write_text(raw)
    steps, final, usage, turns, cost = [], "", {}, 0, 0
    for line in raw.splitlines():
        try: ev = json.loads(line)
        except Exception: continue
        if ev.get("type") == "assistant":
            for c in ev["message"].get("content", []):
                if c["type"] == "text" and c["text"].strip(): steps.append("SAY: " + c["text"].strip()[:500])
                if c["type"] == "tool_use": steps.append("$ " + str(c["input"].get("command", c["input"]))[:900])
        elif ev.get("type") == "user":
            for c in ev["message"].get("content", []) if isinstance(ev["message"].get("content"), list) else []:
                if c.get("type") == "tool_result":
                    s = c.get("content"); s = s if isinstance(s, str) else "".join(x.get("text", "") for x in s or [])
                    steps.append(f"-> [{len(s)} chars] " + (s[:500] + (" …" + s[-150:] if len(s) > 700 else s[500:700])))
        elif ev.get("type") == "result":
            final = ev.get("result") or ""; usage = ev.get("usage", {}); turns = ev.get("num_turns", 0); cost = ev.get("total_cost_usd", 0)
    ans = final.split("ANSWER:")[-1] if "ANSWER:" in final else final
    correct = bool(final) and all(re.search(e, ans, re.I) for e in t["expect"])
    wtok = usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0) + usage.get("cache_creation_input_tokens", 0) + 5 * usage.get("output_tokens", 0)
    res = dict(id=key, correct=correct, score=round(score(correct, wtok), 3), wtok=wtok, turns=turns, cost=round(cost, 3),
               secs=round(time.time() - t0), infra="exited early" in raw, answer=ans.strip()[:300])
    (wd / "traj.txt").write_text(f"TASK {tid}: {t['task']}\nEXPECT: {t['expect']}\nRESULT: {json.dumps(res)}\n\n" + "\n".join(steps))
    return res

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--skill"); ap.add_argument("--tasks"); ap.add_argument("--tag"); ap.add_argument("--par", type=int, default=4); ap.add_argument("--reps", type=int, default=1)
    a = ap.parse_args()
    ids = [k for k, v in TASKS.items() if v["split"] == a.tasks] or a.tasks.split(",")
    ids = [f"{i}_r{r}" for r in range(1, a.reps + 1) for i in ids]
    skill = "" if a.skill == "none" else open(a.skill).read()
    out = ROOT / "runs" / a.tag; out.mkdir(parents=True, exist_ok=True)
    with cf.ThreadPoolExecutor(a.par) as ex: rs = list(ex.map(lambda i: rollout(i, skill, out), ids))
    n = len(rs); summ = dict(tag=a.tag, skill=a.skill, n=n, acc=round(sum(r["correct"] for r in rs) / n, 3),
        score=round(sum(r["score"] for r in rs) / n, 4), wtok=round(sum(r["wtok"] for r in rs) / n), turns=round(sum(r["turns"] for r in rs) / n, 1),
        cost=round(sum(r["cost"] for r in rs), 2), results=rs)
    (out / "summary.json").write_text(json.dumps(summ, indent=1))
    for r in rs: print(f"{r['id']} {'OK ' if r['correct'] else 'FAIL'} score={r['score']} wtok={r['wtok']} turns={r['turns']} ${r['cost']} {r['secs']}s | {r['answer'][:110]!r}")
    print(f"== {a.tag}: acc={summ['acc']} score={summ['score']} wtok={summ['wtok']} turns={summ['turns']} cost=${summ['cost']}")
