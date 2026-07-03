from __future__ import annotations

import html
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .mailer import build_email, send_smtp
from .store import (
    connect,
    get_message,
    get_setting,
    init_db,
    list_messages,
    list_residences,
    set_setting,
    update_message_status,
)
from .utils import now_iso


def serve_dashboard(db_path: str | Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    class Handler(ReviewHandler):
        database_path = str(db_path)

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Review dashboard: http://{host}:{port}")
    server.serve_forever()


class ReviewHandler(BaseHTTPRequestHandler):
    database_path = "data/outreach.sqlite"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(self._dashboard())
            return
        if parsed.path == "/message":
            message_id = int(parse_qs(parsed.query).get("id", ["0"])[0])
            self._send_html(self._message_page(message_id))
            return
        if parsed.path == "/eml":
            message_id = int(parse_qs(parsed.query).get("id", ["0"])[0])
            self._send_eml(message_id)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/action":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        form = parse_qs(self.rfile.read(length).decode("utf-8"))
        action = form.get("action", [""])[0]
        conn = self._conn()
        try:
            if action == "pause":
                set_setting(conn, "outreach_paused", "true")
            elif action == "resume":
                set_setting(conn, "outreach_paused", "false")
            else:
                message_id = int(form.get("message_id", ["0"])[0])
                if action == "approve":
                    update_message_status(conn, message_id, "approved", {"approved_at": now_iso()})
                elif action == "skip":
                    update_message_status(conn, message_id, "skipped")
                elif action == "mark_sent":
                    update_message_status(conn, message_id, "sent", {"sent_at": now_iso()})
                elif action == "send":
                    self._send_message_action(conn, message_id, form)
        except Exception as exc:
            if action == "send" and form.get("message_id"):
                update_message_status(
                    conn,
                    int(form.get("message_id", ["0"])[0]),
                    "error",
                    {"error": str(exc)},
                )
            else:
                raise
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()

    def _conn(self):
        conn = connect(self.database_path)
        init_db(conn)
        return conn

    def _send_message_action(self, conn, message_id: int, form: dict[str, list[str]]) -> None:
        confirm = form.get("confirm", [""])[0].strip()
        if confirm != "SEND":
            raise RuntimeError("Type SEND to confirm SMTP sending.")
        msg = get_message(conn, message_id)
        if not msg:
            raise RuntimeError("Message not found.")
        if msg["status"] != "approved":
            raise RuntimeError("Message must be approved before sending.")
        if not msg["email"]:
            raise RuntimeError("Residence has no email address. Use the website/contact form and mark as sent manually.")
        send_smtp(msg["email"], msg["subject"], msg["body"])
        update_message_status(conn, message_id, "sent", {"sent_at": now_iso(), "error": ""})

    def _dashboard(self) -> str:
        conn = self._conn()
        paused = get_setting(conn, "outreach_paused", "false") == "true"
        residences = list_residences(conn, include_inactive=True)
        messages = list_messages(conn)
        grouped: dict[str, int] = {}
        for row in residences:
            grouped[row["category"]] = grouped.get(row["category"], 0) + 1

        message_rows = "\n".join(self._message_row(row) for row in messages) or (
            "<tr><td colspan='7'>No drafts yet. Run <code>wohnheim generate-drafts</code>.</td></tr>"
        )
        category_items = "\n".join(
            f"<li><strong>{html.escape(category)}</strong>: {count}</li>"
            for category, count in sorted(grouped.items())
        )
        pause_button = (
            "<button name='action' value='resume'>Resume drafting</button>"
            if paused
            else "<button name='action' value='pause'>Stop/pause follow-ups</button>"
        )
        status = "PAUSED" if paused else "ACTIVE"
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Wohnheim Outreach Review</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; margin: 24px; color: #172026; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
    th, td {{ border-bottom: 1px solid #d8dee4; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f6f8fa; }}
    .status {{ display: inline-block; padding: 2px 8px; border-radius: 6px; background: #eef2f7; }}
    .actions form {{ display: inline; margin-right: 4px; }}
    input[type=text] {{ width: 72px; }}
    code {{ background: #f6f8fa; padding: 2px 4px; border-radius: 4px; }}
    .notice {{ padding: 12px; border: 1px solid #d0d7de; border-radius: 8px; background: #fbfbfc; }}
  </style>
</head>
<body>
  <h1>Wohnheim Outreach Review</h1>
  <div class="notice">
    <strong>Status:</strong> {status}. Drafting/sending is manual-control only.
    SMTP Send requires the message to be approved and the confirmation text <code>SEND</code>.
  </div>
  <form method="post" action="/action" style="margin-top: 12px;">{pause_button}</form>
  <h2>Categories</h2>
  <ul>{category_items}</ul>
  <h2>Drafts</h2>
  <table>
    <thead>
      <tr><th>ID</th><th>Residence</th><th>Category</th><th>To</th><th>Kind</th><th>Status</th><th>Actions</th></tr>
    </thead>
    <tbody>{message_rows}</tbody>
  </table>
</body>
</html>"""

    def _message_row(self, row) -> str:
        to_email = row["email"] or "(website/form)"
        error = f"<br><small>{html.escape(row['error'])}</small>" if row["error"] else ""
        return f"""<tr>
  <td>{row['id']}</td>
  <td><a href="/message?id={row['id']}">{html.escape(row['name'])}</a></td>
  <td>{html.escape(row['category'])}</td>
  <td>{html.escape(to_email)}</td>
  <td>{html.escape(row['kind'])} #{row['sequence']}</td>
  <td><span class="status">{html.escape(row['status'])}</span>{error}</td>
  <td class="actions">
    <form method="post" action="/action"><input type="hidden" name="message_id" value="{row['id']}"><button name="action" value="approve">Approve</button></form>
    <form method="post" action="/action"><input type="hidden" name="message_id" value="{row['id']}"><button name="action" value="skip">Skip</button></form>
    <form method="post" action="/action"><input type="hidden" name="message_id" value="{row['id']}"><button name="action" value="mark_sent">Mark sent</button></form>
    <a href="/eml?id={row['id']}">Download .eml</a>
    <form method="post" action="/action"><input type="hidden" name="message_id" value="{row['id']}"><input type="text" name="confirm" placeholder="SEND"><button name="action" value="send">SMTP Send</button></form>
  </td>
</tr>"""

    def _message_page(self, message_id: int) -> str:
        conn = self._conn()
        msg = get_message(conn, message_id)
        if not msg:
            return "<h1>Message not found</h1><p><a href='/'>Back</a></p>"
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(msg['subject'])}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; margin: 24px; color: #172026; }}
    pre {{ white-space: pre-wrap; border: 1px solid #d0d7de; border-radius: 8px; padding: 16px; background: #fbfbfc; }}
  </style>
</head>
<body>
  <p><a href="/">Back</a></p>
  <h1>{html.escape(msg['name'])}</h1>
  <p><strong>To:</strong> {html.escape(msg['email'] or '(website/contact form)')}</p>
  <p><strong>Subject:</strong> {html.escape(msg['subject'])}</p>
  <pre>{html.escape(msg['body'])}</pre>
</body>
</html>"""

    def _send_eml(self, message_id: int) -> None:
        conn = self._conn()
        msg = get_message(conn, message_id)
        if not msg:
            self.send_error(404)
            return
        if msg["eml_path"] and Path(msg["eml_path"]).exists():
            payload = Path(msg["eml_path"]).read_bytes()
        else:
            payload = bytes(build_email(msg["email"], msg["subject"], msg["body"]))
        filename = f"wohnheim-message-{message_id}.eml"
        self.send_response(200)
        self.send_header("Content-Type", "message/rfc822")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_html(self, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"[{timestamp}] {fmt % args}")

