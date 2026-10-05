"""Deterministic checkers. A task has kind "exact" (reply must equal the expected text after trimming
whitespace) or "json" (reply must parse as JSON and equal the expected object; key order does not matter).
No code fences, no extra words: strict output is part of the job."""
import json


def check(task, reply):
    got = (reply or "").strip()
    if task["kind"] == "exact":
        return got == task["expected"]
    if task["kind"] == "json":
        try:
            return json.loads(got) == task["expected"]
        except ValueError:
            return False
    raise ValueError("unknown kind " + task["kind"])
