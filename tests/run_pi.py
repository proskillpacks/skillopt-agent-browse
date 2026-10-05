#!/usr/bin/env python3
"""Same rollout harness as run.py, but the frozen student is a local model driven by pi (pi -p) instead of claude -p.
usage: run_pi.py --skill <file|none> --tasks <train|sel|test|id,id,...> --tag <name> [--reps 1] [--par 4] [--model <provider>/qwen3.8-27b]
Serve the local fixtures first:  python3 -m http.server 8791 --bind 127.0.0.1 -d fixtures
Results land in ./runs/<tag>/ (summary.json plus one compact traj.txt per rollout)."""
import argparse, json, os, re, signal, subprocess, time, pathlib, threading, concurrent.futures as cf
LAUNCH = threading.Lock()  # snap Chromium fails on concurrent launches
ROOT = pathlib.Path(__file__).resolve().parent
TASKS = json.load(open(ROOT / "tasks.json"))
TOK_CAP = 200_000  # weighted tokens at which efficiency credit reaches 0
TIMEOUT = 900      # pi has no --max-turns, so wall clock is the only stop

def score(correct, wtok):
    # correctness dominates; up to 30% of the credit is for doing it cheaply
    return 0.0 if not correct else 0.7 + 0.3 * max(0.0, 1 - wtok / TOK_CAP)

def text_of(content):
    return content if isinstance(content, str) else "".join(c.get("text", "") for c in content or [] if c.get("type") == "text")

def rollout(key, skill_text, outdir, model):
    tid = key.split('_')[0]; t = TASKS[tid]; wd = outdir / key; wd.mkdir(parents=True, exist_ok=True)
    sess = f"so-{outdir.name}-{key}"
    prompt = (t["task"] + "\n\nDo this in a real browser using the `agent-browser` CLI through Bash "
              "(do not use curl/wget or other HTTP clients). When done, end your reply with a final line "
              "`ANSWER: <your answer>`. A private browser session is already running and preselected through "
              "environment variables, so plain `agent-browser <command>` calls use it.")
    cmd = ["pi", "-p", "--mode", "json", "--model", model, "--tools", "bash", "--no-session", "--no-extensions",
           "--no-skills", "--no-context-files", "--no-prompt-templates", "--offline"]
    if skill_text: cmd += ["--append-system-prompt", skill_text]
    cmd += ["--", prompt]
    # every rollout gets its own daemon namespace, session and Chrome profile, so students cannot disturb each other
    snap = pathlib.Path.home() / "snap/chromium/common"  # snap Chromium can only write profiles under this directory
    prof = (snap if snap.is_dir() else pathlib.Path("/tmp")) / "ab-so" / sess
    env = dict(os.environ, AGENT_BROWSER_SESSION=sess, AGENT_BROWSER_NAMESPACE=sess, AGENT_BROWSER_PROFILE=str(prof))
    with LAUNCH:  # warm the browser serially so launch flakiness never reaches the student
        for _ in range(4):
            try:
                if subprocess.run(["agent-browser", "open", "about:blank"], env=env, capture_output=True, timeout=90).returncode == 0: break
            except subprocess.TimeoutExpired: pass
            subprocess.run(["agent-browser", "close"], env=env, capture_output=True, timeout=60)
    t0 = time.time(); timed_out = False
    with open(wd / "raw.jsonl", "w") as fo, open(wd / "stderr.txt", "w") as fe:
        # stdin must be closed or pi -p waits on it; own process group so a timeout also kills the student's children
        p = subprocess.Popen(cmd, cwd=wd, env=env, stdin=subprocess.DEVNULL, stdout=fo, stderr=fe, start_new_session=True)
        try: p.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            timed_out = True; os.killpg(p.pid, signal.SIGKILL); p.wait()
    try: subprocess.run(["agent-browser", "close", "--all"], env=env, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired: pass
    subprocess.run(["rm", "-rf", str(prof)])
    steps, final, turns, wtok, out_tok, curl = [], "", 0, 0, 0, False
    for line in open(wd / "raw.jsonl", errors="replace"):
        try: ev = json.loads(line)
        except Exception: continue
        if ev.get("type") != "message_end": continue
        m = ev["message"]
        if m.get("role") == "assistant":
            turns += 1; u = m.get("usage", {}); out_tok += u.get("output", 0)
            wtok += u.get("input", 0) + u.get("cacheRead", 0) + u.get("cacheWrite", 0) + 5 * u.get("output", 0)
            txt = text_of(m.get("content")).strip()
            if txt: steps.append("SAY: " + txt[:500]); final = txt
            for c in m.get("content", []):
                if c.get("type") == "toolCall":
                    command = str(c["arguments"].get("command", c["arguments"]))
                    curl = curl or bool(re.search(r"(^|[\s;&|(])(curl|wget)\s", command))
                    steps.append("$ " + command[:900])
            if m.get("stopReason") not in ("stop", "toolUse"): steps.append(f"!! stopReason={m.get('stopReason')} {str(m.get('errorMessage', ''))[:300]}")
        elif m.get("role") == "toolResult":
            s = text_of(m.get("content"))
            steps.append(f"-> [{len(s)} chars] " + (s[:500] + (" …" + s[-150:] if len(s) > 700 else s[500:700])))
    ans = final.split("ANSWER:")[-1] if "ANSWER:" in final else final
    # run.py blocks curl/wget at the tool layer; pi cannot, so a rollout that used them is scored wrong
    correct = bool(final) and not curl and not timed_out and all(re.search(e, ans, re.I) for e in t["expect"])
    res = dict(id=key, correct=correct, score=round(score(correct, wtok), 3), wtok=wtok, out_tok=out_tok, turns=turns,
               secs=round(time.time() - t0), timed_out=timed_out, curl=curl, answer=ans.strip()[:300])
    (wd / "traj.txt").write_text(f"TASK {tid}: {t['task']}\nEXPECT: {t['expect']}\nRESULT: {json.dumps(res)}\n\n" + "\n".join(steps))
    return res

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--skill"); ap.add_argument("--tasks"); ap.add_argument("--tag"); ap.add_argument("--par", type=int, default=4); ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--model", default="ignis/qwen3.8-27b")
    a = ap.parse_args()
    ids = [k for k, v in TASKS.items() if v["split"] == a.tasks] or a.tasks.split(",")
    ids = [f"{i}_r{r}" for r in range(1, a.reps + 1) for i in ids]
    skill = "" if a.skill == "none" else open(a.skill).read()
    out = ROOT / "runs" / a.tag; out.mkdir(parents=True, exist_ok=True)
    with cf.ThreadPoolExecutor(a.par) as ex: rs = list(ex.map(lambda i: rollout(i, skill, out, a.model), ids))
    n = len(rs); summ = dict(tag=a.tag, skill=a.skill, model=a.model, n=n, acc=round(sum(r["correct"] for r in rs) / n, 3),
        score=round(sum(r["score"] for r in rs) / n, 4), wtok=round(sum(r["wtok"] for r in rs) / n), turns=round(sum(r["turns"] for r in rs) / n, 1),
        results=rs)
    (out / "summary.json").write_text(json.dumps(summ, indent=1))
    for r in rs: print(f"{r['id']} {'OK ' if r['correct'] else 'FAIL'} score={r['score']} wtok={r['wtok']} turns={r['turns']} {r['secs']}s{' TIMEOUT' if r['timed_out'] else ''}{' CURL' if r['curl'] else ''} | {r['answer'][:110]!r}")
    print(f"== {a.tag}: acc={summ['acc']} score={summ['score']} wtok={summ['wtok']} turns={summ['turns']}")
