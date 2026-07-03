from __future__ import annotations

CATEGORIES: dict[str, str] = {
    "public_student_union": "Public student union / Studierendenwerk",
    "catholic_church": "Catholic / katholische Träger",
    "protestant_church": "Protestant / evangelische Träger",
    "ecumenical_christian": "Ecumenical Christian / ökumenisch",
    "christian_other": "Other Christian / christlich",
    "youth_housing": "Youth housing / Jugendwohnen",
    "social_nonprofit_association": "Association, foundation, or nonprofit",
    "commercial_private": "Commercial private operator",
    "municipal": "Municipal / city-run",
    "specialized_field": "Specialized eligibility",
    "short_term": "Short-term fallback",
    "other_unknown": "Other / needs review",
}

CATEGORY_RULES: dict[str, tuple[str, ...]] = {
    "public_student_union": (
        "studierendenwerk",
        "studentenwerk",
        "stwm",
        "wohnanlage",
        "olympisches dorf",
        "studentenstadt",
    ),
    "catholic_church": (
        "kathol",
        "erzdiözese",
        "erzbistum",
        "kolping",
        "caritas",
        "newman",
        "pater-rupert",
        "roncalli",
        "albertus",
        "eomuc",
        "don bosco",
        "schulschwestern",
        "kkv",
        "st. benedikt",
        "deutsche burse",
    ),
    "protestant_church": (
        "evangel",
        "eswm",
        "evang.-luth",
        "waisenhausverein",
        "esg",
        "georg lanzenstiel",
        "hochschulhaus garching",
    ),
    "ecumenical_christian": (
        "ökumen",
        "oekumen",
        "oecumen",
        "collegium oecumenicum",
        "interreligious",
    ),
    "christian_other": (
        "christlich",
        "cvjm",
        "john-mott",
        "kreuzkirche",
    ),
    "youth_housing": (
        "jugendwohn",
        "jugendwohnen",
        "in via",
        "auszubildende",
        "18-25",
        "18-27",
    ),
    "social_nonprofit_association": (
        "e.v.",
        "verein",
        "stiftung",
        "geschwister scholl",
        "maßmann",
        "massmann",
        "bllv",
        "marchionini",
        "mühlfenzl",
        "van calker",
    ),
    "commercial_private": (
        "the fizz",
        "campus viva",
        "uni apart",
        "die zimmerei",
        "youniq",
        "vonder",
        "the base",
        "home & co",
        "studio m",
        "apian",
        "domino",
        "the flag",
    ),
    "municipal": (
        "stadt dachau",
        "municipal",
        "stadt ",
    ),
    "specialized_field": (
        "medizin",
        "architektur",
        "bauwesen",
        "nur medizinstudierende",
        "fachrichtungen",
    ),
    "short_term": (
        "jugendherberge",
        "hostel",
        "short stay",
        "temporary",
    ),
}


def classify_residence(*parts: str) -> str:
    text = " ".join(p for p in parts if p).lower()
    scores: dict[str, int] = {}
    for category, keywords in CATEGORY_RULES.items():
        score = sum(1 for keyword in keywords if keyword in text)
        if score:
            scores[category] = score
    if not scores:
        return "other_unknown"
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[0][0]


def category_label(category: str) -> str:
    return CATEGORIES.get(category, category)

