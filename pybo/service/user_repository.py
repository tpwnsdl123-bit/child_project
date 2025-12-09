from pybo import db
from pybo.models import Users


class UserRepository:

    def get_by_id(self, user_id: int) -> Users | None:
        return Users.query.get(user_id)

    def get_by_username(self, username: str) -> Users | None:
        return Users.query.filter_by(username=username).first()

    def get_by_email(self, email: str) -> Users | None:
        return Users.query.filter_by(email=email).first()

    def get_by_username_and_email(self, username: str, email: str) -> Users | None:
        return Users.query.filter_by(username=username, email=email).first()

    def add(self, user: Users):
        db.session.add(user)

    def commit(self):
        db.session.commit()

    def rollback(self):
        db.session.rollback()
