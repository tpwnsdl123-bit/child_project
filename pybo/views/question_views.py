from flask import Blueprint, render_template, request, url_for, g, flash
from werkzeug.utils import redirect
from datetime import datetime

from pybo import db
from pybo.models import Question
from ..forms import QuestionForm, AnswerForm
from pybo.views.auth_views import login_required

bp = Blueprint('question', __name__, url_prefix='/question')

# 질문 목록
@bp.route('/list/')
def _list():
    page = request.args.get('page', type=int, default=1)
    question_list = Question.query.order_by(Question.create_date.desc()).paginate(
        page=page,
        per_page=10
    )
    # 여기서 qna.html 또는 question_list.html 둘 중 하나 골라서 사용
    return render_template('question/qna.html', question_list=question_list)
    # 만약 qna.html 대신 기존 리스트만 쓰고 싶으면:
    # return render_template('question/question_list.html', question_list=question_list)


# 질문 상세
@bp.route('/detail/<int:question_id>/')
def detail(question_id):
    question = Question.query.get_or_404(question_id)
    form = AnswerForm()
    return render_template('question/question_detail.html',
                           question=question, form=form)


# 질문 작성
@bp.route('/create/', methods=('GET', 'POST'))
@login_required
def create():
    form = QuestionForm()
    if request.method == 'POST' and form.validate_on_submit():
        question = Question(
            subject=form.subject.data,
            content=form.content.data,
            create_date=datetime.now(),
             user=g.user,
        )
        db.session.add(question)
        db.session.commit()
        return redirect(url_for('question._list'))

    return render_template('question/question_form.html', form=form)

#질문 삭제
@bp.route('/delete/<int:question_id>/')
@login_required
def delete(question_id):
    question = Question.query.get_or_404(question_id)

    # ★ 권한 체크
    if question.user_id != g.user.id and not g.user.is_admin:
        flash('삭제 권한이 없습니다.')
        return redirect(url_for('question.detail', question_id=question_id))

    db.session.delete(question)
    db.session.commit()
    return redirect(url_for('question._list'))

# 질문 수정
@bp.route('/modify/<int:question_id>/', methods=('GET', 'POST'))
@login_required
def modify(question_id):
    question = Question.query.get_or_404(question_id)

    # 작성자 아니고 관리자도 아니면 막기
    if question.user_id != g.user.id and not g.user.is_admin:
        flash('수정 권한이 없습니다.')
        return redirect(url_for('question.detail', question_id=question_id))

    form = QuestionForm(obj=question)  # 기존 내용 폼에 채워 넣기

    if request.method == 'POST' and form.validate_on_submit():
        question.subject = form.subject.data
        question.content = form.content.data
        db.session.commit()
        return redirect(url_for('question.detail', question_id=question_id))

    return render_template('question/question_form.html', form=form)