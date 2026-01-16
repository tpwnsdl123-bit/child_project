import os
import sys

# 프로젝트 루트를 경로에 추가
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

from pybo.service.genai_service import get_genai_service
from pybo import create_app, db

def test_agent():
    app = create_app()
    with app.app_context():
        service = get_genai_service()
        
        print("\n=== [테스트 1: 법령 질문 (RAG)] ===")
        q1 = "지역아동센터 종사자 인건비 기준에 대해 알려줘"
        print(f"질문: {q1}")
        print(f"답변: {service.answer_qa_with_log(q1)}")

        print("\n=== [테스트 2: 통계 질문 (DB)] ===")
        q2 = "강남구의 2025년 아동 인구 예측치를 알려줘"
        print(f"질문: {q2}")
        print(f"답변: {service.answer_qa_with_log(q2)}")

        print("\n=== [테스트 3: 복합 질문 (RAG + DB)] ===")
        q3 = "강남구 아동 인구 변화에 맞춰서 필요한 인건비 지원 정책을 추천해줘"
        print(f"질문: {q3}")
        print(f"답변: {service.answer_qa_with_log(q3)}")

if __name__ == "__main__":
    test_agent()
