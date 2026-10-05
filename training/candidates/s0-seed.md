# Browsing the web with agent-browser

`agent-browser` drives a real Chrome through short CLI commands. The browser stays open between commands.

## Core loop
1. `agent-browser open <url>`
2. `agent-browser snapshot -i` — lists interactive elements with refs like `@e3`
3. Act on refs: `click @e3`, `fill @e4 "text"`, `select @e5 "Label"`, `press Enter`, `hover @e6`
4. Re-run `snapshot -i` after anything that changes the page, then continue.

## Reading
- `agent-browser get text <ref|css>` for one element, `agent-browser read` for the page text.
- `agent-browser eval "<js>"` to pull structured data out of the DOM.

## Waiting
- Prefer `wait --text "..."` or `wait <css|@ref>` over fixed sleeps.

## Finish
- Run `agent-browser close` when the task is done.
