from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Residence:
    name: str
    category: str
    city: str = ""
    address: str = ""
    email: str = ""
    phone: str = ""
    url: str = ""
    source_url: str = ""
    notes: str = ""
    eligibility: str = ""
    status: str = "active"
    priority: int = 3

    @classmethod
    def from_mapping(cls, data: dict[str, object]) -> "Residence":
        return cls(
            name=str(data.get("name") or "").strip(),
            category=str(data.get("category") or "").strip(),
            city=str(data.get("city") or "").strip(),
            address=str(data.get("address") or "").strip(),
            email=str(data.get("email") or "").strip(),
            phone=str(data.get("phone") or "").strip(),
            url=str(data.get("url") or "").strip(),
            source_url=str(data.get("source_url") or "").strip(),
            notes=str(data.get("notes") or "").strip(),
            eligibility=str(data.get("eligibility") or "").strip(),
            status=str(data.get("status") or "active").strip(),
            priority=int(data.get("priority") or 3),
        )

