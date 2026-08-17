"""Recruitment dashboard and analytics queries."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import case, func

from recruitment.extensions import db
from recruitment.job_window import job_window_payload
from recruitment.models import Candidate, CandidateExperience, Employee, Job, JobApplication, OfferLetter, RecruitmentAuditLog


def _pct(part: int, whole: int) -> float:
    if not whole:
        return 0.0
    return round((part / whole) * 100, 2)


def dashboard_stats() -> dict:
    clicks = RecruitmentAuditLog.query.filter_by(event_type="SALES_EXECUTIVE_CTA_CLICK").count()
    unique_visitors = (
        db.session.query(func.count(func.distinct(RecruitmentAuditLog.visitor_id)))
        .filter(RecruitmentAuditLog.event_type == "SALES_EXECUTIVE_CTA_CLICK")
        .filter(RecruitmentAuditLog.visitor_id.isnot(None))
        .scalar()
        or 0
    )
    job_views = RecruitmentAuditLog.query.filter_by(event_type="JOB_PAGE_VIEW").count()
    started = RecruitmentAuditLog.query.filter_by(event_type="APPLICATION_STARTED").count()
    submitted = JobApplication.query.count()
    new_apps = JobApplication.query.filter_by(application_status="New").count()
    under_review = JobApplication.query.filter_by(application_status="Under Review").count()
    shortlisted = JobApplication.query.filter_by(application_status="Shortlisted").count()
    interview = JobApplication.query.filter_by(application_status="Interview Scheduled").count()
    selected = JobApplication.query.filter_by(application_status="Selected").count()
    rejected = JobApplication.query.filter_by(application_status="Rejected").count()

    visitors_who_clicked = (
        db.session.query(RecruitmentAuditLog.visitor_id)
        .filter(RecruitmentAuditLog.event_type == "SALES_EXECUTIVE_CTA_CLICK")
        .filter(RecruitmentAuditLog.visitor_id.isnot(None))
        .distinct()
        .subquery()
    )
    applied_after_click = (
        db.session.query(func.count(func.distinct(JobApplication.visitor_id)))
        .filter(JobApplication.visitor_id.in_(db.session.query(visitors_who_clicked.c.visitor_id)))
        .scalar()
        or 0
    )

    first_click = (
        db.session.query(func.min(RecruitmentAuditLog.event_timestamp))
        .filter_by(event_type="SALES_EXECUTIVE_CTA_CLICK")
        .scalar()
    )
    last_click = (
        db.session.query(func.max(RecruitmentAuditLog.event_timestamp))
        .filter_by(event_type="SALES_EXECUTIVE_CTA_CLICK")
        .scalar()
    )

    return {
        "cta_clicks": clicks,
        "unique_visitors": unique_visitors,
        "job_page_views": job_views,
        "applications_started": started,
        "applications_submitted": submitted,
        "new_applications": new_apps,
        "under_review": under_review,
        "shortlisted": shortlisted,
        "interview_scheduled": interview,
        "selected": selected,
        "rejected": rejected,
        "hr_selected": JobApplication.query.filter_by(application_status="Selected").count(),
        "hr_offers_pending": OfferLetter.query.filter_by(offer_status="Pending").count(),
        "hr_offers_accepted": OfferLetter.query.filter_by(offer_status="Accepted").count(),
        "hr_appointment_issued": Employee.query.filter_by(employment_status="Appointment Issued").count(),
        "hr_employees": Employee.query.count(),
        "click_to_apply": applied_after_click,
        "click_to_apply_rate": _pct(applied_after_click, unique_visitors),
        "cta_to_application_rate": _pct(submitted, clicks),
        "cta_to_view": _pct(job_views, clicks),
        "view_to_started": _pct(started, job_views),
        "started_to_submitted": _pct(submitted, started),
        "submitted_to_shortlisted": _pct(shortlisted, submitted),
        "shortlisted_to_selected": _pct(selected, shortlisted),
        "first_click": first_click.isoformat(sep=" ", timespec="minutes") if first_click else None,
        "last_click": last_click.isoformat(sep=" ", timespec="minutes") if last_click else None,
    }


def _series(event_type: str | None, days: int = 30, applications: bool = False) -> list[dict]:
    start = datetime.utcnow() - timedelta(days=days - 1)
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    if applications:
        rows = (
            db.session.query(func.date(JobApplication.submitted_at), func.count(JobApplication.application_id))
            .filter(JobApplication.submitted_at >= start)
            .group_by(func.date(JobApplication.submitted_at))
            .all()
        )
    else:
        rows = (
            db.session.query(func.date(RecruitmentAuditLog.event_timestamp), func.count(RecruitmentAuditLog.id))
            .filter(RecruitmentAuditLog.event_type == event_type)
            .filter(RecruitmentAuditLog.event_timestamp >= start)
            .group_by(func.date(RecruitmentAuditLog.event_timestamp))
            .all()
        )
    mapped = {str(day): count for day, count in rows}
    out = []
    for i in range(days):
        day = (start + timedelta(days=i)).date().isoformat()
        out.append({"label": day, "value": int(mapped.get(day, 0))})
    return out


def analytics_payload() -> dict:
    weekly = (
        db.session.query(
            func.strftime("%Y-W%W", JobApplication.submitted_at),
            func.count(JobApplication.application_id),
        )
        .group_by(func.strftime("%Y-W%W", JobApplication.submitted_at))
        .order_by(func.strftime("%Y-W%W", JobApplication.submitted_at))
        .all()
    )
    monthly = (
        db.session.query(
            func.strftime("%Y-%m", JobApplication.submitted_at),
            func.count(JobApplication.application_id),
        )
        .group_by(func.strftime("%Y-%m", JobApplication.submitted_at))
        .order_by(func.strftime("%Y-%m", JobApplication.submitted_at))
        .all()
    )

    from recruitment.models import CandidateEducation

    highest = (
        db.session.query(CandidateEducation.qualification, func.count(JobApplication.application_id))
        .select_from(JobApplication)
        .join(Candidate, Candidate.candidate_id == JobApplication.candidate_id)
        .join(CandidateEducation, CandidateEducation.candidate_id == Candidate.candidate_id)
        .filter(CandidateEducation.education_type == "highest")
        .group_by(CandidateEducation.qualification)
        .all()
    )
    cities = (
        db.session.query(Candidate.city, func.count(JobApplication.application_id))
        .join(JobApplication, JobApplication.candidate_id == Candidate.candidate_id)
        .group_by(Candidate.city)
        .order_by(func.count(JobApplication.application_id).desc())
        .limit(12)
        .all()
    )
    submitted = JobApplication.query.count()
    sources = (
        db.session.query(JobApplication.source, func.count(JobApplication.application_id))
        .group_by(JobApplication.source)
        .all()
    )
    statuses = (
        db.session.query(JobApplication.application_status, func.count(JobApplication.application_id))
        .group_by(JobApplication.application_status)
        .all()
    )
    years_expr = func.coalesce(CandidateExperience.sales_experience_years, 0)
    buckets = (
        db.session.query(
            case(
                (years_expr <= 0, "Freshers"),
                (years_expr <= 2, "1–2 Years"),
                (years_expr <= 5, "2–5 Years"),
                else_="5+ Years",
            ),
            func.count(JobApplication.application_id),
        )
        .select_from(JobApplication)
        .join(CandidateExperience, CandidateExperience.candidate_id == JobApplication.candidate_id)
        .group_by(
            case(
                (years_expr <= 0, "Freshers"),
                (years_expr <= 2, "1–2 Years"),
                (years_expr <= 5, "2–5 Years"),
                else_="5+ Years",
            )
        )
        .all()
    )
    return {
        "daily_cta": _series("SALES_EXECUTIVE_CTA_CLICK"),
        "daily_applications": _series(None, applications=True),
        "weekly_applications": [{"label": label or "", "value": int(count)} for label, count in weekly],
        "monthly_applications": [{"label": label or "", "value": int(count)} for label, count in monthly],
        "by_source": [
            {
                "label": label or "Not specified",
                "value": int(count),
                "pct": _pct(int(count), submitted),
            }
            for label, count in sources
        ],
        "by_city": [{"label": label or "Not specified", "value": int(count)} for label, count in cities],
        "by_qualification": [{"label": label or "Not specified", "value": int(count)} for label, count in highest],
        "by_experience": [{"label": label, "value": int(count)} for label, count in buckets],
        "by_status": [{"label": label or "Unknown", "value": int(count)} for label, count in statuses],
        "stats": dashboard_stats(),
        "job_window": job_window_payload(Job.query.filter_by(slug="sales-executive").first()),
    }
