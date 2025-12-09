# pybo/views/answer_views.py
from flask import Blueprint, url_for, request, render_template
from werkzeug.utils import redirect

from .auth_views import login_required
from ..forms import AnswerForm
from pybo.service.qna_service import QnaService

bp = Blueprint('answer', __name__, url_prefix='/answer')

qna_service = QnaService()


@bp.route('/create/<int:question_id>', methods=('GET', 'POST'))
@login_required
def create(question_id):
    form = AnswerForm()
    question = qna_service.get_question_detail(question_id)

    if form.validate_on_submit():
        content = request.form['content']
        qna_service.create_answer(question_id, content)
        return redirect(url_for('question.detail', question_id=question_id))

    return render_template(
        'question/question_detail.html',
        question=question,
        form=form,
    )
