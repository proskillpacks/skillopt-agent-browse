# Browsing the web with agent-browser

`agent-browser` drives a real Chrome through short CLI commands. The browser stays open between commands. The commands below are the whole everyday surface; do not spend calls on `--help`.

## Core loop
1. `agent-browser open <url>`
2. `agent-browser snapshot -i` — lists interactive elements with refs like `@e3`
3. Act on refs or CSS selectors: `click`, `fill <sel> "text"`, `select <sel> "Label"`, `check`, `hover`, `press Enter`, `upload <sel> <abs-path>`, `drag <src> <dst>`
4. Re-run `snapshot -i` after anything that changes the page, then continue.

`select` only works on a real `<select>` (shown as `combobox` in the snapshot). A dropdown shown as `generic ... clickable` is custom: `click` it, `snapshot -i`, then `click` the option. After filling a form, check the snapshot shows your values before submitting.

Selectors are plain CSS or `@eN` refs, always in double quotes: an unquoted `#go` is a shell comment and the command loses its argument. `text=...` and `:has-text(...)` do not work; to act on visible text use `agent-browser find text "Sign in" click`.

## Work in few calls
- Put several commands in one Bash call. Use `;` between steps that should run regardless and `&&` only where a later step is pointless if the earlier one failed.
- Never invent what you have not seen. Open the URL the task gives and reach other pages through the site's own links; do not guess deep URLs. Do not guess ids or class names either: the first call on a new page ends with a look at it (`snapshot -i`, or `eval "document.querySelector('main,body').innerHTML.slice(0,1500)"` when you need the markup), and selectors come from that output.
- Once you have seen the markup, read data with one `eval` that returns `JSON.stringify(...)` of exactly what you need. 
- Lists are often paginated. An empty result from a selector you guessed proves nothing, so before treating a list as complete, check the page's own total (text such as `26 results` or `Page 1 of 50`) against what you collected, and find the next-page link by its text (`[...document.querySelectorAll('a')].filter(a => /next/i.test(a.textContent)).map(a => a.href)`). Walk the pages in one shell loop that `open`s each next href and stops when there is none; clicking `next` races with the page load.
- `agent-browser close` throws the page state away. Never put it in a chain whose output you still have to check; skip it unless you already hold the answer.

## Slow or stalled page loads
`open` can fail with `Operation timed out` or `CDP command timed out` when the site is slow. The page may look loaded, but its scripts are often missing, so clicks do nothing and content never appears.
- Open with a retry and carry on only after a `✓`: `for i in 1 2 3; do agent-browser open "<url>" && break; sleep 5; done; agent-browser wait "<css you have seen>"; ...`
- If a click reports `✓ Done` but the page does not change, the scripts did not attach: run that same retry loop again and redo the steps. Do not inspect scripts, network requests, console logs or browser processes, and do not replace a real `click` with `eval "el.click()"` or dispatched events.

## Reading
- `agent-browser get text <ref|css>` for one element, `get attr <sel> <name>`, `agent-browser read` for the page text.
- `agent-browser eval "<js>"` to pull structured data out of the DOM. For anything longer than a short expression, pass the script on stdin so the shell cannot break its quotes; the value of the last expression is printed:
```
agent-browser eval --stdin <<'JS'
(() => {
  const rows = [...document.querySelectorAll('h3 a')];
  return JSON.stringify(rows.map(a => a.textContent.trim()));
})()
JS
```
  Keep the `(() => { ... })()` wrapper: top-level `const` and `let` persist between evals and a second declaration fails. The result prints as a quoted JSON string; pipe it through `jq -r .` before parsing it in the shell.

## Waiting
- Prefer `wait --text "..."`, `wait <css|@ref>` or `wait --fn "<js condition>"` over fixed sleeps.

## Dialogs and right-click
- `confirm()` and `prompt()` block the page until answered. Answer in the same Bash call as the click that triggers them: `agent-browser click <sel>; agent-browser dialog dismiss` or `agent-browser dialog accept "text"`.
- `alert()` is accepted automatically and its text is lost. To read it, hook it first: `eval "window.__a=[];window.alert=m=>window.__a.push(String(m))"`, trigger it, then `eval "JSON.stringify(window.__a)"`.
- There is no right-click flag. Get the centre with `get box <sel>`, then `mouse move <x> <y>; mouse down right; mouse up right`.
