"""Uttarakhand e-Stamp article master — unique SHCIL article numbers, English + Hindi."""

from __future__ import annotations

# code matches SHCIL dropdown brackets, e.g. Transfer [62], License [38(A)]
ARTICLES: tuple[dict[str, str], ...] = (
    {"code": "1", "label": "Article 1 (Acknowledgment of a debt)", "hindi": "ऋण की अभिस्वीकृति", "shcil": "Acknowledgment of a debt"},
    {"code": "2", "label": "Article 2 (Administration Bond)", "hindi": "प्रशासन बॉण्ड", "shcil": "Administration Bond"},
    {"code": "3", "label": "Article 3 (Adoption Deed)", "hindi": "दत्तक विलेख", "shcil": "Adoption - Deed"},
    {"code": "4", "label": "Article 4 (Affidavit)", "hindi": "शपथ पत्र", "shcil": "Affidavit"},
    {"code": "5", "label": "Article 5 (Agreement / Memorandum of Agreement)", "hindi": "करार / करार ज्ञापन", "shcil": "Agreement or Memorandum of an agreement"},
    {"code": "6", "label": "Article 6 (Agreement relating to deposit of title deeds)", "hindi": "स्वामित्व विलेख जमा संबंधी करार", "shcil": "Agreement relating to Deposit of Title-Deeds"},
    {"code": "10", "label": "Article 10 (Articles of Association of a Company)", "hindi": "कंपनी के संगम अनुच्छेद", "shcil": "Articles of Association of a Company"},
    {"code": "12", "label": "Article 12 (Award)", "hindi": "अधिनिर्णय", "shcil": "Award"},
    {"code": "15", "label": "Article 15 (Bond)", "hindi": "बॉण्ड", "shcil": "Bond"},
    {"code": "17", "label": "Article 17 (Cancellation)", "hindi": "निरस्तीकरण", "shcil": "Cancellation"},
    {"code": "17(A)", "label": "Article 17(A) (Certificate of enrolment of Advocates)", "hindi": "अधिवक्ता नामांकन प्रमाण पत्र", "shcil": "Certificate of enrolment of Advocates"},
    {"code": "17(B)", "label": "Article 17(B) (Certificate of Practice as Notary)", "hindi": "नोटरी अभ्यास प्रमाण पत्र", "shcil": "Certificate of Practice as Notary"},
    {"code": "18", "label": "Article 18 (Certificate of Sale)", "hindi": "विक्रय प्रमाण पत्र", "shcil": "Certificate of Sale"},
    {"code": "19", "label": "Article 19 (Certificate or other Document)", "hindi": "प्रमाण पत्र / अन्य दस्तावेज", "shcil": "Certificate or other Document"},
    {"code": "20", "label": "Article 20 (Charter Party)", "hindi": "चार्टर पार्टी", "shcil": "Charter Party"},
    {"code": "22", "label": "Article 22 (Composition Deed)", "hindi": "समझौता विलेख", "shcil": "Composition - Deed"},
    {"code": "23", "label": "Article 23 (Conveyance)", "hindi": "हस्तांतरण विलेख", "shcil": "Conveyance"},
    {"code": "24", "label": "Article 24 (Copy or Extract)", "hindi": "प्रतिलिपि / उद्धरण", "shcil": "Copy or Extract"},
    {"code": "33", "label": "Article 33 (Gift)", "hindi": "दान", "shcil": "Gift"},
    {"code": "35", "label": "Article 35 (Lease)", "hindi": "पट्टा", "shcil": "Lease"},
    {"code": "36", "label": "Article 36 (Letter of Allotment of Shares)", "hindi": "अंश आवंटन पत्र", "shcil": "Letter of Allotment of Shares"},
    {"code": "37", "label": "Article 37 (Letter of Credit)", "hindi": "साख पत्र", "shcil": "Letter of Credit"},
    {"code": "38", "label": "Article 38 (Letter of License)", "hindi": "लाइसेंस पत्र", "shcil": "Letter of License"},
    {"code": "38(A)", "label": "Article 38(A) (License)", "hindi": "लाइसेंस", "shcil": "License"},
    {"code": "39", "label": "Article 39 (Memorandum of Association of a Company)", "hindi": "कंपनी का संगम ज्ञापन", "shcil": "Memorandum of Association of a Company"},
    {"code": "40", "label": "Article 40 (Mortgage Deed)", "hindi": "बंधक विलेख", "shcil": "Mortgage - Deed"},
    {"code": "41", "label": "Article 41 (Mortgage of a Crop)", "hindi": "फसल बंधक", "shcil": "Mortgage of a Crop"},
    {"code": "42", "label": "Article 42 (Notarial Act)", "hindi": "नोटरी कार्य", "shcil": "Notarial Act"},
    {"code": "43", "label": "Article 43 (Note or Memorandum)", "hindi": "नोट / ज्ञापन", "shcil": "Note or Memorandum"},
    {"code": "44", "label": "Article 44 (Note of Protest)", "hindi": "विरोध नोट", "shcil": "Note of Protest"},
    {"code": "45", "label": "Article 45 (Partition)", "hindi": "विभाजन", "shcil": "Partition"},
    {"code": "46", "label": "Article 46 (Partnership)", "hindi": "साझेदारी", "shcil": "Partnership"},
    {"code": "46(A)", "label": "Article 46(A) (Partnership)", "hindi": "साझेदारी", "shcil": "Partnership"},
    {"code": "47", "label": "Article 47 (Policy of Insurance)", "hindi": "बीमा पॉलिसी", "shcil": "Policy of Insurance"},
    {"code": "48", "label": "Article 48 (Power of Attorney)", "hindi": "मुख्तारनामा", "shcil": "Power of Attorney"},
    {"code": "49", "label": "Article 49 (Promissory Note)", "hindi": "वचन पत्र", "shcil": "Promissory Note"},
    {"code": "50", "label": "Article 50 (Protest of Bill or note)", "hindi": "बिल / नोट का विरोध", "shcil": "Protest of Bill or note"},
    {"code": "51", "label": "Article 51 (Protest by the Master of a Ship)", "hindi": "पोत मास्टर द्वारा विरोध", "shcil": "Protest by the Master of a Ship"},
    {"code": "52", "label": "Article 52 (Proxy)", "hindi": "प्रतिनिधि", "shcil": "Proxy"},
    {"code": "54", "label": "Article 54 (Reconveyance of mortgaged property)", "hindi": "बंधक संपत्ति का पुनर्हस्तांतरण", "shcil": "Re-Conveyance of Mortgaged property"},
    {"code": "55", "label": "Article 55 (Release)", "hindi": "मोचन", "shcil": "Release"},
    {"code": "57", "label": "Article 57 (Security Bond / Mortgage Deed)", "hindi": "प्रतिभूति बॉण्ड / बंधक विलेख", "shcil": "Security Bond"},
    {"code": "58(A)", "label": "Article 58(A) (Settlement)", "hindi": "समझौता", "shcil": "Settlement"},
    {"code": "58(B)", "label": "Article 58(B) (Revocation of Settlement)", "hindi": "समझौता निरस्तीकरण", "shcil": "Revocation of Settlement"},
    {"code": "62", "label": "Article 62 (Transfer)", "hindi": "हस्तांतरण", "shcil": "Transfer"},
    {"code": "64", "label": "Article 64 (Trust)", "hindi": "न्यास", "shcil": "Trust"},
    {"code": "other", "label": "Other article (mention in review)", "hindi": "अन्य अनुच्छेद", "shcil": ""},
)


def _dedupe(items: tuple[dict[str, str], ...]) -> tuple[dict[str, str], ...]:
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for item in items:
        code = (item.get("code") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        unique.append(item)
    return tuple(unique)


ARTICLES = _dedupe(ARTICLES)


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
            "shcil": item.get("shcil") or "",
        }
        for item in ARTICLES
    ]


def article_by_code(code: str) -> dict | None:
    key = (code or "").strip()
    if not key:
        return None
    for item in ARTICLES:
        if item["code"] == key or item["code"].lower() == key.lower():
            return item
    return None


def article_shcil_hint(code: str) -> str:
    item = article_by_code(code)
    if not item:
        return ""
    return (item.get("shcil") or "").strip()
