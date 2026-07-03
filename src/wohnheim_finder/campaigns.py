from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .categories import category_label
from .config import load_applicant
from .llm import generate_with_llm
from .mailer import write_eml
from .store import add_message, list_residences, next_sequence
from .utils import ensure_dir, slugify


@dataclass(frozen=True)
class CampaignResult:
    week_id: str
    timestamp: str
    base_path: Path
    category_paths: dict[str, Path]
    drafts_created: int
    skipped: int


def generate_weekly_campaign(
    conn,
    applicant_path: str | Path,
    campaigns_dir: str | Path = "campaigns",
    outbox_dir: str | Path = "outbox",
    use_ai: bool = False,
    create_drafts: bool = True,
    limit_categories: list[str] | None = None,
    now: datetime | None = None,
) -> CampaignResult:
    now = now or datetime.now(timezone.utc)
    week_id = iso_week_id(now)
    timestamp = campaign_timestamp(now)
    applicant_config = load_applicant(applicant_path)
    campaign_dir = ensure_dir(Path(campaigns_dir) / week_id / timestamp)
    base_dir = ensure_dir(campaign_dir / "base")
    categories_dir = ensure_dir(campaign_dir / "categories")
    outbox_week_dir = ensure_dir(Path(outbox_dir) / week_id / timestamp)

    residences = [dict(row) for row in list_residences(conn) if row["status"] in {"active", "priority"}]
    grouped = group_residences_by_category(residences)
    if limit_categories:
        allowed = set(limit_categories)
        grouped = {category: rows for category, rows in grouped.items() if category in allowed}

    recent_base_mails = load_recent_base_mails(campaigns_dir, limit=2)
    base_subject = build_weekly_subject(applicant_config, week_id)
    base_body = build_base_mail(applicant_config, recent_base_mails, week_id, use_ai=use_ai)
    base_path = base_dir / "base-mail.md"
    write_markdown_mail(
        base_path,
        {
            "type": "weekly_base_mail",
            "week": week_id,
            "generated_at": now.isoformat(),
            "subject": base_subject,
            "previous_context_count": str(len(recent_base_mails)),
        },
        base_body,
    )

    category_paths: dict[str, Path] = {}
    category_bodies: dict[str, str] = {}
    for category, rows in grouped.items():
        body = build_category_mail(
            category,
            rows,
            applicant_config,
            base_subject,
            base_body,
            week_id,
            use_ai=use_ai,
        )
        category_bodies[category] = body
        path = categories_dir / f"{slugify(category)}.md"
        category_paths[category] = path
        write_markdown_mail(
            path,
            {
                "type": "weekly_category_mail",
                "week": week_id,
                "generated_at": now.isoformat(),
                "category": category,
                "category_label": category_label(category),
                "subject": base_subject,
                "residence_count": str(len(rows)),
            },
            body,
        )

    drafts_created = 0
    skipped = 0
    if create_drafts:
        for category, rows in grouped.items():
            category_outbox = ensure_dir(outbox_week_dir / slugify(category))
            body = category_bodies[category]
            for residence in rows:
                sequence = next_sequence(conn, residence["id"])
                eml_path = ""
                if residence["email"]:
                    eml_name = f"{residence['id']:04d}-{sequence:02d}-{slugify(residence['name'])}.eml"
                    eml_path = str(category_outbox / eml_name)
                    write_eml(eml_path, residence["email"], base_subject, body)
                add_message(
                    conn,
                    residence["id"],
                    sequence,
                    "weekly_campaign",
                    base_subject,
                    body,
                    now.replace(microsecond=0).isoformat(),
                    eml_path,
                )
                drafts_created += 1
    else:
        skipped = sum(len(rows) for rows in grouped.values())

    return CampaignResult(
        week_id=week_id,
        timestamp=timestamp,
        base_path=base_path,
        category_paths=category_paths,
        drafts_created=drafts_created,
        skipped=skipped,
    )


def iso_week_id(value: datetime) -> str:
    year, week, _weekday = value.isocalendar()
    return f"{year}-W{week:02d}"


def campaign_timestamp(value: datetime) -> str:
    utc_value = value.astimezone(timezone.utc)
    return utc_value.strftime("%Y%m%dT%H%M%SZ")


