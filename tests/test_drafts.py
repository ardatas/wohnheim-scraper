from wohnheim_finder.drafts import build_message


def test_fallback_draft_uses_placeholders_not_false_eviction():
    residence = {"name": "Testwohnheim", "category": "public_student_union"}
    applicant = {
        "applicant": {"full_name": "A", "university": "TUM", "program": "Informatik"},
        "truthful_reasons": ["Ich habe ein knappes studentisches Budget."],
        "attachments": ["Immatrikulationsbescheinigung"],
    }
    _subject, body = build_message(residence, applicant, sequence=0)
    assert "gekündigt" not in body.lower()
    assert "Ich habe ein knappes studentisches Budget." in body
    assert "[Ihre aktuelle Wohnsituation wahrheitsgemäß ergänzen]" in body

