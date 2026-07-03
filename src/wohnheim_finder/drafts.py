from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .categories import category_label
from .config import load_applicant
from .llm import generate_with_openai
from .mailer import write_eml
from .store import add_message, last_sent_message, list_residences, next_sequence
from .utils import ensure_dir, now_iso, slugify


def generate_due_drafts(
    conn,
    applicant_path: str | Path,
    outbox_dir: str | Path = "outbox",
    follow_up_days: int = 3,
    use_ai: bool = False,
    limit: int | None = None,
) -> dict[str, int]:
    applicant = load_applicant(applicant_path)
    outbox = ensure_dir(outbox_dir)
    stats = {"initial": 0, "follow_up": 0, "skipped": 0}

    for residence in list_residences(conn):
        if limit is not None and stats["initial"] + stats["follow_up"] >= limit:
            break
        if residence["status"] not in {"active", "priority"}:
            stats["skipped"] += 1
            continue

        sequence = next_sequence(conn, residence["id"])
        if sequence == 0:
            kind = "initial"
            scheduled_at = now_iso()
        else:
            last_sent = last_sent_message(conn, residence["id"])
            if not last_sent:
                stats["skipped"] += 1
                continue
            sent_at = datetime.fromisoformat(last_sent["sent_at"])
            due_at = sent_at + timedelta(days=follow_up_days)
            if due_at > datetime.now(timezone.utc):
                stats["skipped"] += 1
                continue
            kind = "follow_up"
            scheduled_at = due_at.replace(microsecond=0).isoformat()

        subject, body = build_message(dict(residence), applicant, sequence, use_ai=use_ai)
        eml_path = ""
        if residence["email"]:
            eml_name = f"{residence['id']:04d}-{sequence:02d}-{slugify(residence['name'])}.eml"
            eml_path = str(Path(outbox) / eml_name)
            write_eml(eml_path, residence["email"], subject, body)
        add_message(conn, residence["id"], sequence, kind, subject, body, scheduled_at, eml_path)
        stats[kind] += 1

    return stats


def build_message(
    residence: dict[str, Any],
    applicant_config: dict[str, Any],
    sequence: int,
    use_ai: bool = False,
) -> tuple[str, str]:
    applicant = applicant_config.get("applicant", {})
    move_in = applicant.get("desired_move_in") or "[gewünschtes Einzugsdatum]"
    name = applicant.get("full_name") or "[Ihr Name]"
    university = applicant.get("university") or "[Universität]"
    program = applicant.get("program") or "[Studiengang]"
    max_rent = applicant.get("max_warm_rent_eur") or "[maximale Warmmiete]"
    residence_name = residence.get("name") or "Ihr Wohnheim"

    if sequence == 0:
        subject = f"Dringende Anfrage Wohnheimplatz ab {move_in}"
    else:
        subject = f"Freundliche Nachfrage: Wohnheimplatz ab {move_in}"

    if use_ai:
        prompt = _prompt_for_ai(residence, applicant_config, sequence, subject)
        try:
            generated = generate_with_openai(prompt)
        except Exception as exc:
            generated = None
            body = _fallback_message(
                residence, applicant_config, sequence, error_note=f"[AI fallback: {exc}]"
            )
        if generated:
            return subject, generated
        if "body" in locals():
            return subject, body

    return subject, _fallback_message(residence, applicant_config, sequence)


def _prompt_for_ai(
    residence: dict[str, Any],
    applicant_config: dict[str, Any],
    sequence: int,
    subject: str,
) -> str:
    return (
        f"Subject: {subject}\n"
        f"Sequence: {'initial email' if sequence == 0 else 'follow-up email'}\n"
        f"Residence metadata: {residence}\n"
        f"Applicant profile and truthful reasons: {applicant_config}\n\n"
        "Draft only the German email body. Keep it under 220 words."
    )


def _fallback_message(
    residence: dict[str, Any],
    applicant_config: dict[str, Any],
    sequence: int,
    error_note: str = "",
) -> str:
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
    category = residence.get("category") or "other_unknown"

    reason_text = "\n".join(f"- {reason}" for reason in reasons) or "- [Konkreten, belegbaren Grund ergänzen]"
    attachment_text = ", ".join(attachments) if attachments else "[Immatrikulationsbescheinigung, Ausweis, Finanzierungsnachweis, weitere Unterlagen]"
    community_line = ""
    if category in {"catholic_church", "protestant_church", "ecumenical_christian", "christian_other"}:
        community_line = (
            "\nFalls bei Ihnen Engagement im Hausleben, ein Motivationsschreiben oder eine Referenz erforderlich ist, "
            "reiche ich das gerne kurzfristig nach."
        )
    elif category == "public_student_union":
        community_line = (
            "\nFalls es Härtefall-, Nachrück- oder Kontingentmöglichkeiten gibt, wäre ich für einen Hinweis sehr dankbar."
        )
    elif category == "commercial_private":
        community_line = "\nIch bin auch für kurzfristige, befristete oder kleinere Zimmer/Appartements offen."

    if sequence == 0:
        body = f"""Sehr geehrte Damen und Herren,

mein Name ist {name}. Ich studiere {program} im {semester}. Semester an der {university} und suche sehr dringend einen Wohnheimplatz ab {desired_move_in}.

Meine Situation ist aktuell:
{reason_text}
- Aktuelle Wohnsituation: {current_housing}
- Finanzielle Obergrenze: ca. {max_rent} EUR warm monatlich

Ich frage deshalb direkt an, ob es bei {residence.get('name', 'Ihnen')} kurzfristig einen freien Platz, eine Nachrückmöglichkeit, eine Warteliste oder eine andere passende Option gibt. Ich bin flexibel bei Zimmergröße, Wohnform und Einzugsdatum, solange der Platz realistisch finanzierbar ist.{community_line}

Folgende Unterlagen kann ich sofort senden: {attachment_text}.

Sie erreichen mich jederzeit per E-Mail unter {email} oder telefonisch unter {phone}. Vielen Dank für jede Rückmeldung und auch für Hinweise, falls ich mich zusätzlich über ein Formular bewerben muss.

Mit freundlichen Grüßen
{name}"""
    else:
        body = f"""Sehr geehrte Damen und Herren,

ich wollte freundlich zu meiner Anfrage wegen eines Wohnheimplatzes ab {desired_move_in} nachfragen.

Die Wohnungssuche ist für mich weiterhin dringend, weil:
{reason_text}

Ich bin weiterhin flexibel bei Zimmergröße, Wohnform und Einzugsdatum und kann alle erforderlichen Unterlagen kurzfristig nachreichen. Falls es eine Warteliste, einen frei werdenden Platz, ein Nachrückverfahren oder eine Härtefallprüfung gibt, wäre ich für einen kurzen Hinweis sehr dankbar.

Vielen Dank im Voraus für Ihre Rückmeldung.

Mit freundlichen Grüßen
{name}

Kontakt: {email} | {phone}"""

    if error_note:
        body += f"\n\n{error_note}"
    body += f"\n\nKategorie intern: {category_label(category)}"
    return body

