from datetime import datetime

from pybo import db
from pybo.models import Question, Answer

class QuestionRepository:
    def get_question_page(self, page: int, per_page: int = 10): # 질문 목록(페이징)
        return (
            Question.query
            .order_by(Question.create_date.desc())
            .paginate(page=page, per_page=per_page)
        )

    def get_question_or_404(self, question_id: int) -> Question: # 질문 조회
        return Question.query.get_or_404(question_id)

    def create_question(self, subject: str, content: str, user): # 질문 생성
        question = Question(
            subject= subject,
            content= content,
            create_date= datetime.now(),
            user= user,
        )
        db.session.add(question)
        db.session.commit()
        return question

    def update_question(self, question: Question, content: str): # 답변 생성
        answer = Answer(
            content= content,
            create_date= datetime.now(),
        )
        question.answer_set.append(answer)
        db.session.commit()
        return answer