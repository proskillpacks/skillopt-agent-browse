"""Student/optimizer adapters. One interface: Adapter.complete(system, user) -> dict(text, in_tok, out_tok, cost).
Standard library only. Add your own by writing a class with a complete() method and registering it in ADAPTERS."""
import json, os, subprocess, tempfile, urllib.request, urllib.error


class ClaudeCLI:
    """`claude -p` headless, no tools, no user settings. The skill text is appended to the system prompt."""
    def __init__(self, model=None):
        self.model = model or os.environ.get("STUDENT_MODEL", "haiku")

    def complete(self, system, user):
        cmd = ["claude", "-p", user, "--model", self.model, "--output-format", "json", "--tools", "",
               "--disable-slash-commands", "--strict-mcp-config", "--setting-sources", "project",
               "--no-session-persistence", "--max-turns", "3"]
        if system:
            cmd += ["--append-system-prompt", system]
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        with tempfile.TemporaryDirectory(prefix="rollout-") as wd:  # fresh empty working directory per call
            p = subprocess.run(cmd, cwd=wd, env=env, capture_output=True, text=True, timeout=600)
        try:
            d = json.loads(p.stdout)
        except Exception:
            return dict(text="", in_tok=0, out_tok=0, cost=0, error=(p.stderr or p.stdout)[:300])
        u = d.get("usage", {})
        in_tok = u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
        return dict(text=d.get("result") or "", in_tok=in_tok, out_tok=u.get("output_tokens", 0), cost=d.get("total_cost_usd", 0))


class OpenAICompatible:
    """Any OpenAI-compatible /chat/completions endpoint (Ollama, llama.cpp server, LM Studio, vLLM, hosted APIs).
    Environment: OPENAI_BASE_URL (default http://localhost:11434/v1), STUDENT_MODEL (required),
    OPENAI_API_KEY (optional), STUDENT_TEMPERATURE (default 0.2), STUDENT_EXTRA (optional JSON merged into the request body)."""
    def __init__(self, model=None):
        self.base = os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1").rstrip("/")
        self.model = model or os.environ.get("STUDENT_MODEL")
        if not self.model:
            raise SystemExit("set STUDENT_MODEL (or pass --model) for the openai adapter")
        self.key = os.environ.get("OPENAI_API_KEY", "")
        self.temp = float(os.environ.get("STUDENT_TEMPERATURE", "0.2"))
        self.extra = json.loads(os.environ.get("STUDENT_EXTRA", "{}"))

    def complete(self, system, user):
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
        body = dict(model=self.model, messages=msgs, temperature=self.temp, **self.extra)
        h = {"Content-Type": "application/json"}
        if self.key:
            h["Authorization"] = "Bearer " + self.key
        req = urllib.request.Request(self.base + "/chat/completions", json.dumps(body).encode(), h)
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                d = json.load(r)
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            return dict(text="", in_tok=0, out_tok=0, cost=0, error=str(e)[:300])
        u = d.get("usage", {})
        return dict(text=d["choices"][0]["message"].get("content") or "", in_tok=u.get("prompt_tokens", 0),
                    out_tok=u.get("completion_tokens", 0), cost=0)


ADAPTERS = {"claude": ClaudeCLI, "openai": OpenAICompatible}


def get_adapter(name, model=None):
    return ADAPTERS[name](model)
