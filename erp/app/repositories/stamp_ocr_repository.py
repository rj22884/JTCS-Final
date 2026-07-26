from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.stamp import StampOcrImage


class StampOcrRepository:
    def __init__(self, session: Session | None = None):
        self.session = session or db.session

    def create(self, data: dict) -> StampOcrImage:
        data.setdefault("CreatedDate", datetime.utcnow())
        row = StampOcrImage(**data)
        self.session.add(row)
        self.session.flush()
        return row

    def link_stamp(self, ocr_image_id: int, stamp_id: int) -> None:
        row = self.session.get(StampOcrImage, ocr_image_id)
        if row:
            row.StampID = stamp_id
            self.session.flush()

    def get_by_id(self, ocr_image_id: int) -> StampOcrImage | None:
        return self.session.get(StampOcrImage, ocr_image_id)

    def unlink_stamp(self, stamp_id: int) -> None:
        rows = self.session.scalars(
            select(StampOcrImage).where(StampOcrImage.StampID == stamp_id)
        ).all()
        for row in rows:
            row.StampID = None
        self.session.flush()

    def has_linked_stamp(self, stamp_id: int) -> bool:
        stmt = select(StampOcrImage.StampID).where(StampOcrImage.StampID == stamp_id).limit(1)
        return self.session.scalars(stmt).first() is not None
