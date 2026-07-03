from __future__ import annotations

from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .categories import classify_residence
from .config import load_yaml
from .models import Residence
from .store import connect, init_db, upsert_residence
from .utils import clean_space, extract_emails, first_nonempty, read_csv

HOUSING_TERMS = (
    "wohnheim",
    "studenten",
    "studierenden",
    "apartment",
    "appartement",
    "kolping",
    "fizz",
    "zimmerei",
    "dorm",
    "residence",
)

PROVIDER_HINTS = (
    "almaha",
    "bllv-cimbernheim",
    "campusviva",
    "caritas-jugendwohnheim",
    "caritas-jugendwohnheime",
    "collegium-oecm",
    "cvjm-muenchen",
    "deutsche-burse",
    "donboscoschwestern",
    "ewv-muenchen",
    "hausbenedikt",
    "homeand.co",
    "imp10",
    "invia-muenchen",
    "jakob-balde",
    "jointhebase",
    "kkv",
    "kolping",
    "kreuzkirche",
    "marchionini",
    "massmannplatz",
    "newman",
    "oskarvonmillerforum",
    "prm-heim",
    "roncalli",
    "schollheim",
    "schulschwestern",
    "studentenappartements-muenchen",
    "studentenwohnheim-dachau",
    "studentenwohnheim-willi-graf",
    "the-fizz",
    "uniapart",
    "vondereurope",
    "zimmerei",
)

GENERIC_NAMES = {
    "adresse",
    "application",
    "bewerbung",
    "blog",
    "campusleben",
    "contact",
    "datenschutz",
    "de",
    "en",
    "faq",
    "fundraising",
    "häuser",
    "houses",
    "impressum",
    "kontakt",
    "links",
    "navigation",
    "privacy",
    "servicepaket",
    "studierende",
    "über uns",
    "wohnen",
    "wohnen beim studierendenwerk",
    "wohnheime",
    "wohnheimleben",
    "wohnanlagen",
    "wohnanlagen privater träger",
    "wohnheime für junge frauen",
    "wohnheime von vereinen, kirchlichen und sozialen trägern",
}

GENERIC_FRAGMENTS = (
    "aktuelles",
    "alle bilder",
    "angebote für",
    "beratung",
    "bürozeiten",
    "campus ",
    "downloads",
    "e-mail:",
    "finden sie",
    "informationen",
    "mietpreise",
    "nach oben",
    "personensuche",
    "publikationen",
    "standorte",
    "such",
    "telefon",
    "tipps",
    "überblick",
    "veranstaltungen",
    "weitere tipps",
    "what is",
    "zur übersicht",
    "association learn",
    "cms",
    "datenschutzerklärung",
    "gottesdienste",
    "hochschulgemeinden",
    "hochschulpastoral",
    "staff & board",
    "studentisches wohnen",
    "studentenleben",
    "studienförderung",
    "wohnheime speziell für junge frauen",
)


def import_seed_csv(conn, csv_path: str | Path) -> int:
    count = 0
    for row in read_csv(csv_path):
        residence = Residence.from_mapping(row)
        if not residence.name:
            continue
        if not residence.category:
            residence.category = classify_residence(
                residence.name, residence.notes, residence.url, residence.source_url
            )
        upsert_residence(conn, residence)
        count += 1
    return count


def fetch_page(url: str, timeout: int = 20) -> str:
    headers = {
        "User-Agent": "wohnheim-finder/0.1 (+manual student housing research; contact owner before reusing)"
    }
    response = requests.get(url, timeout=timeout, headers=headers)
    response.raise_for_status()
    return response.text


def extract_candidates_from_html(url: str, html: str) -> list[Residence]:
    soup = BeautifulSoup(html, "html.parser")
    title = clean_space(soup.title.get_text(" ")) if soup.title else ""
    page_text = clean_space(soup.get_text(" "))
    page_emails = extract_emails(page_text)
    candidates: list[Residence] = []

    for link in soup.find_all("a"):
        text = clean_space(link.get_text(" "))
        href = link.get("href") or ""
        if not _looks_like_candidate_name(text) or _is_bad_href(href):
            continue
        combined = f"{text} {href}".lower()
        if not _looks_like_housing_link(text, href):
            continue
        absolute_url = urljoin(url, href)
        category = classify_residence(text, absolute_url)
        candidates.append(
            Residence(
                name=text,
                category=category,
                url=absolute_url,
                source_url=url,
                notes=f"Discovered from link on {title or url}",
                priority=4,
            )
        )

    for heading in soup.find_all(["h1", "h2", "h3", "h4"]):
        name = clean_space(heading.get_text(" "))
        if not _looks_like_candidate_name(name):
            continue
        block_text = _nearby_text(heading)
        address = _guess_address(block_text)
        if not _name_has_residence_signal(name) and not address:
            continue
        combined = f"{name} {block_text}"
        if not any(term in combined.lower() for term in HOUSING_TERMS) and not _name_has_residence_signal(name):
            continue
        emails = extract_emails(block_text)
        link = heading.find_next("a")
        href = urljoin(url, link.get("href")) if link and link.get("href") else ""
        if _is_bad_href(href):
            href = ""
        candidates.append(
            Residence(
                name=name,
                category=classify_residence(combined, href),
                city=_guess_city(block_text),
                address=address,
                email=first_nonempty([emails[0] if emails else "", page_emails[0] if len(page_emails) == 1 else ""]),
                url=href,
                source_url=url,
                notes=f"Scraped from source page. Nearby text: {block_text[:500]}",
                priority=4,
            )
        )

    return candidates


