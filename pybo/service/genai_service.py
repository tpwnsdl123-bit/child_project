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

# 리팩토링된 에이전트 모듈 임포트
from pybo.agent.tool_agent import ToolAgent
from pybo.agent.prompts import QA_SYSTEM_PROMPT, REPORT_SYSTEM_PROMPT, POLICY_SYSTEM_PROMPT

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
        # RAG가 필요할때만 로드 (기존 호환성 유지)
        if self._rag_service is None:
            from pybo.service.rag_service import RagService
            print("무거운 임베딩 모델 로딩 중...")
            self._rag_service = RagService()
        return self._rag_service

    @property
    def agent(self):
        # 에이전트 엔진 초기화 (LLM 콜백 전달)
        if not hasattr(self, "_agent_instance"):
            self._agent_instance = ToolAgent(llm_callback=self._call_llama3)
        return self._agent_instance

    @staticmethod
    def _ensure_meta_defaults(meta: QueryMeta, **kwargs) -> QueryMeta:
        # None이 프롬프트/DB에 섞여 들어가는 것 방지
        meta.district = kwargs.get("district", meta.district)
        meta.start_year = kwargs.get("start_year", meta.start_year or 2023)
        meta.end_year = kwargs.get("end_year", meta.end_year or 2030)
        return meta

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

    # 보고서 (Agentic AI - 에이전트 엔진에게 위임)
    def generate_report_with_data(self, user_prompt: str, **kwargs) -> str:
        district = kwargs.get("district", "전체")
        start_year = kwargs.get("start_year", 2023)
        end_year = kwargs.get("end_year", 2030)
        
        mission = (
            f"[지시상황: {district} 지역아동센터 분석 보고서 작성 임무]\n"
            f"1. db_forecast_search를 사용하여 {start_year}~{end_year}년 인구 데이터를 먼저 조회하라.\n"
            f"2. 위 데이터 수치를 바탕으로 분석하여 create_report_task 도구로 보고서를 작성하라.\n"
            "3. 인사말이나 진행 설명은 생략하고 오직 보고서의 최종 결과물만 'Final Answer:'로 제출하라."
        )
        raw_response = self.agent.run(mission, instruction=REPORT_SYSTEM_PROMPT)
        
        report_data = {
            "title": f"{district} 아동복지 데이터 분석 보고서",
            "summary": "AI 자율 분석 기반 보고서",
            "content": raw_response
        }
        return json.dumps(report_data, ensure_ascii=False)

    # 정책 아이디어 (에이전트 위임)
    def generate_policy(self, user_prompt: str, **kwargs) -> str:
        district = kwargs.get("district", "전체")
        mission = (
            f"[지시상황: {district} 지역 맞춤형 정책 제안 임무]\n"
            "**반드시 아래 순서대로 실행하십시오:**\n"
            "1단계: db_forecast_search를 호출하여 지역의 통계 트렌드를 먼저 확인하라.\n"
            "2단계: 위 통계 결과를 바탕으로 create_policy_task를 호출하여 구체적인 정책 3가지를 생성하라.\n"
            "**주의: 1단계 결과가 나오기 전에 2단계를 앞서서 진행하지 마십시오.**\n"
            "최종 결과인 정책 본문만 'Final Answer:'로 제출하십시오."
        )
        return self.agent.run(mission, instruction=POLICY_SYSTEM_PROMPT)

    # QA (에이전트 위임)
    def answer_qa_with_log(self, question: str, **kwargs) -> str:
        # 단기 메모리 (history) 관리
        if not hasattr(self, "_chat_history"):
            self._chat_history = []
            
        # 인사말 처리 (인사말일 때도 히스토리엔 남김)
        greetings = ["안녕", "반가워", "하이", "hello", "hi", "누구"]
        is_greet = any(greet in (question or "").lower() for greet in greetings) and len(question.strip()) < 15
        
        if is_greet:
            # 인삿말도 에이전트의 안정적인 루프와 언어 제어를 따르도록 수정
            answer = self.agent.run(question, instruction=QA_SYSTEM_PROMPT, history=self._chat_history)
        else:
            # 에이전트 실행 시 히스토리 및 QA 전용 프롬프트 전달
            answer = self.agent.run(question, instruction=QA_SYSTEM_PROMPT, history=self._chat_history)
        
        # 히스토리에 추가 (추론 과정 제외, 오직 질문과 결과만 저장)
        self._chat_history.append(f"Q: {question}")
        self._chat_history.append(f"A: {answer}")
        
        # 히스토리 크기 제한 (최근 3턴 정도만 유지하여 할루시네이션 방지)
        if len(self._chat_history) > 6:
            self._chat_history = self._chat_history[-6:]
            
        return answer

    # 메타 추출 (필요시 도구 내부에서 처리하거나 제거)
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


# 싱글톤 인스턴스
_genai_service_instance = None


def get_genai_service():
    global _genai_service_instance
    if _genai_service_instance is None:
        _genai_service_instance = GenAIService()
    return _genai_service_instance
