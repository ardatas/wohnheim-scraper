from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

from .utils import ensure_dir, load_dotenv


def build_email(
    to_email: str,
    subject: str,
    body: str,
    from_email: str | None = None,
) -> EmailMessage:
    from_email = from_email or os.getenv("SMTP_FROM") or os.getenv("SMTP_USERNAME") or ""
    msg = EmailMessage()
    msg["To"] = to_email
    msg["From"] = from_email
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg.set_content(body)
    return msg


def write_eml(
    path: str | Path,
    to_email: str,
    subject: str,
    body: str,
    from_email: str | None = None,
) -> Path:
    p = Path(path)
    ensure_dir(p.parent)
    msg = build_email(to_email, subject, body, from_email)
    p.write_bytes(bytes(msg))
    return p


def send_smtp(to_email: str, subject: str, body: str) -> None:
    load_dotenv()
    host = os.getenv("SMTP_HOST", "").strip()
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    if not host or not username or not password:
        raise RuntimeError("SMTP_HOST, SMTP_USERNAME, and SMTP_PASSWORD must be configured in .env")

    port = int(os.getenv("SMTP_PORT", "587"))
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes"}
    msg = build_email(to_email, subject, body)
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        if use_tls:
            smtp.starttls()
        smtp.login(username, password)
        smtp.send_message(msg)

