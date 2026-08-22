"""Uttarakhand e-Stamp article list for the public website."""

from __future__ import annotations

ARTICLES: tuple[dict[str, str], ...] = (
    {"code": "4", "label": "Article 4 (Affidavit)", "hindi": "शपथ पत्र"},
    {"code": "5", "label": "Article 5 (Agreement / Memorandum of Agreement)", "hindi": "करार / करार ज्ञापन"},
    {"code": "6", "label": "Article 6 (Agreement relating to deposit of title deeds)", "hindi": "स्वामित्व विलेख जमा संबंधी करार"},
    {"code": "12", "label": "Article 12 (Award)", "hindi": "अधिनिर्णय"},
    {"code": "15", "label": "Article 15 (Bond)", "hindi": "बॉण्ड"},
    {"code": "17", "label": "Article 17 (Cancellation)", "hindi": "निरस्तीकरण"},
    {"code": "23", "label": "Article 23 (Conveyance)", "hindi": "हस्तांतरण विलेख"},
    {"code": "24", "label": "Article 24 (Copy or Extract)", "hindi": "प्रतिलिपि / उद्धरण"},
    {"code": "35", "label": "Article 35 (Lease)", "hindi": "पट्टा"},
    {"code": "40", "label": "Article 40 (Mortgage Deed)", "hindi": "बंधक विलेख"},
    {"code": "42", "label": "Article 42 (Notarial Act)", "hindi": "नोटरी कार्य"},
    {"code": "46", "label": "Article 46 (Partnership)", "hindi": "साझेदारी"},
    {"code": "48", "label": "Article 48 (Power of Attorney)", "hindi": "मुख्तारनामा"},
    {"code": "54", "label": "Article 54 (Reconveyance of mortgaged property)", "hindi": "बंधक संपत्ति का पुनर्हस्तांतरण"},
    {"code": "55", "label": "Article 55 (Release)", "hindi": "मोचन"},
    {"code": "57", "label": "Article 57 (Security Bond / Mortgage Deed)", "hindi": "प्रतिभूति बॉण्ड / बंधक विलेख"},
    {"code": "62", "label": "Article 62 (Transfer)", "hindi": "हस्तांतरण"},
    {"code": "64", "label": "Article 64 (Trust)", "hindi": "न्यास"},
    {"code": "other", "label": "Other article (mention in review)", "hindi": "अन्य अनुच्छेद"},
)


def article_display(item: dict) -> str:
    hindi = (item.get("hindi") or "").strip()
    label = (item.get("label") or "").strip()
    return f"{label} ({hindi})" if hindi else label


def public_articles() -> list[dict]:
    return [
        {
            "code": item["code"],
            "label": article_display(item),
            "hindi": item["hindi"],
        }
        for item in ARTICLES
    ]


def article_by_code(code: str) -> dict | None:
    key = (code or "").strip().lower()
    for item in ARTICLES:
        if item["code"].lower() == key:
            return item
    return None
