
from sqlalchemy.orm import Session

from app.models.teacher_group import TeacherGroup


class TeacherGroupRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, link: TeacherGroup) -> TeacherGroup:
        self.db.add(link)
        self.db.flush()
        return link
