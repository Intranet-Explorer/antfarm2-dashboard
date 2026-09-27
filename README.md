# antfarm2-dashboard

Live viewer for [antfarm2](https://github.com/Intranet-Explorer/antfarm2-standalone):
watch two LLM agents think, act and talk to each other in real time.

![dashboard screenshot](screenshot.png)

## What it shows

- **Per-agent live columns** — thinking (💭), tool calls (⚙️), tool results
  (👁️), and what the agent says (💬), each visually distinct, oldest→newest,
  auto-scrolling to the latest activity unless you've scrolled up to read
  history.
- **Status cards** — which agent is active right now, which model it's
  running, how long its current shift has been going, a live pulse/glow
  while a shift is in progress.
- **Inter-agent comms** — every direct message between the two agents,
  newest first, with a pulse animation when a new one lands.
- **Tool-usage stats** — per-agent bar chart of real tool calls made (not
  self-reported — pulled straight from logged tool-call events).
- **Shared workspace + observer ticks** — what files exist right now and a
  timeline of passive filesystem snapshots, so claimed actions can be
  checked against what actually happened on disk.

## Running it

```bash
python3 server.py
# opens an HTTP API + static viewer on :8765
```

It reads live from the harness's SQLite database
(`../antfarm2-standalone/state.db` by default) — no separate setup, just
point it at a running (or paused) harness instance.

## Security

Accepts requests only from its own page: no CORS, and POSTs need the
`X-Antfarm` header.
