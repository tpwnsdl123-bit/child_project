import requests
import json
import os
import time
from transformers import pipeline
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import Optional, Tuple

from pybo import db
from pybo.models import RegionForecast
from sqlalchemy import func

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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

        # 세션 + Retry 설정 (런포드 일시 장애에 강해짐)
        self.session = requests.Session()
        retry = Retry(
            total=2, # 최대 재시도 횟수
            backoff_factor=0.6, # 0.6s, 1.2s 형태로 증가
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["POST"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        self.default_settings = {"temperature": 0.3, "max_new_tokens": 512}

        self._summarizer = None

    @property
    def rag_service(self):
        # RAG가 필요할때만 로드
        if self._rag_service is None:
            from pybo.service.rag_service import RagService
            print("무거운 임베딩 모델 로딩 중...")
            self._rag_service = RagService()
        return self._rag_service

    @staticmethod
    def _truncate(text: str, max_chars: int = 4000) -> str:
        if not text:
            return ""
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n...(생략됨)"

    @staticmethod
    def _ensure_meta_defaults(meta: QueryMeta, **kwargs) -> QueryMeta:
        # None이 프롬프트/DB에 섞여 들어가는 것 방지
        meta.district = kwargs.get("district", meta.district)
        meta.start_year = kwargs.get("start_year", meta.start_year or 2023)
        meta.end_year = kwargs.get("end_year", meta.end_year or 2030)
        return meta

    @staticmethod
    def _looks_like_report_3lines(text: str) -> bool:
        if not text:
            return False
        # 3개 항목이 모두 존재
        return ("- 요약:" in text) and ("- 가능 요인:" in text) and ("- 추가 데이터:" in text)

    # 런포드 호출
    def _call_llama3(
        self,
        instruction: str,
        input_text: str,
        max_new_tokens: Optional[int] = None,
        model_version: str = "final",
        temperature: Optional[float] = None,
        timeout: Tuple[float, float] = (10.0, 180.0),  # (connect, read)
    ) -> str:
        start = time.time()
        headers = {"Content-Type": "application/json"}
        payload = {
            "instruction": instruction,
            "input": input_text,
            "model_version": model_version,
            "max_new_tokens": max_new_tokens or self.default_settings["max_new_tokens"],
            "temperature": temperature if temperature is not None else self.default_settings["temperature"],
        }

        try:
            response = self.session.post(self.api_url, json=payload, headers=headers, timeout=timeout)
            # raise_for_status는 Retry와 같이 쓸 때 불편해질 수 있으니 여기선 status_code로 처리
            if not (200 <= response.status_code < 300):
                print(f"[LLM ERROR] status={response.status_code}, body={response.text[:300]}")
                return "AI 서버 오류로 답변 생성에 실패했습니다. 잠시 후 다시 시도해주세요."

            elapsed = time.time() - start
            print(f"--- AI 추론 완료 (소요시간: {elapsed:.2f}초) ---")

            return (response.json().get("text", "") or "").strip()

        except requests.exceptions.Timeout:
            print("[LLM TIMEOUT] AI 서버 응답 지연")
            return "AI 서버 응답이 지연되고 있습니다. 잠시 후 다시 시도해주세요."
        except requests.exceptions.RequestException as e:
            print(f"[LLM REQUEST ERROR] {e}")
            return "AI 서버 통신 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
        except Exception as e:
            print(f"[LLM UNKNOWN ERROR] {e}")
            return "AI 서버 처리 중 알 수 없는 오류가 발생했습니다."

    # 보고서
    def generate_report_with_data(self, user_prompt: str, **kwargs) -> str:
        start_all = time.time()
        print(f"\n[로그 1] 함수 진입 완료: {time.time() - start_all:.4f}s")

        meta = self._extract_query_meta(user_prompt)
        meta = self._ensure_meta_defaults(meta, **kwargs)
        print(f"[로그 2] 메타데이터 확정 완료: {time.time() - start_all:.4f}s")

        print("[로그 3] DB 조회 시작...")
        sql_context = self._build_forecast_context(meta)
        sql_context = self._truncate(sql_context, max_chars=2500)
        print(f"[로그 4] DB 조회 및 가공 완료: {time.time() - start_all:.4f}s")

        instruction = (
            "너는 서울시 아동복지 정책 전문가다. 반드시 한국어로 답해.\n"
            "아래 형식을 정확히 지켜. (딱 3줄만, 추가 문장/설명 금지)\n"
            "- 요약: 한 문장\n"
            "- 가능 요인: 한 문장\n"
            "- 추가 데이터: 한 문장\n"
            "※ 제공된 데이터 범위 밖은 추측하지 말고 '자료에 없음'이라고 말해."
        )
        input_text = (
            f"지역:{meta.district}\n"
            f"기간:{meta.start_year}-{meta.end_year}\n"
            f"데이터:\n{sql_context}\n\n"
            f"사용자 요청:{user_prompt}"
        )

        print(f"[로그 5] 런포드 요청 직전: {time.time() - start_all:.4f}s")
        raw_response = self._call_llama3(
            instruction,
            input_text,
            max_new_tokens=kwargs.get("max_new_tokens", 512),
            model_version=kwargs.get("model_version", "final"),
        )
        print(f"[로그 6] 런포드 응답 수신 완료: {time.time() - start_all:.4f}s")

        # 형식이 깨지면 1회만 재시도(temperature=0으로 고정해서 안정화)
        if not self._looks_like_report_3lines(raw_response):
            retry_instruction = (
                "너는 서울시 아동복지 정책 전문가다. 반드시 한국어로 답해.\n"
                "반드시 아래 3줄만 출력해. 다른 문장/머리말/끝맺음/공백 추가 금지.\n"
                "- 요약: 한 문장\n"
                "- 가능 요인: 한 문장\n"
                "- 추가 데이터: 한 문장\n"
                "※ 제공된 데이터 범위 밖은 추측하지 말고 '자료에 없음'이라고 말해."
            )
            raw_response = self._call_llama3(
                retry_instruction,
                input_text,
                max_new_tokens=256,
                model_version=kwargs.get("model_version", "final"),
                temperature=0.0,
            )

        report_data = {
            "title": f"{meta.district} 지역아동센터 수요 분석",
            "summary": "분석 완료",
            "content": raw_response
        }

        # "- 요약:" 기준으로 summary 추출 (형식 깨져도 최대한 안전하게)
        if "- 요약:" in raw_response:
            try:
                summary_part = raw_response.split("- 요약:")[1]
                report_data["summary"] = summary_part.split("- 가능 요인:")[0].strip()
            except Exception:
                pass

        return json.dumps(report_data, ensure_ascii=False)

    # 정책 아이디어
    def generate_policy(self, user_prompt: str, **kwargs) -> str:
        meta = self._extract_query_meta(user_prompt)
        meta = self._ensure_meta_defaults(meta, **kwargs)

        sql_context = self._build_forecast_context(meta)
        sql_context = self._truncate(sql_context, max_chars=2000)

        instruction = (
            "너는 서울시 아동복지 정책 전문가다. 반드시 한국어로 답해라.\n"
            "제공된 지역별 수요 예측 데이터를 바탕으로 정책 아이디어 3가지를 한 줄씩만 제시해라. 추가 설명 금지.\n"
            "자료 밖은 추측하지 말고 '자료에 없음'이라고 말해.\n"
            "형식:\n"
            "1) ...\n"
            "2) ...\n"
            "3) ...\n"
        )

        input_text = f"지역: {meta.district}\n기간:{meta.start_year}-{meta.end_year}\n예측 데이터:\n{sql_context}\n\n사용자 요청: {user_prompt}"

        return self._call_llama3(
            instruction,
            input_text,
            max_new_tokens=kwargs.get("max_new_tokens", 256),
            model_version=kwargs.get("model_version", "final"),
        )

    # QA (RAG + DB)
    def answer_qa_with_log(self, question: str, **kwargs) -> str:
        greetings = ["안녕", "반가워", "하이", "hello", "hi", "누구"]
        q_low = (question or "").lower()
        is_greeting = any(greet in q_low for greet in greetings) and len((question or "").strip()) < 15

        if is_greeting:
            instruction = (
                "너는 서울시 아동복지 정책 전문가이자 친절한 상담사야. "
                "사용자의 인사에 반갑게 화답하고 무엇을 도와줄지 짧고 친절하게 물어봐."
            )
            return self._call_llama3(
                instruction,
                f"사용자 질문: {question}",
                model_version=kwargs.get("model_version", "final")
            )

        # RAG + DB
        pdf_context = self.rag_service.get_relevant_context(question)
        pdf_context = self._truncate(pdf_context, max_chars=3500)

        meta = self._extract_query_meta(question)
        meta = self._ensure_meta_defaults(meta, **kwargs)
        sql_context = self._build_forecast_context(meta) if meta.district != "전체" else ""
        sql_context = self._truncate(sql_context, max_chars=2000)

        combined_context = (
            f"법령 및 지침 자료:\n{pdf_context}\n\n"
            f"실제 통계 데이터:\n{sql_context}"
        )

        instruction = (
            "너는 서울시 아동복지 정책 전문가다. 반드시 한국어로 답변해라. "
            "반드시 제공된 '참조 자료'에 근거해서만 답해라. "
            "참조 자료에 없는 내용은 추측하지 말고 '자료에 없음'이라고 말해라. "
            "질문과 직접 관련 없는 법령/지침은 생략해라. "
            "상담사처럼 친절한 말투(~해요, ~입니다)를 사용해라."
        )

        return self._call_llama3(
            instruction,
            f"참조 자료:\n{combined_context}\n\n질문: {question}",
            model_version=kwargs.get("model_version", "final")
        )

    # 메타 추출
    def _extract_query_meta(self, text: str) -> QueryMeta:
        meta = QueryMeta()
        districts = [
            "종로구", "중구", "용산구", "성동구", "광진구", "동대문구", "중랑구", "성북구", "강북구", "도봉구",
            "노원구", "은평구", "서대문구", "마포구", "양천구", "강서구", "구로구", "금천구", "영등포구", "동작구",
            "관악구", "서초구", "강남구", "송파구", "강동구",
        ]
        for gu in districts:
            if gu in (text or ""):
                meta.district = gu
                break
        return meta

    # DB 컨텍스트
    def _build_forecast_context(self, meta: QueryMeta) -> str:
        start_year = meta.start_year or 2023
        end_year = meta.end_year or 2030

        if meta.district == "전체":
            summary = (
                db.session.query(
                    RegionForecast.year,
                    func.sum(RegionForecast.predicted_child_user).label("total")
                )
                .filter(
                    RegionForecast.year >= start_year,
                    RegionForecast.year <= end_year
                )
                .group_by(RegionForecast.year)
                .order_by(RegionForecast.year.asc())
                .all()
            )
            return "\n".join([f"{s.year}년 합계: {s.total}명" for s in summary]) if summary else "데이터 없음"

        rows = (
            RegionForecast.query
            .filter(
                RegionForecast.district == meta.district,
                RegionForecast.year >= start_year,
                RegionForecast.year <= end_year
            )
            .order_by(RegionForecast.year.asc())
            .all()
        )
        return "\n".join([f"{r.year}년: {r.predicted_child_user}명" for r in rows]) if rows else "데이터 없음"

    def update_settings(self, settings: dict):
        # max_tokens 키 혼동 방지: max_new_tokens로 통일
        if "max_tokens" in settings and "max_new_tokens" not in settings:
            settings["max_new_tokens"] = settings.pop("max_tokens")
        self.default_settings.update(settings)

    # 텍스트 요약
    def summarize_text(self, text: str) -> str:
        if self._summarizer is None:
            print("경량 요약 모델(KoBART) 로딩 중...")
            self._summarizer = pipeline("summarization", model="digit82/kobart-summarization")

        try:
            result = self._summarizer(text, max_length=300, min_length=10, do_sample=False)
            return result[0]["summary_text"]
        except Exception as e:
            print(f"[SUMMARIZE ERROR] {e}")
            return "요약 중 오류가 발생했습니다."


# 싱글톤 인스턴스
_genai_service_instance = None


def get_genai_service():
    global _genai_service_instance
    if _genai_service_instance is None:
        _genai_service_instance = GenAIService()
    return _genai_service_instance
