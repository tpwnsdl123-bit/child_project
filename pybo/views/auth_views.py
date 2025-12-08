from flask import Blueprint, url_for, render_template, request, flash, session, g
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import redirect
from functools import wraps

from pybo import db
from pybo.forms import UserCreateForm, UserLoginForm, FindIdForm, ResetPasswordVerifyForm, ResetPasswordChangeForm
from pybo.models import Users


bp = Blueprint('auth',__name__, url_prefix='/auth')

def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('auth.login'))
        return view(**kwargs)
    return wrapped_view


from sqlalchemy.exc import IntegrityError

@bp.route('/signup', methods=('GET', 'POST'))
def signup():
    form = UserCreateForm()
    if request.method == 'POST' and form.validate_on_submit():

        # 1) 아이디 중복 체크
        user_by_name = Users.query.filter_by(username=form.username.data).first()
        if user_by_name:
            flash('이미 사용 중인 아이디입니다.')
            return render_template('auth/signup.html', form=form, auth_page=True)

        # 2) 이메일 중복 체크
        user_by_email = Users.query.filter_by(email=form.email.data).first()
        if user_by_email:
            flash('이미 사용 중인 이메일입니다.')
            return render_template('auth/signup.html', form=form, auth_page=True)

        # 3) 둘 다 통과하면 저장 시도
        user = Users(
            username=form.username.data,
            password=generate_password_hash(form.password1.data),
            email=form.email.data,
        )
        db.session.add(user)

        try:
            db.session.commit()
        except IntegrityError:
            # 혹시 모를 예외 대비 (레이스 컨디션 등)
            db.session.rollback()
            flash('이미 사용 중인 아이디 또는 이메일입니다.')
            return render_template('auth/signup.html', form=form, auth_page=True)

        return redirect(url_for('main.index'))

    return render_template('auth/signup.html', form=form, auth_page=True)


@bp.route('/login', methods=('GET', 'POST'))
def login():
    form = UserLoginForm()
    if request.method == 'POST' and form.validate_on_submit():
        error = None
        user = Users.query.filter_by(username=form.username.data).first()
        if not user:
            error = '존재하지 않는 사용자입니다.'
        elif not check_password_hash(user.password, form.password.data):
            error = '비밀번호가 올바르지 않습니다.'
        if error is None:
            session.clear()
            session['user_id'] = user.id
            return redirect(url_for('main.index'))
        flash(error)
    return render_template('auth/login.html', form=form, auth_page=True)


@bp.before_app_request
def load_logged_in_user():
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
        user = Users.query.filter_by(email=form.email.data).first()
        if user:
            username = user.username
        else:
            flash('해당 이메일로 가입된 아이디가 없습니다.')

    return render_template('auth/find_id.html', form=form, username=username, auth_page=True)


@bp.route('/reset-password', methods=('GET', 'POST'))
def reset_password_verify():
    form = ResetPasswordVerifyForm()
    if request.method == 'POST' and form.validate_on_submit():
        user = Users.query.filter_by(
            username=form.username.data,
            email=form.email.data
        ).first()

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
        user = Users.query.get(user_id)
        if user is None:
            flash('사용자 정보를 찾을 수 없습니다.')
            return redirect(url_for('auth.reset_password_verify'))

        user.password = generate_password_hash(form.password1.data)
        db.session.commit()

        # 한 번 쓰고 세션에서 제거
        session.pop('reset_user_id', None)

        flash('비밀번호가 변경되었습니다. 새 비밀번호로 로그인해주세요.')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password_change.html', form=form, auth_page=True)
