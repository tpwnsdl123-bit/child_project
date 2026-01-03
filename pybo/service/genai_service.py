import requests
import json
import os
import time
from transformers import pipeline
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
        self.default_settings = {"temperature": 0.3, "max_tokens": 512}
        self._summarizer = None

    @property
    def rag_service(self):
        # RAG가 필요할때만 로드
        if self._rag_service is None:
            from pybo.service.rag_service import RagService
            print("무거운 임베딩 모델 로딩 중...")
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

        print(f"[로그 3] DB 조회 시작...")  #
        sql_context = self._build_forecast_context(meta)
        print(f"[로그 4] DB 조회 및 가공 완료: {time.time() - start_all:.4f}s")  #

        instruction = (
            "너는 서울시 아동복지 정책 전문가다. 반드시 한국어로 답해.\n"
            "아래 형식을 정확히 지켜. (딱 3줄만, 추가 문장/설명 금지)\n"
            "- 요약: 한 문장\n"
            "- 가능 요인: 한 문장\n"
            "- 추가 데이터: 한 문장\n"
        )
        input_text = f"지역:{meta.district}\n기간:{meta.start_year}-{meta.end_year}\n데이터:\n{sql_context}"

        print(f"[로그 5] 런포드 요청 직전: {time.time() - start_all:.4f}s")  #

        raw_response = self._call_llama3(
            instruction,
            input_text,
            max_tokens=512,
            model_version=kwargs.get('model_version', 'final')
        )
        print(f"[로그 6] 런포드 응답 수신 완료: {time.time() - start_all:.4f}s")  #
        report_data = {
            "title": f"{meta.district} 지역아동센터 수요 분석",
            "summary": "분석 완료",
            "content": raw_response
        }

        # split("-") 대신 다음 항목 키워드로 자르기
        if "- 요약:" in raw_response:
            try:
                summary_part = raw_response.split("- 요약:")[1]
                # '가능 요인' 항목 전까지만 가져옵니다.
                report_data["summary"] = summary_part.split("- 가능 요인:")[0].strip()
            except:
                pass
        return json.dumps(report_data, ensure_ascii=False)

    def generate_policy(self, user_prompt: str, **kwargs) -> str:
        # 질문에서 지역 및 연도 정보 추출
        meta = self._extract_query_meta(user_prompt)
        meta.district = kwargs.get('district', meta.district)
        
        # SQL DB에서 해당 지역의 예측 수치 조회
        sql_context = self._build_forecast_context(meta)
        
        instruction = (
            "너는 서울시 아동복지 정책 전문가다. 반드시 한국어로 답해라.\n"
            "제공된 지역별 수요 예측 데이터를 바탕으로 정책 아이디어 3가지를 한 줄씩만 제시해라. 추가 설명 금지.\n"
            "형식:\n"
            "1) ...\n"
            "2) ...\n"
            "3) ...\n"
        )
        
        # 사용자 질문과 DB 데이터를 함께 입력값으로 구성
        input_text = f"지역: {meta.district}\n예측 데이터:\n{sql_context}\n\n사용자 요청: {user_prompt}"
        
        return self._call_llama3(
            instruction, 
            input_text, 
            max_tokens=256, 
            model_version=kwargs.get('model_version', 'final')
        )

    def answer_qa_with_log(self, question: str, **kwargs) -> str:
        # 간단한 인사말인지 확인
        greetings = ["안녕", "반가워", "하이", "hello", "hi", "누구"]
        is_greeting = any(greet in question.lower() for greet in greetings) and len(question.strip()) < 10

        if is_greeting:
            # 인사말인 경우 RAG와 DB 조회를 건너뛰고 바로 응답
            instruction = "너는 서울시 아동복지 정책 전문가이자 친절한 상담사야. 사용자의 인사에 반갑게 화답하고 무엇을 도와줄지 짧고 친절하게 물어봐."
            return self._call_llama3(instruction, f"사용자 질문: {question}", 
                                     model_version=kwargs.get('model_version', 'final'))

        # 일반 질문인 경우 기존 로직 수행 (RAG + DB)
        pdf_context = self.rag_service.get_relevant_context(question)
        meta = self._extract_query_meta(question)
        sql_context = self._build_forecast_context(meta) if meta.district != "전체" else ""

        combined_context = f"법령 및 지침 자료:\n{pdf_context}\n\n실제 통계 데이터:\n{sql_context}"
        
        instruction = (
            "너는 서울시 아동복지 정책 전문가다. 반드시 한국어로 답변해라. "
            "제공된 자료에 근거하여 답변하되, 질문과 직접적인 관련이 없는 법령은 생략하고 "
            "상담사처럼 친절한 말투(~해요, ~입니다)를 사용해라."
        )

        return self._call_llama3(
            instruction, 
            f"참조 자료:\n{combined_context}\n질문: {question}",
            model_version=kwargs.get('model_version', 'final')
        )

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
    
    # 텍스트 요약
    def summarize_text(self, text: str) -> str:
        # 요약 모델 지연 로딩
        if self._summarizer is None:
            print("경량 요약 모델(KoBART) 로딩 중...")
            self._summarizer = pipeline("summarization", model="digit82/kobart-summarization")

        try:
            # 요약 수행 (최대 길이는 300자로 제한)
            result = self._summarizer(text, max_length=300, min_length=10, do_sample=False)
            return result[0]['summary_text']
        except Exception as e:
            return f"요약 중 오류가 발생했습니다: {e}"

# 싱글톤 인스턴스
_genai_service_instance = None


def get_genai_service():
    global _genai_service_instance
    if _genai_service_instance is None:
        _genai_service_instance = GenAIService()
    return _genai_service_instance