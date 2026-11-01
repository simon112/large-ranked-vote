#!/usr/bin/env python3
"""Tiny ranked-choice poll server (Borda count). Stdlib only, SQLite storage.

Routes:
  GET  /                 create-poll page
  POST /api/polls        {title, options[]} -> {id}
  GET  /p/<id>           voting + results page
  GET  /api/polls/<id>   poll, ballots, Borda tallies
  POST /api/polls/<id>/vote  {name, ranking[option indices], tiers?, replaces?}
  POST /api/polls/<id>/rename  {name, new_name}  move a ballot to a new name
  POST /api/polls/<id>/delete  {name}            remove a ballot
"""
import html
import json
import os
import secrets
import socket
import socketserver
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = os.environ.get("POLL_DB", str(ROOT / "polls.db"))
PORT = int(os.environ.get("POLL_PORT", "8787"))
HOST = os.environ.get("POLL_HOST", "127.0.0.1")
MAX_BODY = 1024 * 1024
NUM_TIERS = 5  # must match TIERS in static/poll.html
NUM_SUB = 3    # High/Mid/Low: must match SUB in static/poll.html
MAX_DEPTH = 3  # tier + two levels of split: must match MAX_DEPTH in static/poll.html


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS polls (
              id TEXT PRIMARY KEY, title TEXT NOT NULL, options TEXT NOT NULL,
              created TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS ballots (
              poll_id TEXT NOT NULL, name TEXT NOT NULL, ranking TEXT NOT NULL,
              updated TEXT DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (poll_id, name COLLATE NOCASE));
            """
        )
        cols = [r[1] for r in c.execute("PRAGMA table_info(ballots)")]
        if "tiers" not in cols:
            c.execute("ALTER TABLE ballots ADD COLUMN tiers TEXT")


def valid_paths(tiers, n):
    """Normalise group paths (a bare int means a top-level tier) and check they describe
    contiguous, properly nested groups. Returns the normalised list, or None if invalid."""
    if not isinstance(tiers, list) or len(tiers) != n:
        return None
    paths = [[t] if type(t) is int else t for t in tiers]
    for p in paths:
        if not (isinstance(p, list) and 1 <= len(p) <= MAX_DEPTH and all(type(k) is int for k in p)):
            return None
        if not (0 <= p[0] < NUM_TIERS and all(0 <= k < NUM_SUB for k in p[1:])):
            return None
    if any(a > b for a, b in zip(paths, paths[1:])):  # lexicographic: groups are contiguous blocks
        return None
    seen = {tuple(p) for p in paths}
    if any(tuple(p[:d]) in seen for p in paths for d in range(1, len(p))):  # an option can't sit beside its own sub-groups
        return None
    return paths


def borda(options, ballots):
    """Rank k (0-based) of n options earns n-1-k points."""
    n = len(options)
    scores = [0] * n
    for b in ballots:
        for k, idx in enumerate(b["ranking"]):
            scores[idx] += n - 1 - k
    order = sorted(range(n), key=lambda i: (-scores[i], i))
    return [{"index": i, "option": options[i], "score": scores[i]} for i in order]


def load_poll(pid):
    with db() as c:
        row = c.execute("SELECT * FROM polls WHERE id=?", (pid,)).fetchone()
        if not row:
            return None
        ballots = [
            {
                "name": r["name"],
                "ranking": json.loads(r["ranking"]),
                "tiers": json.loads(r["tiers"]) if r["tiers"] else None,
                "updated": r["updated"],
            }
            for r in c.execute(
                "SELECT * FROM ballots WHERE poll_id=? ORDER BY updated", (pid,)
            )
        ]
    options = json.loads(row["options"])
    return {
        "id": pid,
        "title": row["title"],
        "options": options,
        "ballots": ballots,
        "results": borda(options, ballots),
        "max_score": (len(options) - 1) * len(ballots),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "poll/1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body)
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n < 0 or n > MAX_BODY:
            raise ValueError("body too large")
        return json.loads(self.rfile.read(n) or b"{}")

    def page(self, name, title="Ranked poll", description="Drag to rank, Borda count"):
        tpl = (ROOT / "static" / name).read_text()
        tpl = tpl.replace("{{TITLE}}", html.escape(title)).replace(
            "{{DESCRIPTION}}", html.escape(description)
        )
        self.send(200, tpl, "text/html")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            return self.page("create.html")
        if path.startswith("/p/"):
            poll = load_poll(path[3:])
            if not poll:
                return self.send(404, "Poll not found", "text/plain")
            # No option names: listing them in entry order would hand the first few a head start
            # that the page's per-voter shuffle is there to prevent.
            desc = f"Ranked poll: put {len(poll['options'])} options in order. Tap to vote."
            return self.page("poll.html", poll["title"], desc)
        if path.startswith("/api/polls/"):
            poll = load_poll(path[len("/api/polls/"):])
            return self.send(200, poll) if poll else self.send(404, {"error": "not found"})
        self.send(404, "Not found", "text/plain")

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            body = self.read_json()
        except Exception:
            return self.send(400, {"error": "bad JSON"})

        if path == "/api/polls":
            title = str(body.get("title", "")).strip()[:200]
            options = [str(o).strip()[:200] for o in body.get("options", []) if str(o).strip()]
            if not title or len(options) < 2 or len(options) > 200:
                return self.send(400, {"error": "need a title and 2-200 options"})
            if len(set(o.lower() for o in options)) != len(options):
                return self.send(400, {"error": "options must be distinct"})
            pid = secrets.token_urlsafe(6)
            with db() as c:
                c.execute(
                    "INSERT INTO polls (id, title, options) VALUES (?,?,?)",
                    (pid, title, json.dumps(options)),
                )
            return self.send(201, {"id": pid})

        if path.startswith("/api/polls/") and path.endswith("/vote"):
            pid = path[len("/api/polls/"):-len("/vote")]
            poll = load_poll(pid)
            if not poll:
                return self.send(404, {"error": "not found"})
            name = str(body.get("name", "")).strip()[:60]
            ranking = body.get("ranking")
            n = len(poll["options"])
            if not name:
                return self.send(400, {"error": "name required"})
            if (
                not isinstance(ranking, list)
                or not all(type(i) is int for i in ranking)
                or sorted(ranking) != list(range(n))
            ):
                return self.send(400, {"error": "ranking must order every option once"})
            # Optional group path per ranked position, e.g. [0] = "Love it", [0, 2] = its "Low"
            # sub-group. Display/editing aid only: scoring uses the flat ranking.
            tiers = body.get("tiers")
            if tiers is not None:
                tiers = valid_paths(tiers, n)
                if tiers is None:
                    return self.send(400, {"error": "bad tiers"})
            # replaces: a name this browser saved under before; that ballot moves to the new name
            # in the same transaction, so a rejected save never leaves a half-done rename.
            replaces = str(body.get("replaces") or "").strip()[:60]
            with db() as c:
                if replaces and replaces.lower() != name.lower():
                    c.execute("DELETE FROM ballots WHERE poll_id=? AND name=? COLLATE NOCASE", (pid, replaces))
                c.execute(
                    """INSERT INTO ballots (poll_id, name, ranking, tiers) VALUES (?,?,?,?)
                       ON CONFLICT(poll_id, name) DO UPDATE
                       SET ranking=excluded.ranking, tiers=excluded.tiers,
                           updated=CURRENT_TIMESTAMP""",
                    (pid, name, json.dumps(ranking), json.dumps(tiers) if tiers else None),
                )
            return self.send(200, load_poll(pid))

        # Names are the only identity (no accounts), so anyone who can overwrite a ballot by
        # saving under its name can also rename or delete it: these add no new power.
        for action in ("rename", "delete"):
            if path.startswith("/api/polls/") and path.endswith("/" + action):
                pid = path[len("/api/polls/"):-len("/" + action)]
                if not load_poll(pid):
                    return self.send(404, {"error": "not found"})
                name = str(body.get("name", "")).strip()[:60]
                with db() as c:
                    if action == "delete":
                        n = c.execute("DELETE FROM ballots WHERE poll_id=? AND name=? COLLATE NOCASE",
                                      (pid, name)).rowcount
                    else:
                        new = str(body.get("new_name", "")).strip()[:60]
                        if not new:
                            return self.send(400, {"error": "new name required"})
                        clash = c.execute("SELECT 1 FROM ballots WHERE poll_id=? AND name=? COLLATE NOCASE",
                                          (pid, new)).fetchone()
                        if clash and new.lower() != name.lower():
                            return self.send(409, {"error": f"{new} has already voted"})
                        try:
                            n = c.execute("UPDATE ballots SET name=? WHERE poll_id=? AND name=? COLLATE NOCASE",
                                          (new, pid, name)).rowcount
                        except sqlite3.IntegrityError:  # lost a race with another save under `new`
                            return self.send(409, {"error": f"{new} has already voted"})
                if not n:
                    return self.send(404, {"error": f"no vote saved as {name}"})
                return self.send(200, load_poll(pid))

        self.send(404, {"error": "not found"})


class InheritedSocketServer(ThreadingHTTPServer):
    """Serve on an already-listening socket. Skips TCPServer.__init__, which would create (and,
    under RestrictAddressFamilies=none, fail to create) a socket of its own."""
    def __init__(self, sock, handler):
        socketserver.BaseServer.__init__(self, sock.getsockname(), handler)
        self.socket = sock
        self.server_name, self.server_port = self.server_address[:2]


def make_server():
    """Use the listening socket systemd passes in (socket activation, see poll.socket) if there is
    one, so the service itself can run with no network access; otherwise bind HOST:PORT."""
    if os.environ.get("LISTEN_PID") == str(os.getpid()) and os.environ.get("LISTEN_FDS") == "1":
        sock = socket.socket(fileno=3)  # SD_LISTEN_FDS_START
        return InheritedSocketServer(sock, Handler), f"systemd socket {sock.getsockname()}"
    return ThreadingHTTPServer((HOST, PORT), Handler), f"http://{HOST}:{PORT}"

if __name__ == "__main__":
    init_db()
    server, where = make_server()
    print(f"poll server on {where}", flush=True)
    server.serve_forever()
