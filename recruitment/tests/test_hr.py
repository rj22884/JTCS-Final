from recruitment.extensions import db
from recruitment.models import Employee, JobApplication, OfferLetter
from recruitment.tests.conftest import resume_file, sample_form


def _apply(client):
    data = sample_form()
    data["resume"] = resume_file()
    res = client.post("/careers/apply/sales-executive", data=data, content_type="multipart/form-data")
    assert res.status_code == 302
    return JobApplication.query.first()


def test_interview_updates_existing_status(admin_client):
    application = _apply(admin_client)
    admin_client.post(
        f"/recruitment/admin/applications/{application.application_id}/interview",
        data={
            "interview_date": "2026-08-20",
            "interview_time": "11:00",
            "interview_mode": "Video Call",
            "interview_location": "https://meet.example/jtcs",
            "interview_interviewer": "HR Manager",
            "interview_notes": "Internal only",
            "interview_result": "Pending",
        },
        follow_redirects=True,
    )
    db.session.refresh(application)
    assert application.application_status == "Interview Scheduled"
    admin_client.post(
        f"/recruitment/admin/applications/{application.application_id}/interview",
        data={
            "interview_date": "2026-08-20",
            "interview_time": "11:00",
            "interview_mode": "Video Call",
            "interview_location": "https://meet.example/jtcs",
            "interview_interviewer": "HR Manager",
            "interview_notes": "Internal only",
            "interview_result": "Recommended",
        },
        follow_redirects=True,
    )
    db.session.refresh(application)
    assert application.application_status == "Interviewed"
    public = admin_client.post(
        "/careers/application-status",
        data={"application_number": application.application_number, "mobile": "9876543210"},
    )
    assert b"Interview Completed" in public.data
    assert b"Internal only" not in public.data
    assert b"HR Manager" not in public.data
    assert b"Recommended" not in public.data


def test_convert_requires_selected(admin_client):
    application = _apply(admin_client)
    res = admin_client.post(f"/recruitment/admin/applications/{application.application_id}/convert", follow_redirects=True)
    assert res.status_code == 200
    assert b"Only a Selected application" in res.data
    assert Employee.query.count() == 0


def test_selected_to_appointment_flow(admin_client):
    application = _apply(admin_client)
    admin_client.post(
        f"/recruitment/admin/applications/{application.application_id}/status",
        data={"status": "Selected", "reason": "Recommended"},
        follow_redirects=True,
    )
    detail = admin_client.get(f"/recruitment/admin/applications/{application.application_id}")
    assert b"Convert to Employee" in detail.data

    converted = admin_client.post(
        f"/recruitment/admin/applications/{application.application_id}/convert",
        follow_redirects=True,
    )
    assert converted.status_code == 200
    employee = Employee.query.first()
    assert employee is not None
    assert employee.employee_code.startswith("EMP-")
    assert employee.application_id == application.application_id
    assert employee.application_number == application.application_number
    assert employee.name == "Ravi Sharma"
    assert employee.email == "ravi.sharma@example.com"
    assert employee.highest_qualification == "Graduate"

    admin_client.post(
        f"/recruitment/admin/employees/{employee.employee_id}",
        data={
            "joining_date": "2026-09-01",
            "salary_ctc": "30000 monthly",
            "probation_period": "6 months",
            "employment_status": "Selected",
            "employment_type": "Full-time",
            "work_location": "Haldwani, Uttarakhand",
        },
        follow_redirects=True,
    )
    offer = admin_client.post(f"/recruitment/admin/employees/{employee.employee_id}/offer", follow_redirects=True)
    assert offer.status_code == 200
    db.session.refresh(application)
    assert application.application_status == "Offer Issued"
    assert OfferLetter.query.count() == 1
    pdf = admin_client.get(f"/recruitment/admin/employees/{employee.employee_id}/offer.pdf")
    assert pdf.status_code == 200
    assert pdf.data.startswith(b"%PDF")

    admin_client.post(
        f"/recruitment/admin/employees/{employee.employee_id}/offer-status",
        data={"offer_status": "Accepted", "acceptance_method": "Email"},
        follow_redirects=True,
    )
    db.session.refresh(application)
    assert application.application_status == "Offer Accepted"

    apt = admin_client.post(f"/recruitment/admin/employees/{employee.employee_id}/appointment", follow_redirects=True)
    assert apt.status_code == 200
    db.session.refresh(application)
    assert application.application_status == "Appointment Issued"
    letter = admin_client.get(f"/recruitment/admin/employees/{employee.employee_id}/appointment.pdf")
    assert letter.status_code == 200
    assert letter.data.startswith(b"%PDF")

    employees = admin_client.get("/recruitment/admin/employees")
    assert employees.status_code == 200
    assert employee.employee_code.encode() in employees.data
    assert b"View Appointment Letter" in employees.data
    dash = admin_client.get("/recruitment/admin/")
    assert dash.status_code == 200
    assert b"Employees Created" in dash.data
    assert b"Appointment Issued" in dash.data

    public = admin_client.post(
        "/careers/application-status",
        data={"application_number": application.application_number, "mobile": "9876543210"},
    )
    assert b"Appointment Letter Issued" in public.data
    assert b"Recommended" not in public.data
    assert b"Convert to Employee" not in public.data


def test_viewer_cannot_download_offer(app, admin_client):
    from recruitment.models import AdminUser

    viewer = AdminUser(name="Viewer", email="viewer@jtcsxpert.com", role="viewer", is_active_flag=True)
    viewer.set_password("ViewOnly!234")
    db.session.add(viewer)
    db.session.commit()
    application = _apply(admin_client)
    admin_client.post(f"/recruitment/admin/applications/{application.application_id}/status", data={"status": "Selected"})
    admin_client.post(f"/recruitment/admin/applications/{application.application_id}/convert")
    employee = Employee.query.first()
    admin_client.post(f"/recruitment/admin/employees/{employee.employee_id}/offer")
    allowed = admin_client.get(f"/recruitment/admin/employees/{employee.employee_id}/offer.pdf")
    assert allowed.status_code == 200
    admin_client.post("/recruitment/admin/logout")
    login = admin_client.post(
        "/recruitment/admin/login",
        data={"email": "viewer@jtcsxpert.com", "password": "ViewOnly!234"},
        follow_redirects=True,
    )
    assert login.status_code == 200
    assert b"Viewer" in login.data
    denied = admin_client.get(f"/recruitment/admin/employees/{employee.employee_id}/offer.pdf")
    assert denied.status_code == 403
