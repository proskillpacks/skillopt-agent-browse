---
name: agent-browse
description: Browse and operate real web pages with the agent-browser CLI in as few tool calls as possible. Use when a task needs a real browser - clicking, filling forms, logging in, hover menus, uploads, drag and drop, JS dialogs, iframes, infinite scroll, or extracting data from rendered or paginated pages.
allowed-tools: Bash(agent-browser:*)
---

# Browsing the web with agent-browser

`agent-browser` drives a real Chrome through short CLI commands. The browser stays open between commands. The commands below are the whole everyday surface; do not spend calls on `--help`.

## Core loop
1. `agent-browser open <url>`
2. `agent-browser snapshot -i` — lists interactive elements with refs like `@e3`
3. Act on refs or CSS selectors: `click`, `fill <sel> "text"`, `select <sel> "Label"`, `check`, `hover`, `press Enter`, `upload <sel> <abs-path>`, `drag <src> <dst>`
4. Re-run `snapshot -i` after anything that changes the page, then continue.

## Work in few calls
- Put several commands in one Bash call. Use `;` between steps that should run regardless and `&&` only where a later step is pointless if the earlier one failed.
- When the task is to read data and the page structure is predictable, skip snapshots: `open` then one `eval` that returns `JSON.stringify(...)` of exactly what you need. For paginated data, loop over the pages in a single shell `for` loop.
- Append `agent-browser close` to your last command chain instead of spending a separate call on it.

## Slow or stalled page loads
`open` can report `Operation timed out` when a page's load event hangs on a slow third-party script. This is usually not fatal and not worth diagnosing.
- Never chain the rest of the work to `open` with `&&`. Write `agent-browser open <url>; agent-browser wait "<css of the element you need>"; ...`
- If elements are missing or clicks have no effect after a timed-out load, the page's own scripts did not attach: run the same `open; wait` once more. Do not inspect network requests, console logs or browser processes.

## Reading
- `agent-browser get text <ref|css>` for one element, `get attr <sel> <name>`, `agent-browser read` for the page text.
- `agent-browser eval "<js>"` to pull structured data out of the DOM.

## Waiting
- Prefer `wait --text "..."`, `wait <css|@ref>` or `wait --fn "<js condition>"` over fixed sleeps.

## Dialogs and right-click
- `confirm()` and `prompt()` block the page until answered. Answer in the same Bash call as the click that triggers them: `agent-browser click <sel>; agent-browser dialog dismiss` or `agent-browser dialog accept "text"`.
- `alert()` is accepted automatically and its text is lost. To read it, hook it first: `eval "window.__a=[];window.alert=m=>window.__a.push(String(m))"`, trigger it, then `eval "JSON.stringify(window.__a)"`.
- There is no right-click flag. Get the centre with `get box <sel>`, then `mouse move <x> <y>; mouse down right; mouse up right`.

## Setup (once per task)
- Use your own browser, never the shared default: `export AGENT_BROWSER_SESSION=<task-name>` at the start of each Bash call, and close only that session. Never run `agent-browser close --all`; it closes other agents' browsers.
- If launch fails with `Chrome exited early ... DevToolsActivePort` (snap Chromium, several browsers at once), also set `AGENT_BROWSER_PROFILE` to a private directory under `~/snap/chromium/common/`.