def _nearby_text(node) -> str:
    parts: list[str] = []
    for sibling in node.find_all_next(limit=8):
        if sibling.name in {"h1", "h2", "h3", "h4"} and sibling is not node:
            break
        text = clean_space(sibling.get_text(" "))
        if text:
            parts.append(text)
    return clean_space(" ".join(parts))


def _looks_like_candidate_name(name: str) -> bool:
    if not name or len(name) > 100:
        return False
    lower = name.strip().lower()
    if lower in GENERIC_NAMES:
        return False
    if any(fragment in lower for fragment in GENERIC_FRAGMENTS):
        return False
    if lower.startswith(("http://", "https://")):
        return False
    if lower.startswith("www.") or " spam prevention " in lower or "(at)" in lower or "@" in lower:
        return False
    return True


def _is_bad_href(href: str) -> bool:
    lower = href.lower()
    if lower.startswith(("mailto:", "tel:")):
        return True
    bad_parts = ("datenschutz", "impressum", "privacy", "/verein", "/personen", "/staff")
    return any(part in lower for part in bad_parts)


def _looks_like_housing_link(text: str, href: str) -> bool:
    lower_text = text.lower()
    lower_href = href.lower()
    if any(term in lower_text for term in HOUSING_TERMS):
        return True
    if any(hint in lower_href for hint in PROVIDER_HINTS):
        return True
    if any(hint in lower_text for hint in PROVIDER_HINTS):
        return True
    return False


def _name_has_residence_signal(name: str) -> bool:
    lower = name.lower()
    signals = (
        "apartment",
        "appartement",
        "burse",
        "campus viva",
        "college",
        "collegium",
        "fizz",
        "haus",
        "heim",
        "kolleg",
        "residence",
        "stift",
        "studentenstadt",
        "the base",
        "wohnanlage",
        "wohnheim",
        "zimmerei",
    )
    return any(signal in lower for signal in signals)


def _guess_city(text: str) -> str:
    for city in ("München", "Garching", "Freising", "Rosenheim", "Dachau", "Oberschleißheim"):
        if city.lower() in text.lower():
            return city
    return ""


def _guess_address(text: str) -> str:
    # Conservative address hint; the CSV seed remains the reliable source.
    match = __import__("re").search(
        r"([A-ZÄÖÜ][\wäöüÄÖÜß.\-/ ]{3,60}\s+\d+[a-zA-Z]?(?:[-–]\d+[a-zA-Z]?)?,?\s+\d{5}\s+[A-ZÄÖÜ][\wäöüÄÖÜß-]+)",
        text,
    )
    return clean_space(match.group(1)) if match else ""


def discover(config_path: str | Path, db_path: str | Path, fetch: bool = True) -> dict[str, int]:
    config = load_yaml(config_path)
    conn = connect(db_path)
    init_db(conn)

    stats = {"seeded": 0, "scraped": 0, "failed_sources": 0}
    seed_file = config.get("manual_residences_file")
    if seed_file:
        stats["seeded"] += import_seed_csv(conn, Path(seed_file))

    for item in config.get("manual_residences", []) or []:
        residence = Residence.from_mapping(item)
        if not residence.category:
            residence.category = classify_residence(
                residence.name, residence.notes, residence.url, residence.source_url
            )
        upsert_residence(conn, residence)
        stats["seeded"] += 1

    if fetch:
        for source in config.get("source_urls", []) or []:
            url = source["url"] if isinstance(source, dict) else str(source)
            try:
                html = fetch_page(url)
            except Exception:
                stats["failed_sources"] += 1
                continue
            for residence in extract_candidates_from_html(url, html):
                upsert_residence(conn, residence)
                stats["scraped"] += 1

    return stats
