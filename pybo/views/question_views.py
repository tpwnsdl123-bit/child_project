from flask import Blueprint, render_template, request, url_for, g, flash
from werkzeug.utils import redirect

from ..forms import QuestionForm, AnswerForm
from pybo.views.auth_views import login_required
from pybo.service.qna_service import QnaService

bp = Blueprint('question', __name__, url_prefix='/question')

qna_service = QnaService()

# 질문 목록
@bp.route('/list/')
def _list():
    page = request.args.get('page', type=int, default=1)
    question_list = qna_service.get_question_list(page=page, per_page=10)

    return render_template('question/qna.html', question_list=question_list)

# 질문 상세
@bp.route('/detail/<int:question_id>/')
def detail(question_id):
    question = qna_service.get_question_detail(question_id)
    form = AnswerForm()
    return render_template('question/question_detail.html',
                           question=question, form=form)


# 질문 작성
@bp.route('/create/', methods=('GET', 'POST'))
@login_required
def create():
    form = QuestionForm()
    if request.method == 'POST' and form.validate_on_submit():
        qna_service.create_question_from_form(form)
        return redirect(url_for('question._list'))

    return render_template('question/question_form.html', form=form)

#질문 삭제
@bp.route('/delete/<int:question_id>/')
@login_required
def delete(question_id):
    question = qna_service.get_question_detail(question_id)

    # 권한 체크
    if not qna_service.can_edit_or_delete(question, g.user):
        flash('삭제 권한이 없습니다.')
        return redirect(url_for('question.detail', question_id=question_id))

    qna_service.delete_question(question)
    return redirect(url_for('question._list'))

# 질문 수정
@bp.route('/modify/<int:question_id>/', methods=('GET', 'POST'))
@login_required
def modify(question_id):
    question = qna_service.get_question_detail(question_id)

    # 작성자 아니고 관리자도 아니면 막기
    if not qna_service.can_edit_or_delete(question, g.user):
        flash('수정 권한이 없습니다.')
        return redirect(url_for('question.detail', question_id=question_id))

    form = QuestionForm(obj=question)  # 기존 내용 폼에 채워 넣기

    if request.method == 'POST' and form.validate_on_submit():
        qna_service.update_question_from_form(question, form)
        return redirect(url_for('question.detail', question_id=question_id))

    return render_template('question/question_form.html', form=form)