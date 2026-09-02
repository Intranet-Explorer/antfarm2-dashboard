#!/usr/bin/env python3
"""
antfarm2 live dashboard server.
Serves a JSON API over both agent profiles' SQLite session stores plus
the passive observer snapshots, and a static HTML/JS viewer.
Stdlib only — no dependencies.
"""
import sqlite3
import json
import os
import http.server
import socketserver
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HOME = Path.home()
PROFILES = {
    "alpha": HOME / ".hermes/profiles/agent-alpha/state.db",
    "beta": HOME / ".hermes/profiles/agent-beta/state.db",
}
STANDALONE_DB = HOME / "antfarm2-standalone" / "state.db"
OBSERVER_DIR = HOME / "antfarm2-observer"
WORKSPACE_DIR = HOME / "antfarm2"
STATIC_DIR = Path(__file__).parent / "static"

AGENTS_MODEL = {
    "alpha": "qwen3.8-27b-obliterated",
    "beta": "qwen3-14b-64k",
}

PORT = 8765


def get_standalone_db():
    if not STANDALONE_DB.exists():
        return None
    conn = sqlite3.connect(f"file:{STANDALONE_DB}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_standalone_shifts(agent, limit=20):
    conn = get_standalone_db()
    if not conn:
        return []
    try:
        rows = conn.execute(
            "SELECT id, agent, started_at, ended_at, note FROM shifts WHERE agent=? ORDER BY started_at DESC LIMIT ?",
            (agent, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def fetch_standalone_events(shift_id, limit=200):
    conn = get_standalone_db()
    if not conn:
        return []
    try:
        rows = conn.execute(
            "SELECT id, agent, shift_id, role, content, reasoning, tool_name, tool_args, tool_call_id, timestamp "
            "FROM events WHERE shift_id=? ORDER BY id ASC LIMIT ?",
            (shift_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def fetch_standalone_status():
    conn = get_standalone_db()
    if not conn:
        return {"alpha": {"active": False}, "beta": {"active": False}, "current_shift": None}
    try:
        out = {}
        for agent in ("alpha", "beta"):
            row = conn.execute(
                "SELECT id, started_at, ended_at FROM shifts WHERE agent=? ORDER BY started_at DESC LIMIT 1",
                (agent,),
            ).fetchone()
            if row:
                out[agent] = {
                    "active": row["ended_at"] is None,
                    "shift_id": row["id"],
                    "started_at": row["started_at"],
                }
            else:
                out[agent] = {"active": False, "shift_id": None, "started_at": None}
        return out
    finally:
        conn.close()


def fetch_standalone_stats(agent):
    conn = get_standalone_db()
    if not conn:
        return {}
    try:
        total_shifts = conn.execute("SELECT COUNT(*) c FROM shifts WHERE agent=?", (agent,)).fetchone()["c"]
        tool_rows = conn.execute(
            "SELECT tool_name FROM events WHERE agent=? AND role='assistant' AND tool_name IS NOT NULL",
            (agent,),
        ).fetchall()
        tool_counts = {}
        for r in tool_rows:
            n = r["tool_name"]
            tool_counts[n] = tool_counts.get(n, 0) + 1
        last = conn.execute(
            "SELECT MAX(started_at) m FROM shifts WHERE agent=?", (agent,)
        ).fetchone()["m"]
        return {
            "total_shifts": total_shifts,
            "tool_usage": tool_counts,
            "last_active": last,
        }
    finally:
        conn.close()


def fetch_standalone_comms(limit=20):
    conn = get_standalone_db()
    if not conn:
        return []
    try:
        rows = conn.execute(
            "SELECT id, from_agent, to_agent, text, timestamp FROM agent_messages ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]
    finally:
        conn.close()


def get_db(agent):
    path = PROFILES.get(agent)
    if not path or not path.exists():
        return None
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_sessions(agent, limit=50):
    conn = get_db(agent)
    if not conn:
        return []
    try:
        rows = conn.execute(
            """SELECT id, source, model, started_at, ended_at, end_reason,
                      message_count, chat_id
               FROM sessions
               ORDER BY started_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def fetch_status(agent):
    """Is this agent's most recent session still running (no ended_at)?"""
    conn = get_db(agent)
    if not conn:
        return {"active": False, "session_id": None, "started_at": None}
    try:
        row = conn.execute(
            "SELECT id, started_at, ended_at FROM sessions ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return {"active": False, "session_id": None, "started_at": None}
        return {
            "active": row["ended_at"] is None,
            "session_id": row["id"],
            "started_at": row["started_at"],
        }
    finally:
        conn.close()


def fetch_agent_messages(limit=50):
    """Cross-agent messages: any tool_calls referencing message_agent, across both DBs."""
    out = []
    for agent in PROFILES:
        conn = get_db(agent)
        if not conn:
            continue
        try:
            rows = conn.execute(
                """SELECT id, session_id, content, tool_calls, tool_name, timestamp, role
                   FROM messages
                   WHERE (tool_calls LIKE '%message_agent%')
                      OR (role='tool' AND tool_name='message_agent')
                   ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            for r in rows:
                d = dict(r)
                d["from_agent"] = agent
                out.append(d)
        finally:
            conn.close()
    out.sort(key=lambda r: r["timestamp"])
    return out


def fetch_messages(agent, session_id=None, limit=200):
    conn = get_db(agent)
    if not conn:
        return []
    try:
        if session_id:
            rows = conn.execute(
                """SELECT id, session_id, role, content, tool_call_id,
                          tool_calls, tool_name, timestamp, reasoning
                   FROM messages WHERE session_id = ?
                   ORDER BY id ASC""",
                (session_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, session_id, role, content, tool_call_id,
                          tool_calls, tool_name, timestamp, reasoning
                   FROM messages
                   ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            rows = list(reversed(rows))
        return [dict(r) for r in rows]
    finally:
        conn.close()


def fetch_stats(agent):
    conn = get_db(agent)
    if not conn:
        return {}
    try:
        total_sessions = conn.execute("SELECT COUNT(*) c FROM sessions").fetchone()["c"]
        total_messages = conn.execute("SELECT COUNT(*) c FROM messages").fetchone()["c"]
        tool_calls = conn.execute(
            "SELECT COUNT(*) c FROM messages WHERE role='assistant' AND tool_calls IS NOT NULL AND tool_calls != ''"
        ).fetchone()["c"]
        # tool usage breakdown: parse tool_calls JSON per assistant message
        tool_rows = conn.execute(
            "SELECT tool_calls FROM messages WHERE role='assistant' AND tool_calls IS NOT NULL AND tool_calls != ''"
        ).fetchall()
        tool_counts = {}
        for r in tool_rows:
            try:
                calls = json.loads(r["tool_calls"])
                for c in calls:
                    name = c.get("function", {}).get("name", "unknown")
                    tool_counts[name] = tool_counts.get(name, 0) + 1
            except Exception:
                pass
        last_active = conn.execute("SELECT MAX(started_at) m FROM sessions").fetchone()["m"]
        return {
            "total_sessions": total_sessions,
            "total_messages": total_messages,
            "assistant_turns_with_tools": tool_calls,
            "tool_usage": tool_counts,
            "last_active": last_active,
        }
    finally:
        conn.close()


def fetch_observer_timeline(limit=100):
    jsonl = OBSERVER_DIR / "timeline.jsonl"
    if not jsonl.exists():
        return []
    lines = jsonl.read_text().strip().split("\n")
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def fetch_latest_observer_snapshot():
    if not OBSERVER_DIR.exists():
        return None
    snaps = sorted(OBSERVER_DIR.glob("*.json"))
    if not snaps:
        return None
    try:
        return json.loads(snaps[-1].read_text())
    except Exception:
        return None


def fetch_workspace_files():
    if not WORKSPACE_DIR.exists():
        return []
    out = []
    for f in sorted(WORKSPACE_DIR.rglob("*")):
        if f.is_file():
            try:
                out.append({
                    "path": str(f.relative_to(WORKSPACE_DIR)),
                    "size": f.stat().st_size,
                    "mtime": f.stat().st_mtime,
                    "content": f.read_text(errors="replace")[:5000] if f.stat().st_size < 50000 else None,
                })
            except Exception:
                pass
    return out


def fetch_shift():
    shift_file = WORKSPACE_DIR / "shift.json"
    if not shift_file.exists():
        return None
    try:
        return json.loads(shift_file.read_text())
    except Exception:
        return None


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, fmt, *args):
        pass  # quiet

    def _send_json(self, data):
        body = json.dumps(data, default=str).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/api/sessions":
            agent = qs.get("agent", ["alpha"])[0]
            shifts = fetch_standalone_shifts(agent)
            # normalize field names to what the frontend expects
            sessions = [{
                "id": s["id"], "source": "shift", "model": AGENTS_MODEL.get(agent, ""),
                "started_at": s["started_at"], "ended_at": s["ended_at"],
                "message_count": None, "note": s["note"],
            } for s in shifts]
            self._send_json({"sessions": sessions})
            return

        if parsed.path == "/api/messages":
            agent = qs.get("agent", ["alpha"])[0]
            shift_id = qs.get("session_id", [None])[0]
            events = fetch_standalone_events(shift_id) if shift_id else []
            # normalize to what the frontend expects
            messages = []
            for e in events:
                if e["role"] == "system":
                    continue
                m = {
                    "id": e["id"], "session_id": e["shift_id"], "role": e["role"],
                    "content": e["content"], "tool_calls": None, "tool_name": e["tool_name"],
                    "timestamp": e["timestamp"], "reasoning": e.get("reasoning"),
                }
                if e["role"] == "assistant" and e["tool_name"]:
                    m["tool_calls"] = json.dumps([{
                        "function": {"name": e["tool_name"], "arguments": e["tool_args"]}
                    }])
                messages.append(m)
            self._send_json({"messages": messages})
            return

        if parsed.path == "/api/stats":
            self._send_json({
                "alpha": fetch_standalone_stats("alpha"),
                "beta": fetch_standalone_stats("beta"),
            })
            return

        if parsed.path == "/api/status":
            st = fetch_standalone_status()
            self._send_json({
                "alpha": st.get("alpha", {}),
                "beta": st.get("beta", {}),
                "shift": None,
            })
            return

        if parsed.path == "/api/agent-messages":
            comms = fetch_standalone_comms()
            messages = [{
                "from_agent": c["from_agent"], "content": c["text"],
                "tool_calls": None, "timestamp": c["timestamp"],
            } for c in comms]
            self._send_json({"messages": messages})
            return

        if parsed.path == "/api/observer":
            self._send_json({
                "timeline": fetch_observer_timeline(),
                "latest": fetch_latest_observer_snapshot(),
            })
            return

        if parsed.path == "/api/workspace":
            self._send_json({"files": fetch_workspace_files()})
            return

        # fall through to static file serving
        super().do_GET()


def main():
    STATIC_DIR.mkdir(exist_ok=True)
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), Handler) as httpd:
        print(f"antfarm2 dashboard running at http://127.0.0.1:{PORT}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
