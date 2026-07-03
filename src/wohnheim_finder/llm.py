from __future__ import annotations

import json
import os
from urllib import request


SYSTEM_PROMPT = """You draft German student housing outreach emails.
Rules:
- Do not invent financial, family, religious, medical, or eviction facts.
- Use only facts provided by the applicant profile and residence metadata.
- If an important detail is missing, use a bracketed placeholder.
- Keep the tone respectful, urgent, concrete, and not manipulative.
- Ask for next steps, waiting list, emergency option, or required documents.
- Do not claim the applicant is being kicked out unless that exact fact is provided.
"""


def generate_with_openai(prompt: str) -> str | None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
    }
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{base_url}/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=45) as response:
        result = json.loads(response.read().decode("utf-8"))
    return result["choices"][0]["message"]["content"].strip()

