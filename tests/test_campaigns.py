from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from wohnheim_finder.campaigns import generate_weekly_campaign, load_recent_base_mails
from wohnheim_finder.models import Residence
from wohnheim_finder.store import connect, init_db, upsert_residence


def write_applicant(path: Path) -> None:
    path.write_text(
        """
applicant:
  full_name: "Test User"
  email: "test@example.com"
  phone: "+49 123"
  university: "Technische Universität München"
  program: "Informatik"
  semester: "2"
  desired_move_in: "so bald wie möglich"
  max_warm_rent_eur: 550
  current_housing_truth: "Meine aktuelle Zwischenmiete ist befristet."
truthful_reasons:
  - "Ich bin auf eine bezahlbare studentische Miete angewiesen."
attachments:
  - "Immatrikulationsbescheinigung"
""".strip(),
        encoding="utf-8",
    )


def test_weekly_campaign_saves_base_category_mails_and_drafts(tmp_path):
    db_path = tmp_path / "outreach.sqlite"
    conn = connect(db_path)
    init_db(conn)
    upsert_residence(
        conn,
        Residence(
            name="Catholic Dorm 1",
            category="catholic_church",
            email="one@example.com",
        ),
    )
    upsert_residence(
        conn,
        Residence(
            name="Catholic Dorm 2",
            category="catholic_church",
            email="two@example.com",
        ),
    )
    upsert_residence(
        conn,
        Residence(
            name="Private Dorm",
            category="commercial_private",
            email="three@example.com",
        ),
    )
    applicant = tmp_path / "applicant.yaml"
    write_applicant(applicant)

    result = generate_weekly_campaign(
        conn,
        applicant,
        campaigns_dir=tmp_path / "campaigns",
        outbox_dir=tmp_path / "outbox",
        use_ai=False,
        now=datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc),
    )

    assert result.week_id == "2026-W27"
    assert result.base_path.exists()
    assert set(result.category_paths) == {"catholic_church", "commercial_private"}
    assert all(path.exists() for path in result.category_paths.values())
    assert result.drafts_created == 3

    rows = conn.execute(
        """
        SELECT r.category, m.body
        FROM messages m
        JOIN residences r ON r.id = m.residence_id
        ORDER BY r.category, r.name
        """
    ).fetchall()
    catholic_bodies = [row["body"] for row in rows if row["category"] == "catholic_church"]
    assert len(catholic_bodies) == 2
    assert catholic_bodies[0] == catholic_bodies[1]
    assert "Gemeinschaftsleben" in catholic_bodies[0]
    assert "kleinere, befristete" in [row["body"] for row in rows if row["category"] == "commercial_private"][0]


def test_load_recent_base_mails_returns_last_two(tmp_path):
    root = tmp_path / "campaigns"
    old = root / "2026-W25" / "20260620T120000Z" / "base" / "base-mail.md"
    middle = root / "2026-W26" / "20260627T120000Z" / "base" / "base-mail.md"
    new = root / "2026-W27" / "20260703T120000Z" / "base" / "base-mail.md"
    for idx, path in enumerate([old, middle, new], start=1):
        path.parent.mkdir(parents=True)
        path.write_text(f"base {idx}", encoding="utf-8")

    recent = load_recent_base_mails(root, limit=2)

    assert recent == ["base 3", "base 2"]

