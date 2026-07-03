from __future__ import annotations

import csv
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


EMAIL_RE = re.compile(r"[\w.!#$%&'*+/=?^_`{|}~-]+@[\w.-]+\.[A-Za-z]{2,}")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def slugify(value: str, fallback: str = "item") -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return slug or fallback


def clean_space(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def deobfuscate_email_text(text: str) -> str:
    replacements = {
        " spam prevention @": "@",
        " spam-prevention @": "@",
        " [at] ": "@",
        " (at) ": "@",
        "(at)": "@",
        " at ": "@",
        " dot ": ".",
    }
    result = text
    for old, new in replacements.items():
        result = result.replace(old, new)
    result = re.sub(r"\s*@\s*", "@", result)
    result = re.sub(r"\s*\.\s*", ".", result)
    return result


def extract_emails(text: str) -> list[str]:
    deobfuscated = deobfuscate_email_text(text)
    emails = {m.group(0).strip(".,;:()[]<>") for m in EMAIL_RE.finditer(deobfuscated)}
    return sorted(emails)


def first_nonempty(values: Iterable[str | None]) -> str:
    for value in values:
        if value:
            stripped = str(value).strip()
            if stripped:
                return stripped
    return ""


def read_csv(path: str | Path) -> list[dict[str, str]]:
    p = Path(path)
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8") as f:
        return [dict(row) for row in csv.DictReader(f)]


def load_dotenv(path: str | Path = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for raw_line in p.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)

