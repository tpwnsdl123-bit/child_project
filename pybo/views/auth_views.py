# pybo/views/auth_views.py
from functools import wraps

from flask import Blueprint, url_for, render_template, request, flash, session, g
from werkzeug.utils import redirect

from pybo import db  # load_logged_in_user에서 Users.query 대신 repo 써도 되지만, 우선 기존 import 유지
from pybo.forms import (
    UserCreateForm,
    UserLoginForm,
    FindIdForm,
    ResetPasswordVerifyForm,
    ResetPasswordChangeForm,
)
from pybo.service.auth_service import AuthService
from pybo.service.user_repository import UserRepository
from pybo.models import Users

bp = Blueprint('auth', __name__, url_prefix='/auth')

auth_service = AuthService(UserRepository())


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('auth.login'))
        return view(**kwargs)

    return wrapped_view


@bp.route('/signup', methods=('GET', 'POST'))
def signup():
    form = UserCreateForm()
    if request.method == 'POST' and form.validate_on_submit():
        user, error = auth_service.create_user_from_form(form)
        if error:
            flash(error)
            return render_template('auth/signup.html', form=form, auth_page=True)

        return redirect(url_for('main.index'))

    return render_template('auth/signup.html', form=form, auth_page=True)


@bp.route('/login', methods=('GET', 'POST'))
def login():
    form = UserLoginForm()
    if request.method == 'POST' and form.validate_on_submit():
        user, error = auth_service.authenticate(form)
        if error:
            flash(error)
            return render_template('auth/login.html', form=form, auth_page=True)

        # 로그인 성공
        session.clear()
        session['user_id'] = user.id
        return redirect(url_for('main.index'))

    return render_template('auth/login.html', form=form, auth_page=True)


@bp.before_app_request
def load_logged_in_user():
    """
    매 요청마다 session의 user_id로 사용자 객체를 g.user에 세팅.
    (기존 동작 그대로 유지)
    """
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        g.user = Users.query.get(user_id)


@bp.route('/logout')
def logout():
    session.clear()
    return render_template('auth/logout.html')


@bp.route('/find-id', methods=('GET', 'POST'))
def find_id():
    form = FindIdForm()
    username = None

    if request.method == 'POST' and form.validate_on_submit():
        username = auth_service.find_username_by_email(form.email.data)
        if username is None:
            flash('해당 이메일로 가입된 아이디가 없습니다.')

    return render_template('auth/find_id.html', form=form, username=username, auth_page=True)


@bp.route('/reset-password', methods=('GET', 'POST'))
def reset_password_verify():
    form = ResetPasswordVerifyForm()
    if request.method == 'POST' and form.validate_on_submit():
        user = auth_service.find_user_for_reset(
            username=form.username.data,
            email=form.email.data,
        )

        if not user:
            flash('아이디 또는 이메일이 일치하지 않습니다.')
        else:
            # 2단계에서 쓸 user_id를 세션에 잠깐 저장
            session['reset_user_id'] = user.id
            return redirect(url_for('auth.reset_password_change'))

    return render_template('auth/reset_password_verify.html', form=form, auth_page=True)


@bp.route('/reset-password/change', methods=('GET', 'POST'))
def reset_password_change():
    user_id = session.get('reset_user_id')

    # 1단계 정보 없이 바로 들어오면 막기
    if user_id is None:
        flash('비밀번호 재설정 정보가 없습니다. 다시 시도해주세요.')
        return redirect(url_for('auth.reset_password_verify'))

    form = ResetPasswordChangeForm()

    if request.method == 'POST' and form.validate_on_submit():
        ok = auth_service.change_password(user_id, form.password1.data)
        if not ok:
            flash('사용자 정보를 찾을 수 없습니다.')
            return redirect(url_for('auth.reset_password_verify'))

        # 한 번 쓰고 세션에서 제거
        session.pop('reset_user_id', None)

        flash('비밀번호가 변경되었습니다. 새 비밀번호로 로그인해주세요.')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password_change.html', form=form, auth_page=True)
