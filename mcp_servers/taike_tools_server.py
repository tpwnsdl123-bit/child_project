import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)

import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from pybo.service.rag_service import RagService
from pybo import db
from pybo.models import RegionForecast
from sqlalchemy import func


# mcp서버 (stateless + json 응답 권장 설정 패턴)
mcp = FastMCP(
    "tAIke-tools",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "localhost:*",
            "127.0.0.1:*",
            "host.docker.internal:*",
        ],
        allowed_origins=[
            "http://localhost:*",
            "http://127.0.0.1:*",
            "http://host.docker.internal:*",
        ],
    ),
)

# Runpod 호출 세션
RUNPOD_URL = os.getenv("RUNPOD_API_URL")

session = requests.Session()
retry = Retry(
    total=2,
    backoff_factor=0.6,
    status_forcelist=(429,500,502,503,504),
    allowed_methods=frozenset(["POST"]),
    raise_on_status=False,
)
adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
session.mount("http://", adapter)
session.mount("https://", adapter)

DEFAULT_TEMP = 0.3
DEFAULT_MAX_NEW_TOKENS = 512

rag = RagService()

@mcp.tool()
def rag_search(question: str) -> str:
    # "질문과 관련된 법령, 지침 근거(RAG 컨텍스트)를 반환"
    return rag.get_relevant_context(question)

@mcp.tool()
def db_forecast_search(district: str = "전체", start_year: int = 2023, end_year: int = 2030) -> str:
    """
    서울시 구별 아동 인구 예측 데이터를 조회합니다.
    :param district: 구 이름 (예: '강남구', '종로구' 등. 전체 합계는 '전체')
    :param start_year: 시작 연도 (기본 2023)
    :param end_year: 종료 연도 (기본 2030)
    """
    try:
        if district == "전체":
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
            if not summary:
                return f"{start_year}~{end_year} 기간의 전체 데이터가 없습니다."
            return "\n".join([f"{s.year}년 서울시 전체 합계: {s.total}명" for s in summary])

        rows = (
            RegionForecast.query
            .filter(
                RegionForecast.district == district,
                RegionForecast.year >= start_year,
                RegionForecast.year <= end_year
            )
            .order_by(RegionForecast.year.asc())
            .all()
        )
        if not rows:
            return f"{district}의 {start_year}~{end_year} 기간 데이터가 없습니다."
        
        result = [f"{district} 예측 데이터:"]
        result.extend([f"- {r.year}년: {r.predicted_child_user}명" for r in rows])
        return "\n".join(result)
    except Exception as e:
        return f"DB 조회 중 오류 발생: {str(e)}"

@mcp.tool()
def create_report_task(data_context: str, district: str) -> str:
    """
    수집된 통계 데이터를 바탕으로 서울시 아동복지 보고서를 작성합니다.
    :param data_context: DB 등에서 조회된 통계 데이터 텍스트
    :param district: 대상 자치구 이름
    """
    instruction = (
        "너는 서울시 아동복지 정책 전문가다. 반드시 한국어로 답해.\n"
        "제공된 데이터를 바탕으로 아래 형식을 정확히 지켜서 보고서를 작성해. (딱 3줄만, 추가 설명 금지)\n"
        "- 요약: 한 문장\n"
        "- 가능 요인: 한 문장\n"
        "- 추가 데이터: 한 문장\n"
        "※ 데이터 범위 밖은 추측하지 말고 '자료에 없음'이라고 말해."
    )
    input_text = f"지역: {district}\n데이터:\n{data_context}"
    
    # 내부적으로 llama_generate 도구의 로직을 사용하거나 호출
    return llama_generate(instruction, input_text, model_version="final", temperature=0.1)

@mcp.tool()
def create_policy_task(data_context: str, district: str) -> str:
    """
    통계 데이터를 분석하여 자치구 맞춤형 정책 아이디어 3가지를 제안합니다.
    :param data_context: DB 등에서 조회된 통계 데이터 텍스트
    :param district: 대상 자치구 이름
    """
    instruction = (
        "너는 서울시 아동복지 정책 전문가다. 반드시 한국어로 답해라.\n"
        "제공된 데이터를 바탕으로 정책 아이디어 3가지를 한 줄씩만 제시해라. 추가 설명 금지.\n"
        "형식:\n1) ...\n2) ...\n3) ...\n"
    )
    input_text = f"지역: {district}\n데이터:\n{data_context}"
    return llama_generate(instruction, input_text, model_version="final", temperature=0.3)

@mcp.tool()
def llama_generate(
    instruction: str,
    input_text: str,
    model_version: str = "final",
    temperature: float = DEFAULT_TEMP,
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
    timeout_connect:  float = 10.0,
    timeout_read: float = 180.0,
) -> str:
    # RUNPOD /generate 호출 결과 반환
    if not RUNPOD_URL:
        return "RUNPOD_API_URL이 설정되지 않았습니다."
    
    start = time.time()
    payload = {
        "instruction": instruction,
        "input": input_text,
        "model_version": model_version,
        "max_new_tokens": max_new_tokens,
        "temperature": temperature,
    }

    try:
        res = session.post(
            RUNPOD_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=(timeout_connect, timeout_read)
        )
        if not (200 <= res.status_code < 300):
            return "AI 서버 오류로 답변 생성에 실패했습니다. 잠시 후 재시도 해주세요."
        
        _elapsed = time.time() - start
        return (res.json().get("text","") or "").strip()
    
    except requests.exceptions.Timeout:
        return "AI 서버 응답이 지연되고 있습니다. 잠시 후 다시 시도해주세요."
    except requests.exceptions.RequestException:
        return "AI 서버 통신 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
    except Exception:
        return "AI 서버 처리 중 알 수 없는 오류가 발생했습니다."
    
if __name__ == "__main__":
    mcp.run(transport="streamable-http")
