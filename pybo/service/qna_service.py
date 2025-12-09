# pybo/service/qna_service.py
from flask import g

from pybo.service.question_repository import QuestionRepository


class QnaService: # Q&A 도메인 로직

    def __init__(self, question_repo: QuestionRepository | None = None):
        self.question_repo = question_repo or QuestionRepository()

    def get_question_list(self, page: int, per_page: int = 10): # 질문 목록
        """
        질문 목록(페이지네이션) 조회
        """
        return self.question_repo.get_question_page(page, per_page)

    def get_question_detail(self, question_id: int): # 질문 상세
        """
        질문 상세 조회 (없으면 404)
        """
        return self.question_repo.get_question_or_404(question_id)

    def can_edit_or_delete(self, question, user) -> bool: # 권한 체크
        """작성자이거나 관리자면 True"""
        if user is None:
            return False
        return question.user_id == user.id or getattr(user, "is_admin", False)

    def create_question_from_form(self, form): # 질문 생성
        """폼과 g.user를 사용해 질문 생성"""
        return self.question_repo.create_question(
            subject=form.subject.data,
            content=form.content.data,
            user=g.user,
        )

    def update_question_from_form(self, question, form): # 질문 수정
        return self.question_repo.update_question(
            question,
            subject=form.subject.data,
            content=form.content.data,
        )

    def delete_question(self, question): # 질문 삭제
        self.question_repo.delete_question(question)

    def create_answer(self, question_id: int, content: str): # 답변 생성
        question = self.question_repo.get_question_or_404(question_id)
        return self.question_repo.create_answer(question, content)
