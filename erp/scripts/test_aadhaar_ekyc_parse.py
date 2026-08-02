"""Quick offline eKYC XML parse + start route smoke test."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app
from app.services.aadhaar_offline_ekyc_service import AadhaarOfflineEkycService, _parse_offline_xml

SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<OfflinePaperlessKyc referenceId="123420240101120000">
  <UidData>
    <Poi name="RAMESH KUMAR" dob="15-08-1990" gender="M"/>
    <Poa careof="S/O SURESH KUMAR" house="12A" street="MG Road" lm="Near Temple" loc="Ward 3"
         vtc="Haldwani" subdist="Haldwani" dist="Nainital" state="Uttarakhand" country="India" pc="263139"/>
    <Pht>iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==</Pht>
  </UidData>
</OfflinePaperlessKyc>
"""


def main() -> None:
    parsed = _parse_offline_xml(SAMPLE)
    print("parsed", {k: v for k, v in parsed.items() if k != "photo_base64"})
    print("portal", AadhaarOfflineEkycService.portal_url())

    app = create_app()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["role"] = "Administrator"
        sess["user_name"] = "Admin"
    page = client.get("/masters/customer")
    html = page.get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([^"]+)"', html)
    csrf = m.group(1) if m else ""
    resp = client.post(
        "/masters/customer/api/aadhaar-ekyc/start",
        json={},
        headers={"X-CSRFToken": csrf, "Accept": "application/json"},
    )
    print("start", resp.status_code, resp.get_json())


if __name__ == "__main__":
    main()
