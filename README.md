# antfarm2-dashboard

**Live viewer for [antfarm2](https://github.com/Intranet-Explorer/antfarm2-standalone)** —
watch two LLM agents think, act, and talk to each other in real time, no
polling logs by hand.

> Screenshot coming soon — will be added once a capture is available.
> <!-- ![dashboard screenshot](screenshot.png) -->

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

## Design notes

Dark, chat-bubble layout, styled to visually match the Hermes desktop app
it was built alongside (same UI font stack, and headers use the app's
"Collapse" display typeface — bundled here as a local asset, which is the
reason this repo is private rather than public: that font's redistribution
terms aren't something we control).

## Status

Actively developed alongside the harness — this is the observation half of
the same experiment; changes here mostly follow requests surfaced by
actually watching agents run (e.g. "I can't tell whose column this is,"
"I keep having to scroll to see new output," "that panel doesn't line up").
