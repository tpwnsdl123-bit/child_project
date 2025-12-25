import requests
import json
import os
import time  # 시간 측정을 위해 추가
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import Optional
from pybo import db
from pybo.models import RegionForecast
from sqlalchemy import func

load_dotenv()


@dataclass
class QueryMeta:
    district: str = "전체"
    start_year: Optional[int] = None
    end_year: Optional[int] = None


class GenAIService:
    def __init__(self) -> None:
        self.api_url = os.getenv("RUNPOD_API_URL")
        self._rag_service = None
        # 세션을 미리 생성하여 연결 속도를 높입니다.
        self.session = requests.Session()
        self.default_settings = {"temperature": 0.1, "max_tokens": 300}

    @property
    def rag_service(self):
        """Q&A가 필요할 때만 RAG 서비스를 로드합니다 (Lazy Loading)."""
        if self._rag_service is None:
            from pybo.service.rag_service import RagService
            print("--- 무거운 임베딩 모델 로딩 중... ---")
            self._rag_service = RagService()
        return self._rag_service

    def _call_llama3(self, instruction: str, input_text: str, max_tokens: int = None,
                     model_version: str = "final") -> str:
        start = time.time()  # 추론 시간 측정 시작
        headers = {'Content-Type': 'application/json'}
        payload = {
            "instruction": instruction,
            "input": input_text,
            "model_version": model_version,
            "max_new_tokens": max_tokens or self.default_settings["max_tokens"],
            "temperature": self.default_settings["temperature"]
        }
        try:
            # 런포드 서버로 요청 전송
            response = self.session.post(self.api_url, json=payload, timeout=180)
            response.raise_for_status()
            print(f"--- AI 추론 완료 (소요시간: {time.time() - start:.2f}초) ---")  #
            return response.json().get("text", "").strip()
        except Exception as e:
            return f"Error communicating with AI server: {e}"

    def generate_report_with_data(self, user_prompt: str, **kwargs) -> str:
        start_all = time.time()
        print(f"\n[로그 1] 함수 진입 완료: {time.time() - start_all:.4f}s")  #

        meta = self._extract_query_meta(user_prompt)
        meta.district = kwargs.get('district', meta.district)
        meta.end_year = kwargs.get('end_year', meta.end_year)
        meta.start_year = kwargs.get('start_year', 2023)
        print(f"[로그 2] 메타데이터 추출 완료: {time.time() - start_all:.4f}s")  #

        # --- 여기서 시간이 걸리는지 확인 ---
        print(f"[로그 3] DB 조회 시작...")  #
        sql_context = self._build_forecast_context(meta)
        print(f"[로그 4] DB 조회 및 가공 완료: {time.time() - start_all:.4f}s")  #
        # -----------------------------

        instruction = (
            "너는 서울시 아동복지 정책 전문가다. 반드시 한국어로 답해.\n"
            "아래 형식을 정확히 지켜. (딱 3줄만, 추가 문장/설명 금지)\n"
            "- 요약: 한 문장\n"
            "- 가능 요인: 한 문장\n"
            "- 추가 데이터: 한 문장\n"
        )
        input_text = f"지역:{meta.district}\n기간:{meta.start_year}-{meta.end_year}\n데이터:\n{sql_context}"

        print(f"[로그 5] 런포드 요청 직전: {time.time() - start_all:.4f}s")  #

        # 여기서 런포드 터미널 로그와 대조해봐야 합니다.
        raw_response = self._call_llama3(
            instruction,
            input_text,
            max_tokens=128,
            model_version=kwargs.get('model_version', 'final')
        )
        print(f"[로그 6] 런포드 응답 수신 완료: {time.time() - start_all:.4f}s")  #
        report_data = {
            "title": f"{meta.district} 지역아동센터 수요 분석",
            "summary": "분석 완료",
            "content": raw_response
        }

        # 파싱 로직 개선: split("-") 대신 다음 항목 키워드로 자르기
        if "- 요약:" in raw_response:
            try:
                summary_part = raw_response.split("- 요약:")[1]
                # '가능 요인' 항목 전까지만 가져옵니다.
                report_data["summary"] = summary_part.split("- 가능 요인:")[0].strip()
            except:
                pass
        return json.dumps(report_data, ensure_ascii=False)

    def generate_policy(self, user_prompt: str, **kwargs) -> str:
        instruction = (
            "반드시 한국어로 답해라.\n"
            "정책 아이디어 3가지를 한 줄씩만 제시해라. 추가 설명 금지.\n"
            "형식:\n"
            "1) ...\n"
            "2) ...\n"
            "3) ...\n"
        )
        # 정책 제안도 RAG 없이 바로 런포드 호출
        return self._call_llama3(
            instruction,
            user_prompt,
            max_tokens=96,
            model_version=kwargs.get('model_version', 'final')
        )

    def answer_qa_with_log(self, question: str, **kwargs) -> str:
        # Q&A에서만 rag_service가 호출되어 모델을 로드합니다.
        pdf_context = self.rag_service.get_relevant_context(question)
        instruction = "제공된 자료를 바탕으로 한국어로 답변하세요."
        return self._call_llama3(instruction, f"참조:\n{pdf_context}\n질문: {question}",
                                 model_version=kwargs.get('model_version', 'final'))

    def _extract_query_meta(self, text: str) -> QueryMeta:
        meta = QueryMeta()
        districts = [
            "종로구", "중구", "용산구", "성동구", "광진구", "동대문구", "중랑구", "성북구", "강북구", "도봉구",
            "노원구", "은평구", "서대문구", "마포구", "양천구", "강서구", "구로구", "금천구", "영등포구", "동작구",
            "관악구", "서초구", "강남구", "송파구", "강동구",
        ]
        for gu in districts:
            if gu in text:
                meta.district = gu
                break
        return meta

    def _build_forecast_context(self, meta: QueryMeta) -> str:
        if meta.district == "전체":
            summary = db.session.query(
                RegionForecast.year,
                func.sum(RegionForecast.predicted_child_user).label('total')
            ).filter(
                RegionForecast.year >= (meta.start_year or 2023),
                RegionForecast.year <= (meta.end_year or 2030)
            ).group_by(RegionForecast.year).all()
            return "\n".join([f"{s.year}년 합계: {s.total}명" for s in summary]) if summary else "데이터 없음"
        else:
            rows = RegionForecast.query.filter(
                RegionForecast.district == meta.district,
                RegionForecast.year >= (meta.start_year or 2023),
                RegionForecast.year <= (meta.end_year or 2030)
            ).all()
            return "\n".join([f"{r.year}년: {r.predicted_child_user}명" for r in rows]) if rows else "데이터 없음"

    def update_settings(self, settings: dict):
        self.default_settings.update(settings)


# 싱글톤 인스턴스
_genai_service_instance = None


def get_genai_service():
    global _genai_service_instance
    if _genai_service_instance is None:
        _genai_service_instance = GenAIService()
    return _genai_service_instance