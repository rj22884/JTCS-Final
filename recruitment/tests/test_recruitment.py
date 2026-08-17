import re
import zlib
from io import BytesIO

from recruitment.extensions import db
from recruitment.models import ApplicationStatusHistory, Job, JobApplication, RecruitmentAuditLog
from recruitment.tests.conftest import pdf_bytes, resume_file, sample_form
from recruitment.uploads import UploadError, validate_resume
from recruitment.validation import validate_application, validate_dob
from werkzeug.datastructures import FileStorage


def test_sso_token_roundtrip():
    from recruitment.sso import make_sso_token, read_sso_token

    token = make_sso_token("rajneesh@jtcsxpert.com", "Rajneesh Joshi", "Administrator", "secret")
    payload = read_sso_token(token, "secret")
    assert payload["email"] == "rajneesh@jtcsxpert.com"
    assert payload["role"] == "admin"


def test_cta_click_creates_audit(client):
    res = client.post(
        "/api/recruitment/events/cta-click",
        json={"visitor_id": "VABC123", "session_id": "SABC123", "page_url": "https://jtcsxpert.com/"},
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["event"] == "SALES_EXECUTIVE_CTA_CLICK"
    assert RecruitmentAuditLog.query.filter_by(event_type="SALES_EXECUTIVE_CTA_CLICK").count() == 1


def test_job_page_is_public(client):
    res = client.get("/careers/sales-executive")
    assert res.status_code == 302
    assert "careers-sales-executive.html" in (res.headers.get("Location") or "")
    assert RecruitmentAuditLog.query.filter_by(event_type="JOB_PAGE_VIEW").count() == 1


def test_apply_form_does_not_require_account(client):
    res = client.get("/careers/apply/sales-executive")
    assert res.status_code == 200
    assert b"Full Name" in res.data
    assert b"Personal Information" in res.data
    assert b"Educational Information" in res.data
    assert b"Experience" in res.data
    assert b"Upload Resume" in res.data
    assert b'id="recSteps"' not in res.data
    assert b">Continue</button>" not in res.data
    assert b"Preview Application" in res.data
    assert b"Download Preview PDF" in res.data
    assert b"Confirm &amp; Submit Application" in res.data
    assert b"Application Status" in res.data
    assert RecruitmentAuditLog.query.filter_by(event_type="APPLICATION_STARTED").count() == 1


def test_content_length_allows_resume_plus_form(app):
    assert app.config["MAX_CONTENT_LENGTH"] >= 8 * 1024 * 1024


def test_apply_json_missing_resume_returns_errors(client):
    res = client.post(
        "/careers/apply/sales-executive",
        data=sample_form(),
        content_type="multipart/form-data",
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
    )
    assert res.status_code == 400
    body = res.get_json()
    assert body["ok"] is False
    assert "resume" in body["errors"]
    assert JobApplication.query.count() == 0


def test_apply_json_success_returns_redirect(client):
    data = sample_form()
    data["resume"] = resume_file()
    res = client.post(
        "/careers/apply/sales-executive",
        data=data,
        content_type="multipart/form-data",
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert "confirmation" in body["redirect"]
    assert JobApplication.query.count() == 1


def test_dob_validation():
    assert validate_dob("2015-01-01")[0] is None
    assert validate_dob("2099-01-01")[0] is None
    dob, err = validate_dob("1995-06-15")
    assert dob is not None and err is None


def test_fresher_experience_allowed():
    clean, errors = validate_application(sample_form(sales_experience_years="0"), has_resume=True)
    assert "sales_experience_years" not in errors
    assert clean["sales_experience_years"] == 0


def test_declaration_required():
    _, errors = validate_application(sample_form(declaration=""), has_resume=True)
    assert "declaration" in errors


def test_official_title_name_allowed():
    clean, errors = validate_application(
        sample_form(name="DEPUTY DIRECTOR UCRRFP NAINITAL DIVISION HALDWANI"),
        has_resume=True,
    )
    assert "name" not in errors
    assert clean["name"].startswith("DEPUTY DIRECTOR")


def test_invalid_resume_rejected():
    fake = FileStorage(stream=BytesIO(b"MZ executable"), filename="virus.exe", content_type="application/octet-stream")
    try:
        validate_resume(fake)
        assert False, "should reject"
    except UploadError:
        pass


def test_large_resume_rejected():
    fake = FileStorage(stream=BytesIO(b"%PDF" + b"x" * (6 * 1024 * 1024)), filename="big.pdf", content_type="application/pdf")
    try:
        validate_resume(fake, max_mb=5)
        assert False, "should reject"
    except UploadError:
        pass


def test_submit_application_and_number(client):
    data = sample_form()
    data["resume"] = resume_file()
    res = client.post("/careers/apply/sales-executive", data=data, content_type="multipart/form-data")
    assert res.status_code == 302
    app_row = JobApplication.query.first()
    assert app_row is not None
    assert app_row.application_number.startswith("JTCS-SE-")
    assert app_row.visitor_id == "VTEST001"
    db.session.refresh(app_row)
    location = res.headers["Location"]
    assert "/careers/confirmation/" in location
    assert app_row.application_number in location
    home = client.get(location)
    assert home.status_code == 200
    assert app_row.application_number.encode() in home.data
    assert b"Your application is submitted successfully" in home.data
    assert b"Application Number:" in home.data
    assert b"Save for future reference." in home.data
    assert b"Check Application Status" in home.data
    assert b"Download Application PDF" in home.data
    assert b"9876543210" not in home.data
    assert b"ravi.sharma@example.com" not in home.data
    assert app_row.application_pdf_stored_name
    assert b"Suresh Sharma" not in home.data


def test_duplicate_application_blocked(client):
    data = sample_form()
    data["resume"] = (BytesIO(pdf_bytes()), "resume.pdf")
    first = client.post("/careers/apply/sales-executive", data=data, content_type="multipart/form-data")
    assert first.status_code == 302
    data["resume"] = (BytesIO(pdf_bytes()), "resume.pdf")
    second = client.post("/careers/apply/sales-executive", data=data, content_type="multipart/form-data")
    assert second.status_code == 409
    assert b"already exists" in second.data
    assert b"This mobile number is already used" in second.data
    assert b"This email address is already used" in second.data
    assert JobApplication.query.count() == 1


def test_duplicate_email_or_mobile_blocked(client):
    first = sample_form()
    first["resume"] = resume_file()
    assert client.post("/careers/apply/sales-executive", data=first, content_type="multipart/form-data").status_code == 302

    same_email = sample_form(mobile="9123456780", name="Amit Verma")
    same_email["resume"] = resume_file()
    email_dup = client.post("/careers/apply/sales-executive", data=same_email, content_type="multipart/form-data")
    assert email_dup.status_code == 409
    assert b"This email address is already used" in email_dup.data

    same_mobile = sample_form(email="amit.verma@example.com", name="Amit Verma")
    same_mobile["resume"] = resume_file()
    mobile_dup = client.post("/careers/apply/sales-executive", data=same_mobile, content_type="multipart/form-data")
    assert mobile_dup.status_code == 409
    assert b"This mobile number is already used" in mobile_dup.data
    assert JobApplication.query.count() == 1


def test_apply_check_reports_duplicate_fields(client):
    data = sample_form()
    data["resume"] = resume_file()
    client.post("/careers/apply/sales-executive", data=data, content_type="multipart/form-data")
    res = client.post(
        "/api/recruitment/apply-check",
        json={"slug": "sales-executive", "email": "ravi.sharma@example.com", "mobile": "9000000000"},
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["duplicate"] is True
    assert "email" in body["errors"]
    assert "mobile" not in body["errors"]


def test_admin_requires_login(client):
    res = client.get("/recruitment/admin/")
    assert res.status_code in (302, 401)
    assert "/recruitment/admin/login" in (res.headers.get("Location") or "")


def test_admin_dashboard_and_status_change(admin_client):
    data = sample_form()
    data["resume"] = resume_file()
    admin_client.post("/careers/apply/sales-executive", data=data, content_type="multipart/form-data")
    application = JobApplication.query.first()
    dash = admin_client.get("/recruitment/admin/")
    assert dash.status_code == 200
    assert b"Total Applications" in dash.data
    assert b"New Applications" in dash.data
    grid = admin_client.get("/recruitment/admin/applications")
    assert application.application_number.encode() in grid.data
    detail = admin_client.get(f"/recruitment/admin/applications/{application.application_id}")
    assert detail.status_code == 200
    assert RecruitmentAuditLog.query.filter_by(event_type="APPLICATION_VIEWED").count() >= 1
    admin_client.post(
        f"/recruitment/admin/applications/{application.application_id}/status",
        data={"status": "Shortlisted", "reason": "Strong communication"},
    )
    db.session.refresh(application)
    assert application.application_status == "Shortlisted"
    history = ApplicationStatusHistory.query.filter_by(application_id=application.application_id).all()
    assert any(h.new_status == "Shortlisted" and h.old_status == "New" for h in history)
    assert RecruitmentAuditLog.query.filter_by(event_type="APPLICATION_SHORTLISTED").count() == 1


def test_resume_download_authorized_only(app):
    submitter = app.test_client()
    data = sample_form()
    data["resume"] = resume_file()
    submitter.post("/careers/apply/sales-executive", data=data, content_type="multipart/form-data")
    application = JobApplication.query.first()
    denied = app.test_client().get(f"/recruitment/admin/applications/{application.application_id}/resume")
    assert denied.status_code in (302, 401, 403)
    admin = app.test_client()
    admin.post(
        "/recruitment/admin/login",
        data={"email": "admin@jtcsxpert.com", "password": "TestAdmin!234"},
    )
    allowed = admin.get(f"/recruitment/admin/applications/{application.application_id}/resume")
    assert allowed.status_code == 200
    assert allowed.data.startswith(b"%PDF")


def test_audit_export(admin_client):
    admin_client.post("/api/recruitment/events/cta-click", json={"visitor_id": "V1", "session_id": "S1"})
    csv_res = admin_client.get("/recruitment/admin/audit/export/csv")
    assert csv_res.status_code == 200
    assert b"Event" in csv_res.data
    xlsx = admin_client.get("/recruitment/admin/audit/export/xlsx")
    assert xlsx.status_code == 200
    pdf = admin_client.get("/recruitment/admin/audit/export/pdf")
    assert pdf.status_code == 200


def test_analytics_page(admin_client):
    res = admin_client.get("/recruitment/admin/analytics")
    assert res.status_code == 200
    assert b"Daily CTA clicks" in res.data


def test_internal_note_and_interview(admin_client):
    from recruitment.models import ApplicationNote

    data = sample_form()
    data["resume"] = resume_file()
    admin_client.post("/careers/apply/sales-executive", data=data, content_type="multipart/form-data")
    application = JobApplication.query.first()
    note = admin_client.post(
        f"/recruitment/admin/applications/{application.application_id}/notes",
        data={"note": "Call candidate tomorrow"},
        follow_redirects=True,
    )
    assert note.status_code == 200
    assert ApplicationNote.query.count() == 1
    assert b"Call candidate tomorrow" in note.data
    interview = admin_client.post(
        f"/recruitment/admin/applications/{application.application_id}/interview",
        data={
            "interview_date": "2026-08-20",
            "interview_time": "11:00",
            "interview_mode": "Office",
            "interview_location": "JTCS Xpert, Haldwani",
            "interview_interviewer": "HR",
            "interview_result": "Pending",
        },
        follow_redirects=True,
    )
    assert interview.status_code == 200
    assert b"Office" in interview.data
    db.session.refresh(application)
    assert application.interview_location == "JTCS Xpert, Haldwani"
    from recruitment.candidate_status import public_status_payload

    payload = public_status_payload(application)
    assert payload["interview"]["location"] == "JTCS Xpert, Haldwani"
    assert payload["interview"]["mode"] == "Office"
    assert "interviewer" not in payload["interview"]
    assert "notes" not in payload["interview"]


def test_applications_export_respects_filter(admin_client):
    data = sample_form()
    data["resume"] = resume_file()
    admin_client.post("/careers/apply/sales-executive", data=data, content_type="multipart/form-data")
    res = admin_client.get("/recruitment/admin/applications/export/csv?status=New")
    assert res.status_code == 200
    assert b"JTCS-SE-" in res.data
    assert b"Date of Birth" not in res.data


def test_job_window_open_until_ist_deadline(app):
    from datetime import date, datetime
    from zoneinfo import ZoneInfo

    from recruitment.job_window import is_job_application_open
    from recruitment.models import Job

    job = Job.query.filter_by(slug="sales-executive").first()
    job.closing_date = date(2026, 10, 31)
    job.closing_time = "23:59:59"
    job.timezone = "Asia/Kolkata"
    ist = ZoneInfo("Asia/Kolkata")
    assert is_job_application_open(job, datetime(2026, 10, 31, 23, 59, 59, tzinfo=ist)) is True
    assert is_job_application_open(job, datetime(2026, 11, 1, 0, 0, 0, tzinfo=ist)) is False


def test_backend_rejects_application_after_deadline(client):
    from datetime import date

    from recruitment.extensions import db
    from recruitment.models import Job, JobApplication, RecruitmentAuditLog

    job = Job.query.filter_by(slug="sales-executive").first()
    job.closing_date = date(2020, 1, 1)
    db.session.commit()
    data = sample_form()
    data["resume"] = resume_file()
    res = client.post("/careers/apply/sales-executive", data=data, content_type="multipart/form-data")
    assert res.status_code == 403
    assert b"Applications for the Sales Executive position are now closed." in res.data
    assert JobApplication.query.count() == 0
    assert RecruitmentAuditLog.query.filter_by(event_type="APPLICATION_ATTEMPTED_AFTER_DEADLINE").count() >= 1


def test_apply_page_shows_closed_and_hides_submit(client):
    from datetime import date

    from recruitment.extensions import db
    from recruitment.models import Job

    job = Job.query.filter_by(slug="sales-executive").first()
    job.closing_date = date(2020, 1, 1)
    db.session.commit()
    res = client.get("/careers/apply/sales-executive")
    assert res.status_code == 200
    assert b"Applications Closed" in res.data
    assert b"Submit Application" not in res.data


def test_existing_application_remains_after_deadline(admin_client):
    from datetime import date

    from recruitment.extensions import db
    from recruitment.models import Job, JobApplication

    data = sample_form()
    data["resume"] = resume_file()
    submit = admin_client.post("/careers/apply/sales-executive", data=data, content_type="multipart/form-data")
    assert submit.status_code == 302
    application = JobApplication.query.first()
    assert application is not None
    number = application.application_number

    job = Job.query.filter_by(slug="sales-executive").first()
    job.closing_date = date(2020, 1, 1)
    db.session.commit()

    listing = admin_client.get("/recruitment/admin/applications")
    assert listing.status_code == 200
    assert number.encode() in listing.data

    later = sample_form(email="late.applicant@example.com", mobile="9123456789")
    later["resume"] = resume_file()
    blocked = admin_client.post("/careers/apply/sales-executive", data=later, content_type="multipart/form-data")
    assert blocked.status_code == 403
    assert JobApplication.query.count() == 1


def test_job_status_api_uses_server_deadline(client):
    res = client.get("/api/recruitment/jobs/sales-executive/status")
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["timezone"] == "Asia/Kolkata"
    assert "last_date_label" in body
    assert body["open"] is True


def test_empty_applications_state(admin_client):
    res = admin_client.get("/recruitment/admin/applications")
    assert res.status_code == 200
    assert b"No applications received yet." in res.data


def _submit(client, **overrides):
    data = sample_form(**overrides)
    data["resume"] = resume_file()
    res = client.post("/careers/apply/sales-executive", data=data, content_type="multipart/form-data")
    assert res.status_code == 302
    return JobApplication.query.order_by(JobApplication.application_id.desc()).first()


def test_status_page_is_public(client):
    res = client.get("/careers/application-status")
    assert res.status_code == 200
    assert b"Check Your Application Status" in res.data
    assert b"Application Number" in res.data


def test_status_verify_mobile_and_email(client):
    application = _submit(client)
    number = application.application_number
    mobile_ok = client.post(
        "/careers/application-status",
        data={"application_number": number, "mobile": "9876543210"},
    )
    assert mobile_ok.status_code == 200
    assert number.encode() in mobile_ok.data
    assert b"Application Received" in mobile_ok.data
    assert b"Suresh Sharma" not in mobile_ok.data
    assert b"1998-05-12" not in mobile_ok.data
    assert b"Nainital Road" not in mobile_ok.data
    assert b"Call candidate" not in mobile_ok.data

    email_ok = client.post(
        "/careers/application-status",
        data={"application_number": number, "email": "ravi.sharma@example.com"},
    )
    assert email_ok.status_code == 200
    assert b"Application Received" in email_ok.data


def test_status_rejects_number_only_and_wrong_contact(client):
    application = _submit(client)
    number = application.application_number
    generic = b"We could not verify the application details"
    number_only = client.post("/careers/application-status", data={"application_number": number})
    assert number_only.status_code == 200
    assert generic in number_only.data
    assert b"Application Received" not in number_only.data

    wrong_mobile = client.post(
        "/careers/application-status",
        data={"application_number": number, "mobile": "9000000000"},
    )
    assert generic in wrong_mobile.data
    assert b"mobile number is wrong" not in wrong_mobile.data.lower()

    wrong_email = client.post(
        "/careers/application-status",
        data={"application_number": number, "email": "other@example.com"},
    )
    assert generic in wrong_email.data

    missing = client.post(
        "/careers/application-status",
        data={"application_number": "JTCS-SE-2099-99999", "mobile": "9876543210"},
    )
    assert generic in missing.data


def test_status_api_hides_private_fields(client):
    application = _submit(client)
    denied = client.get("/api/careers/application-status")
    assert denied.status_code == 404
    body = denied.get_json()
    assert body["ok"] is False
    assert "could not verify" in body["error"]

    ok = client.get(
        "/api/recruitment/application-status",
        query_string={
            "application_number": application.application_number,
            "mobile": "9876543210",
        },
    )
    assert ok.status_code == 200
    payload = ok.get_json()
    assert payload["ok"] is True
    assert payload["application_number"] == application.application_number
    assert payload["current_status"] == "Application Received"
    assert "admin_status" not in payload
    assert "father_name" not in payload
    assert "dob" not in payload
    assert "address" not in payload
    assert "resume_stored_name" not in payload
    assert "notes" not in payload
    assert "changed_by" not in str(payload)


def test_admin_status_change_appears_on_candidate_page(admin_client):
    application = _submit(admin_client)
    admin_client.post(
        f"/recruitment/admin/applications/{application.application_id}/status",
        data={"status": "Shortlisted", "reason": "Internal shortlist note"},
    )
    shown = admin_client.post(
        "/careers/application-status",
        data={"application_number": application.application_number, "email": "ravi.sharma@example.com"},
    )
    assert b"Shortlisted" in shown.data
    assert b"Congratulations" in shown.data
    assert b"Internal shortlist note" not in shown.data


def test_status_still_works_after_job_closes(client):
    from datetime import date

    application = _submit(client)
    job = Job.query.filter_by(slug="sales-executive").first()
    job.closing_date = date(2020, 1, 1)
    db.session.commit()
    shown = client.post(
        "/careers/application-status",
        data={"application_number": application.application_number, "mobile": "9876543210"},
    )
    assert shown.status_code == 200
    assert application.application_number.encode() in shown.data
    assert b"Application Received" in shown.data


def _pdf_text(data: bytes) -> str:
    chunks = [data.decode("latin-1", "ignore")]
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        raw = match.group(1)
        try:
            raw = zlib.decompress(raw)
        except Exception:
            pass
        chunks.append(raw.decode("latin-1", "ignore"))
    return "\n".join(chunks)


def test_apply_page_shows_preview_pdf_before_submit(client):
    res = client.get("/careers/apply/sales-executive")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert 'id="recResumeHold"' in html
    assert "Preview Application" in html
    assert "Download Preview PDF" in html
    assert "Confirm &amp; Submit Application" in html
    assert html.index("Preview Application") < html.index("Confirm &amp; Submit Application")
    assert html.index("Download Preview PDF") < html.index("Confirm &amp; Submit Application")


def test_preview_pdf_does_not_create_application(client):
    data = sample_form()
    data["resume"] = resume_file()
    res = client.post("/careers/apply/sales-executive/preview-pdf", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    assert res.data.startswith(b"%PDF")
    text = _pdf_text(res.data)
    assert "PREVIEW - NOT SUBMITTED" in text or "PREVIEW" in text
    assert "JTCS Application Preview" in text
    assert "JTCS-SE-2026-" not in text
    assert "PREVIEW" in (res.headers.get("Content-Disposition") or "")
    assert JobApplication.query.count() == 0


def test_final_pdf_contains_application_number(client):
    application = _submit(client)
    db.session.refresh(application)
    from recruitment.application_pdf import resolve_application_pdf

    path = resolve_application_pdf(application)
    assert path is not None
    content = path.read_bytes()
    text = _pdf_text(content)
    assert application.application_number in text
    assert "APPLICATION SUBMITTED" in text
    assert "NOT SUBMITTED" not in text
    assert application.application_pdf_original_name == f"{application.application_number}-Application.pdf"


def test_candidate_pdf_requires_verification(client):
    application = _submit(client)
    stolen = client.post(
        "/careers/application-status/pdf",
        data={"application_number": application.application_number, "mobile": "9000000000"},
        follow_redirects=True,
    )
    assert stolen.status_code == 200
    assert b"%PDF" not in stolen.data
    assert b"could not verify" in stolen.data

    allowed = client.post(
        "/careers/application-status/pdf",
        data={"application_number": application.application_number, "mobile": "9876543210"},
    )
    assert allowed.status_code == 200
    assert allowed.data.startswith(b"%PDF")
    assert application.application_number.encode() in allowed.data


def test_confirmation_pdf_requires_token(client):
    application = _submit(client)
    denied = client.get(f"/careers/confirmation/{application.application_number}/pdf")
    assert denied.status_code == 404
    confirm = client.get(f"/careers/confirmation/{application.application_number}")
    assert confirm.status_code == 200
    assert b"t=" in confirm.data


def test_admin_pdf_download_authorized_only(app):
    submitter = app.test_client()
    application = _submit(submitter)
    denied = app.test_client().get(f"/recruitment/admin/applications/{application.application_id}/pdf")
    assert denied.status_code in (302, 401, 403)
    admin = app.test_client()
    admin.post("/recruitment/admin/login", data={"email": "admin@jtcsxpert.com", "password": "TestAdmin!234"})
    allowed = admin.get(f"/recruitment/admin/applications/{application.application_id}/pdf")
    assert allowed.status_code == 200
    assert allowed.data.startswith(b"%PDF")


def test_public_status_mapping():
    from recruitment.candidate_status import STATUS_MAP, public_status

    assert public_status("New")["label"] == "Application Received"
    assert public_status("Under Review")["label"] == "Application Under Review"
    assert public_status("Interviewed")["label"] == "Interview Completed"
    assert public_status("Rejected")["label"] == "Application Not Selected"
    assert public_status("On Hold")["label"] == "Application On Hold"
    assert set(STATUS_MAP) >= {
        "New",
        "Under Review",
        "Shortlisted",
        "Interview Scheduled",
        "Interviewed",
        "Selected",
        "Rejected",
        "On Hold",
    }
