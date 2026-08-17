"""Shared admin queries over the existing application tables."""

from __future__ import annotations

from datetime import datetime

from flask import Request
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from recruitment.extensions import db
from recruitment.models import Candidate, CandidateEducation, CandidateExperience, JobApplication


def education_map(candidate: Candidate) -> dict:
    highest = next((e for e in candidate.education if e.education_type == "highest"), None)
    last = next((e for e in candidate.education if e.education_type == "last"), None)
    if highest is None and candidate.education:
        highest = candidate.education[0]
    primary = last or highest
    degree = (last.qualification if last else None) or (highest.qualification if highest else "")
    return {
        "highest": highest.qualification if highest else "",
        "last": last.qualification if last else degree,
        "degree": degree,
        "university": primary.university_board if primary else "",
        "year": primary.passing_year if primary else "",
        "score": primary.percentage_cgpa if primary else "",
    }


def experience_label(exp: CandidateExperience | None) -> str:
    if exp is None:
        return "—"
    years = exp.sales_experience_years or 0
    months = exp.sales_experience_months or 0
    if years <= 0 and months <= 0:
        return "Fresher – 0 Years Experience"
    parts = []
    if years:
        parts.append(f"{years} Year{'s' if years != 1 else ''}")
    if months:
        parts.append(f"{months} Month{'s' if months != 1 else ''}")
    return " ".join(parts) or "Fresher – 0 Years Experience"


def filtered_applications(req: Request):
    q = (
        JobApplication.query.join(Candidate)
        .outerjoin(CandidateExperience, CandidateExperience.candidate_id == Candidate.candidate_id)
        .options(
            joinedload(JobApplication.candidate).joinedload(Candidate.education),
            joinedload(JobApplication.candidate).joinedload(Candidate.experience),
        )
    )
    search = (req.args.get("q") or "").strip()
    status = (req.args.get("status") or "").strip()
    city = (req.args.get("city") or "").strip()
    source = (req.args.get("source") or "").strip()
    qualification = (req.args.get("qualification") or "").strip()
    experience = (req.args.get("experience") or "").strip()
    date_from = (req.args.get("from") or "").strip()
    date_to = (req.args.get("to") or "").strip()

    if search:
        like = f"%{search}%"
        q = q.filter(
            or_(
                JobApplication.application_number.ilike(like),
                Candidate.name.ilike(like),
                Candidate.email.ilike(like),
                Candidate.mobile.ilike(like),
                Candidate.city.ilike(like),
                CandidateExperience.previous_company.ilike(like),
            )
        )
    if status:
        q = q.filter(JobApplication.application_status == status)
    if city:
        q = q.filter(Candidate.city == city)
    if source:
        q = q.filter(JobApplication.source == source)
    if date_from:
        q = q.filter(JobApplication.submitted_at >= datetime.strptime(date_from, "%Y-%m-%d"))
    if date_to:
        q = q.filter(JobApplication.submitted_at <= datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59))
    if qualification:
        q = q.join(CandidateEducation, CandidateEducation.candidate_id == Candidate.candidate_id).filter(
            CandidateEducation.qualification == qualification
        )
    if experience == "fresher":
        q = q.filter(db.func.coalesce(CandidateExperience.sales_experience_years, 0) <= 0)
    elif experience == "1-2":
        q = q.filter(CandidateExperience.sales_experience_years.between(1, 2))
    elif experience == "2-5":
        q = q.filter(CandidateExperience.sales_experience_years > 2, CandidateExperience.sales_experience_years <= 5)
    elif experience == "5plus":
        q = q.filter(CandidateExperience.sales_experience_years > 5)

    sort = req.args.get("sort") or "submitted_at"
    direction = req.args.get("dir") or "desc"
    sort_map = {
        "submitted_at": JobApplication.submitted_at,
        "name": Candidate.name,
        "status": JobApplication.application_status,
        "city": Candidate.city,
        "number": JobApplication.application_number,
        "experience": CandidateExperience.sales_experience_years,
    }
    col = sort_map.get(sort, JobApplication.submitted_at)
    q = q.distinct().order_by(col.asc() if direction == "asc" else col.desc())
    return q


def filter_options() -> dict:
    cities = [r[0] for r in db.session.query(Candidate.city).distinct().order_by(Candidate.city).all() if r[0]]
    sources = [r[0] for r in db.session.query(JobApplication.source).distinct().all() if r[0]]
    qualifications = [
        r[0]
        for r in db.session.query(CandidateEducation.qualification).distinct().order_by(CandidateEducation.qualification).all()
        if r[0]
    ]
    return {"cities": cities, "sources": sources, "qualifications": qualifications}