def group_residences_by_category(residences: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for residence in residences:
        grouped[residence.get("category") or "other_unknown"].append(residence)
    return dict(sorted(grouped.items(), key=lambda item: item[0]))


def load_recent_base_mails(campaigns_dir: str | Path, limit: int = 2) -> list[str]:
    root = Path(campaigns_dir)
    if not root.exists():
        return []
    files = sorted(
        root.glob("*/**/base/base-mail.md"),
        key=lambda path: (path.stat().st_mtime, str(path)),
        reverse=True,
    )
    mails: list[str] = []
    for path in files[:limit]:
        mails.append(path.read_text(encoding="utf-8"))
    return mails


def build_weekly_subject(applicant_config: dict[str, Any], week_id: str) -> str:
    applicant = applicant_config.get("applicant", {})
    move_in = applicant.get("desired_move_in") or "[gewünschtes Einzugsdatum]"
    return f"Dringende Anfrage Wohnheimplatz ab {move_in}"


def build_base_mail(
    applicant_config: dict[str, Any],
    recent_base_mails: list[str],
    week_id: str,
    use_ai: bool = False,
) -> str:
    if use_ai:
        prompt = base_mail_prompt(applicant_config, recent_base_mails, week_id)
        try:
            generated = generate_with_llm(prompt)
        except Exception as exc:
            generated = None
            fallback_note = f"\n\n[AI fallback: {exc}]"
        else:
            fallback_note = ""
        if generated:
            return generated
    else:
        fallback_note = ""
    return fallback_base_mail(applicant_config, week_id) + fallback_note


def build_category_mail(
    category: str,
    residences: list[dict[str, Any]],
    applicant_config: dict[str, Any],
    subject: str,
    base_body: str,
    week_id: str,
    use_ai: bool = False,
) -> str:
    if use_ai:
        prompt = category_mail_prompt(category, residences, applicant_config, subject, base_body, week_id)
        try:
            generated = generate_with_llm(prompt)
        except Exception as exc:
            generated = None
            fallback_note = f"\n\n[AI fallback: {exc}]"
        else:
            fallback_note = ""
        if generated:
            return generated
    else:
        fallback_note = ""
    return fallback_category_mail(category, applicant_config, week_id) + fallback_note


def base_mail_prompt(
    applicant_config: dict[str, Any],
    recent_base_mails: list[str],
    week_id: str,
) -> str:
    previous = "\n\n--- previous base mail ---\n\n".join(recent_base_mails) or "No previous base mails."
    return (
        f"Write this week's German base outreach email for student housing.\n"
        f"Week: {week_id}\n"
        f"Applicant profile and truthful reasons: {applicant_config}\n\n"
        "Use the last two base mails as memory/context. Improve continuity without saying that this is an automated campaign.\n"
        "Do not invent any financial, eviction, medical, family, religious, or visa facts.\n"
        "Use bracketed placeholders for missing facts.\n"
        "Write only the email body, under 230 words.\n\n"
        f"Last base mails:\n{previous}"
    )


def category_mail_prompt(
    category: str,
    residences: list[dict[str, Any]],
    applicant_config: dict[str, Any],
    subject: str,
    base_body: str,
    week_id: str,
) -> str:
    sampled = [
        {
            "name": row.get("name", ""),
            "city": row.get("city", ""),
            "eligibility": row.get("eligibility", ""),
            "notes": row.get("notes", ""),
        }
        for row in residences[:8]
    ]
    return (
        f"Tailor this German weekly student-housing email for one residence category.\n"
        f"Week: {week_id}\n"
        f"Subject: {subject}\n"
        f"Category: {category} ({category_label(category)})\n"
        f"Category residence examples: {sampled}\n"
        f"Applicant profile and truthful reasons: {applicant_config}\n\n"
        "Base mail:\n"
        f"{base_body}\n\n"
        "Requirements:\n"
        "- Write one category-level email body that can be sent unchanged to every dorm in this category.\n"
        "- Do not mention a specific dorm name.\n"
        "- Use 'bei Ihnen' or 'in Ihrem Wohnheim' for the recipient.\n"
        "- Keep it truthful, urgent, polite, and under 240 words.\n"
        "- Do not invent facts. Use placeholders when needed.\n"
        "- Include the category-specific angle naturally."
    )


def fallback_base_mail(applicant_config: dict[str, Any], week_id: str) -> str:
    applicant = applicant_config.get("applicant", {})
    reasons = [str(r).strip() for r in applicant_config.get("truthful_reasons", []) if str(r).strip()]
    attachments = [str(a).strip() for a in applicant_config.get("attachments", []) if str(a).strip()]
    name = applicant.get("full_name") or "[Ihr Name]"
    university = applicant.get("university") or "[Universität]"
    program = applicant.get("program") or "[Studiengang]"
    semester = applicant.get("semester") or "[Semester]"
    desired_move_in = applicant.get("desired_move_in") or "[gewünschtes Einzugsdatum]"
    max_rent = applicant.get("max_warm_rent_eur") or "[maximale Warmmiete]"
    current_housing = applicant.get("current_housing_truth") or "[Ihre aktuelle Wohnsituation wahrheitsgemäß ergänzen]"
    phone = applicant.get("phone") or "[Telefonnummer]"
    email = applicant.get("email") or "[E-Mail]"
    reason_text = "\n".join(f"- {reason}" for reason in reasons) or "- [Konkreten, belegbaren Grund ergänzen]"
    attachment_text = ", ".join(attachments) if attachments else "[Unterlagen ergänzen]"

    return f"""Sehr geehrte Damen und Herren,

mein Name ist {name}. Ich studiere {program} im {semester}. Semester an der {university} und suche weiterhin dringend einen bezahlbaren Wohnheimplatz ab {desired_move_in}.

Meine aktuelle Situation:
{reason_text}
- Aktuelle Wohnsituation: {current_housing}
- Finanzielle Obergrenze: ca. {max_rent} EUR warm monatlich

Ich kann kurzfristig reagieren, Unterlagen sofort nachreichen und einen passenden Platz verbindlich annehmen. Für mich kommen auch kleinere Zimmer, Wohngemeinschaften, befristete Angebote, Nachrückplätze oder Wartelistenplätze infrage.

Folgende Unterlagen kann ich kurzfristig senden: {attachment_text}.

Sie erreichen mich per E-Mail unter {email} oder telefonisch unter {phone}. Vielen Dank für jeden Hinweis zum passenden Bewerbungsweg, zu freien Plätzen oder zu kurzfristigen Nachrückmöglichkeiten.

Mit freundlichen Grüßen
{name}"""


def fallback_category_mail(category: str, applicant_config: dict[str, Any], week_id: str) -> str:
    base = fallback_base_mail(applicant_config, week_id)
    angle = category_angle(category)
    return base.replace(
        "Ich kann kurzfristig reagieren, Unterlagen sofort nachreichen und einen passenden Platz verbindlich annehmen.",
        f"{angle}\n\nIch kann kurzfristig reagieren, Unterlagen sofort nachreichen und einen passenden Platz verbindlich annehmen.",
    )


def category_angle(category: str) -> str:
    if category in {"catholic_church", "protestant_church", "ecumenical_christian", "christian_other"}:
        return (
            "Gerade ein Haus mit verbindlichem Gemeinschaftsleben passt gut zu meiner Suche; "
            "falls ein Motivationsschreiben, ein Gespräch oder eine Referenz nötig ist, reiche ich das gerne nach."
        )
    if category == "public_student_union":
        return (
            "Falls es Härtefall-, Nachrück-, Kontingent- oder Wartelistenmöglichkeiten gibt, "
            "wäre ich für einen Hinweis sehr dankbar."
        )
    if category == "commercial_private":
        return (
            "Ich bin auch für kleinere, befristete oder kurzfristig frei werdende Zimmer/Appartements offen, "
            "sofern die Warmmiete für mein studentisches Budget realistisch bleibt."
        )
    if category == "youth_housing":
        return (
            "Falls Altersgrenzen, Ausbildungsstatus oder besondere Unterlagen geprüft werden müssen, "
            "reiche ich diese Informationen gerne direkt nach."
        )
    if category == "social_nonprofit_association":
        return (
            "Falls Ihre Vergabe über Auswahlkriterien, ein persönliches Gespräch oder Empfehlungsschreiben läuft, "
            "bereite ich die Unterlagen gerne kurzfristig vor."
        )
    if category == "specialized_field":
        return (
            "Falls fachliche oder persönliche Zugangsvoraussetzungen gelten, bitte ich um einen kurzen Hinweis, "
            "damit ich meine Eignung ehrlich prüfen kann."
        )
    return "Ich bin beim konkreten Wohnmodell flexibel und richte mich nach Ihrem Bewerbungsprozess."


def write_markdown_mail(path: str | Path, metadata: dict[str, str], body: str) -> None:
    p = Path(path)
    ensure_dir(p.parent)
    header = "\n".join(f"{key}: {value}" for key, value in metadata.items())
    p.write_text(f"---\n{header}\n---\n\n{body.strip()}\n", encoding="utf-8")

