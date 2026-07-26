from __future__ import annotations


def _two_digit(n: int) -> str:
    ones = [
        "Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
        "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
        "Seventeen", "Eighteen", "Nineteen",
    ]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
    if n < 20:
        return ones[n]
    if n < 100:
        return (tens[n // 10] + (" " + ones[n % 10] if n % 10 else "")).strip()
    if n < 1000:
        return (
            ones[n // 100] + " Hundred"
            + (" " + _two_digit(n % 100) if n % 100 else "")
        ).strip()
    return str(n)


def amount_in_words_rupees(amount) -> str:
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return ""
    if value < 0:
        return ""
    rupees = int(value)
    paise = int(round((value - rupees) * 100))
    if rupees == 0 and paise == 0:
        return "Zero Rupees Only"
    parts = []
    crore = rupees // 10000000
    lakh = (rupees % 10000000) // 100000
    thousand = (rupees % 100000) // 1000
    hundred_rest = rupees % 1000
    if crore:
        parts.append(_two_digit(crore) + " Crore")
    if lakh:
        parts.append(_two_digit(lakh) + " Lakh")
    if thousand:
        parts.append(_two_digit(thousand) + " Thousand")
    if hundred_rest:
        parts.append(_two_digit(hundred_rest))
    words = " ".join(parts).strip() or "Zero"
    result = f"{words} Rupee{'s' if rupees != 1 else ''}"
    if paise:
        result += f" and {_two_digit(paise)} Paise"
    return result + " Only"
