from typing import Tuple, Optional

from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import IntegrityError

from pybo.models import Users
from pybo.service.user_repository import UserRepository


class AuthService: # 회원가입, 로그인, 비빌번호 재설정 담당

    def __init__(self, user_repo: UserRepository | None = None):
        self.user_repo = user_repo or UserRepository()

    def create_user_from_form(self, form) -> Tuple[Optional[Users], Optional[str]]: # 회원가입

        if self.user_repo.get_by_username(form.username.data):
            return None, '이미 사용 중인 아이디입니다.'

        if self.user_repo.get_by_email(form.email.data):
            return None, '이미 사용 중인 이메일입니다.'

        user = Users(
            username=form.username.data,
            password=generate_password_hash(form.password1.data),
            email=form.email.data,
        )
        self.user_repo.add(user)

        try:
            self.user_repo.commit()
        except IntegrityError:
            self.user_repo.rollback()
            return None, '이미 사용 중인 아이디 또는 이메일입니다.'

        return user, None

    def authenticate(self, form) -> Tuple[Optional[Users], Optional[str]]: # 로그인
        user = self.user_repo.get_by_username(form.username.data)
        if not user:
            return None, '존재하지 않는 사용자입니다.'

        if not check_password_hash(user.password, form.password.data):
            return None, '비밀번호가 올바르지 않습니다.'

        return user, None

    def find_username_by_email(self, email: str) -> Optional[str]: # 아이디 찾기
        user = self.user_repo.get_by_email(email)
        return user.username if user else None

    def find_user_for_reset(self, username: str, email: str) -> Optional[Users]: # 비밀번호 재설정 (1단계 검증)
        return self.user_repo.get_by_username_and_email(username, email)

    def change_password(self, user_id: int, new_password: str) -> bool: # 비밀번호 변경
        user = self.user_repo.get_by_id(user_id)
        if user is None:
            return False
        user.password = generate_password_hash(new_password)
        self.user_repo.commit()
        return True
