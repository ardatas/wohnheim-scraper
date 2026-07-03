from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib import request

from .utils import load_dotenv


SYSTEM_PROMPT = """You draft German student housing outreach emails.
Rules:
- Do not invent financial, family, religious, medical, or eviction facts.
- Use only facts provided by the applicant profile and residence metadata.
- If an important detail is missing, use a bracketed placeholder.
- Keep the tone respectful, urgent, concrete, and not manipulative.
- Ask for next steps, waiting list, emergency option, or required documents.
- Do not claim the applicant is being kicked out unless that exact fact is provided.
"""


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    base_url: str
    model: str
    provider: str


def resolve_llm_config() -> LLMConfig | None:
    load_dotenv()

    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if deepseek_key:
        return LLMConfig(
            api_key=deepseek_key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip().rstrip("/"),
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash").strip(),
            provider="deepseek",
        )

    generic_key = os.getenv("LLM_API_KEY", "").strip()
    if generic_key:
        return LLMConfig(
            api_key=generic_key,
            base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com").strip().rstrip("/"),
            model=os.getenv("LLM_MODEL", "deepseek-v4-flash").strip(),
            provider="generic",
        )

    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if openai_key:
        return LLMConfig(
            api_key=openai_key,
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/"),
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip(),
            provider="openai",
        )

    return None


def generate_with_llm(prompt: str) -> str | None:
    config = resolve_llm_config()
    if not config:
        return None
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
    }
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{config.base_url}/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=45) as response:
        result = json.loads(response.read().decode("utf-8"))
    return result["choices"][0]["message"]["content"].strip()


def generate_with_openai(prompt: str) -> str | None:
    return generate_with_llm(prompt)
