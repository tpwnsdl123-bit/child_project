import requests
import json
import re
from dataclasses import dataclass
from typing import Optional

from pybo import db
from pybo.models import GenAIChatLog, RegionForecast

DISTRICTS = [
    "종로구", "중구", "용산구", "성동구", "광진구", "동대문구", "중랑구", "성북구", "강북구", "도봉구",
    "노원구", "은평구", "서대문구", "마포구", "양천구", "강서구", "구로구", "금천구", "영등포구", "동작구",
    "관악구", "서초구", "강남구", "송파구", "강동구", ]

INDICATOR_MAP = {
    "한부모": ("single_parent", "한부모 가구 수"),
    "한부모 가구": ("single_parent", "한부모 가구 수"),
    "기초생활": ("basic_beneficiaries", "기초생활수급자 수"),
    "기초생활수급": ("basic_beneficiaries", "기초생활수급자 수"),
    "다문화": ("multicultural_hh", "다문화 가구 수"),
    "다문화 가구": ("multicultural_hh", "다문화 가구 수"),
    "학원": ("academy_cnt", "학원 수"),
    "학원 수": ("academy_cnt", "학원 수"),
    "grdp": ("grdp", "1인당 GRDP"),
    "소득": ("grdp", "1인당 GRDP"),
    "인구": ("population", "자치구 인구수"),
    "인구 수": ("population", "자치구 인구수"), }


@dataclass
class QueryMeta:
    district: str = "전체"
    start_year: Optional[int] = None
    end_year: Optional[int] = None


class GenAIService:

    def __init__(self) -> None:
        # [중요] RunPod 서버 주소 설정
        # RunPod 대시보드 Connect -> TCP Port 8000 주소 복사 후 /generate 붙이기
        self.api_url = "https://1vfjvse5cp5zsj-8000.proxy.runpod.net/generate"

        # 타임아웃 설정 (Llama 3 생성 시간 고려 넉넉하게)
        self.timeout = 60

    # RunPod 통신 함수
    def _call_llama3(self, instruction: str, input_text: str, max_tokens: int = 512) -> str:
        headers = {'Content-Type': 'application/json'}
        payload = {
            "instruction": instruction,
            "input": input_text,
            "max_new_tokens": max_tokens,
            "temperature": 0.35  # 여기도 0.35로 맞춰주세요
        }

        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()

            result = response.json()
            raw_text = result.get("text", "").strip()

            # 한글, 영어, 숫자, 기본 기호 빼고 싹 다 지워버리기
            # 정규표현식: "가-힣(한글)", "a-zA-Z(영어)", "0-9(숫자)", "\s(공백)", ".,%()~-+(기호)" 가 아닌 것은 삭제
            clean_text = re.sub(r'[^가-힣a-zA-Z0-9\s.,%()~:+-]', '', raw_text)

            # 다 지워져서 이상해질 수 있으니 연속된 공백 정리
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()

            return clean_text

        except Exception as e:
            print(f"RunPod Error: {e}")
            return "죄송합니다. AI 서버와 연결할 수 없습니다."

    # 메타 추출 로직
    def _extract_query_meta(self, text: str) -> QueryMeta:
        q = (text or "").strip()
        meta = QueryMeta()
        for gu in DISTRICTS:
            if gu in q:
                meta.district = gu
                break
        range_pattern = r"(20\d{2})\s*[-~]\s*(20\d{2})"
        m = re.search(range_pattern, q)
        if m:
            y1, y2 = int(m.group(1)), int(m.group(2))
            meta.start_year = min(y1, y2)
            meta.end_year = max(y1, y2)
        else:
            single_pattern = r"(20\d{2})\s*년?"
            m2 = re.search(single_pattern, q)
            if m2:
                y = int(m2.group(1))
                meta.start_year = y
                meta.end_year = y
        if meta.start_year is not None and meta.end_year is not None:
            if meta.start_year < 2015: meta.start_year = 2015
            if meta.end_year > 2030: meta.end_year = 2030
            if meta.start_year > meta.end_year: meta.start_year, meta.end_year = meta.end_year, meta.start_year
        return meta

    def _build_meta_with_overrides(self, text: str, *, district: str | None, start_year: int | None,
                                   end_year: int | None) -> QueryMeta:
        meta = self._extract_query_meta(text)
        if district: meta.district = district.strip()
        if start_year is not None: meta.start_year = int(start_year)
        if end_year is not None: meta.end_year = int(end_year)
        return meta

    def _detect_indicator(self, text: str) -> tuple[Optional[str], Optional[str]]:
        q = (text or "").strip().lower()
        for keyword, (col, label) in INDICATOR_MAP.items():
            if keyword.lower() in q: return col, label
        return None, None

    def _format_change(self, start, end) -> str:
        if start is None or end is None: return "데이터 없음"
        try:
            s, e = float(start), float(end)
        except:
            return f"{start} → {end}"
        base = f"{int(round(s)):,} → {int(round(e)):,}"
        if s == 0: return base
        try:
            diff = (e - s) / s * 100.0
        except:
            return base
        sign = "+" if diff >= 0 else ""
        return f"{base} (약 {sign}{diff:.1f}%)"

    def _save_chat_log(self, *, user_id, page, task_type, question, answer) -> None:
        log = GenAIChatLog(user_id=user_id, page=page, task_type=task_type, question=question, answer=answer)
        db.session.add(log)
        db.session.commit()

    def _query_forecast_rows(self, district: str, start_year: int, end_year: int) -> list[RegionForecast]:
        return RegionForecast.query.filter(
            RegionForecast.district == district,
            RegionForecast.year >= start_year,
            RegionForecast.year <= end_year
        ).order_by(RegionForecast.year.asc()).all()

    #  보고서 탭 (RunPod 호출)
    def generate_report_with_data(self, user_prompt: str, *, district: str | None = None, start_year: int | None = None,
                                  end_year: int | None = None) -> str:
        user_prompt = (user_prompt or "").strip()
        meta = self._build_meta_with_overrides(user_prompt, district=district, start_year=start_year, end_year=end_year)

        # DB 데이터 가져오기
        context = self._build_forecast_context(meta)

        # 시스템 프롬프트 (RunPod의 instruction으로 보냄)
        instruction = (
            "너는 서울시 아동 돌봄 정책 전문 데이터 분석가야. "
            "아래 [예측 데이터 요약]을 바탕으로 정책 담당자용 보고서를 작성해. "
            "반드시 아래 [작성 예시]의 말투와 논리 구조를 벤치마킹해서 작성해.\n\n"

            "[작성 예시]\n"
            "1. 현황 분석:\n"
            "이용자 수는 완만히 감소하는 반면, 취약계층 관련 지표는 상승하는 흐름이 관찰된다. "
            "이는 돌봄 필요 계층은 늘어나지만 실제 이용으로 이어지지 않는 '수급 불균형' 가능성을 시사한다.\n"
            "2. 원인 추정:\n"
            "아동 인구 감소가 이용자 수 감소의 주된 원인으로 보인다. "
            "하지만 기초생활수급자 비율 상승에도 불구하고 이용자가 줄어드는 것은, 센터의 접근성이 떨어지거나 "
            "학원 등 민간 대체 서비스로 수요가 이동했을 가능성이 있다.\n"
            "3. 정책 제언:\n"
            "취약계층의 이용 접근성을 높이기 위해 야간/긴급 돌봄 서비스를 확대할 필요가 있다. "
            "또한, 단순 학습 지도보다는 지역 특성에 맞는 특화 프로그램을 도입하여 민간 학원과의 차별성을 확보해야 한다.\n\n"

            "[작성 규칙]\n"
            "- 위 예시처럼 '평서문(~한다, ~이다)'으로 간결하게 작성할 것.\n"
            "- '프리아일랜드', '기계로 하는' 같은 없는 단어나 번역투 문장을 절대 쓰지 말 것.\n"
            "- 수치 증감(%)을 근거로 들 것."
        )

        # 입력 데이터 구성 (Context + User Prompt)
        input_text = f"{context}\n\n[사용자 요청]: {user_prompt}"

        # RunPod 호출
        return self._call_llama3(instruction, input_text, max_tokens=500)

    # 정책 탭 (RunPod 호출)
    def generate_policy(self, prompt: str, *, district: str | None = None, start_year: int | None = None,
                        end_year: int | None = None) -> str:
        user_prompt = (prompt or "").strip()
        meta = self._build_meta_with_overrides(user_prompt, district=district, start_year=start_year, end_year=end_year)
        context = self._build_forecast_context(meta)

        instruction = (
            "너는 서울시 지역아동센터 관련 정책을 기획하는 보조자야. "
            "제공된 데이터를 바탕으로 현실적인 돌봄·지원 정책 아이디어를 3개 제안해 줘. "
            "각 아이디어는 번호를 붙여서 설명해."
        )

        input_text = f"{context}\n\n[사용자 요청]: {user_prompt}"

        return self._call_llama3(instruction, input_text, max_tokens=400)

    # 지표 설명 탭 (RunPod 호출)
    def explain_indicator(self, prompt: str, *, district: str | None = None, start_year: int | None = None,
                          end_year: int | None = None) -> str:
        user_prompt = (prompt or "").strip()
        indicator_col, indicator_label = self._detect_indicator(user_prompt)
        meta = self._build_meta_with_overrides(user_prompt, district=district, start_year=start_year, end_year=end_year)

        if not indicator_col:
            instruction = "너는 데이터 분석가야. 사용자가 묻는 지표의 통계적 의미를 쉽게 설명해 줘."
            input_text = f"질문: {user_prompt}"
            return self._call_llama3(instruction, input_text)

        context = self._build_indicator_context(meta, indicator_col, indicator_label)

        instruction = (
            "너는 데이터 분석가야. 제공된 지표 데이터와 돌봄 수요 간의 상관관계를 "
            "비전문가도 이해하기 쉽게 설명해 줘."
        )
        input_text = f"{context}\n\n질문: {user_prompt}"

        return self._call_llama3(instruction, input_text)

    def analyze_ner(self, text: str) -> list[dict]:
        # NER 라이브러리를 지웠으므로 임시 비활성화
        return []

        # Q&A 탭 (RunPod 호출)
    def answer_qa(self, question: str, *, district: str | None = None, start_year: int | None = None,
                  end_year: int | None = None) -> str:
        user_q = (question or "").strip()
        meta = self._build_meta_with_overrides(user_q, district=district, start_year=start_year, end_year=end_year)
        context = self._build_forecast_context(meta)

        instruction = (
            "너는 서울시 아동 정책 Q&A 봇이야. 예측 데이터를 근거로 질문에 답변해 줘. "
            "정확한 수치를 모르면 경향성 위주로 설명해."
        )
        input_text = f"{context}\n\n질문: {user_q}"

        return self._call_llama3(instruction, input_text)

    def answer_qa_with_log(self, question: str, *, user_id: int | None = None, page: str | None = None,
                           district: str | None = None, start_year: int | None = None,
                           end_year: int | None = None) -> str:
        answer = self.answer_qa(question, district=district, start_year=start_year, end_year=end_year)
        self._save_chat_log(user_id=user_id, page=page, task_type="qa", question=question, answer=answer)
        return answer

    # 컨텍스트 빌더들
    def _build_forecast_context(self, meta: QueryMeta) -> str:
        district = (meta.district or "").strip()
        if not district or district == "전체": return ""
        start_year = meta.start_year if meta.start_year is not None else 2023
        end_year = meta.end_year if meta.end_year is not None else 2030
        rows = self._query_forecast_rows(district, start_year, end_year)
        if not rows: return ""

        lines_predict = []
        for r in rows:
            try:
                val_str = f"{int(round(r.predicted_child_user)):,}"
            except:
                val_str = str(r.predicted_child_user)
            lines_predict.append(f"- {r.year}년: 약 {val_str}명")

        first, last = rows[0], rows[-1]

        def get_attr_safe(obj, name):
            return getattr(obj, name, None)

        feature_summaries = [
            f"예측 이용자 수: {self._format_change(first.predicted_child_user, last.predicted_child_user)}",
            f"한부모 가구 수: {self._format_change(get_attr_safe(first, 'single_parent'), get_attr_safe(last, 'single_parent'))}",
            f"기초생활수급자 수: {self._format_change(get_attr_safe(first, 'basic_beneficiaries'), get_attr_safe(last, 'basic_beneficiaries'))}",
            f"다문화 가구 수: {self._format_change(get_attr_safe(first, 'multicultural_hh'), get_attr_safe(last, 'multicultural_hh'))}",
            f"학원 수: {self._format_change(get_attr_safe(first, 'academy_cnt'), get_attr_safe(last, 'academy_cnt'))}",
            f"1인당 GRDP: {self._format_change(get_attr_safe(first, 'grdp'), get_attr_safe(last, 'grdp'))}",
            f"자치구 인구수: {self._format_change(get_attr_safe(first, 'population'), get_attr_safe(last, 'population'))}"
        ]

        context_lines = [
            "[예측 데이터 요약]", f"자치구: {district}", f"연도 범위: {start_year}년 ~ {end_year}년", "",
            "연도별 지역아동센터 예측 이용자 수:", *lines_predict, "",
            "주요 지표 변화:", *[f"- {fs}" for fs in feature_summaries], "[예측 데이터 요약 끝]"
        ]
        return "\n".join(context_lines) + "\n\n"

    def _build_indicator_context(self, meta: QueryMeta, indicator_col: str, indicator_label: str) -> str:
        district = (meta.district or "").strip()
        if not district or district == "전체": return ""
        start_year = meta.start_year if meta.start_year is not None else 2023
        end_year = meta.end_year if meta.end_year is not None else 2030
        rows = self._query_forecast_rows(district, start_year, end_year)
        if not rows: return ""
        first, last = rows[0], rows[-1]

        def get_attr_safe(obj, name):
            return getattr(obj, name, None)

        indicator_change = self._format_change(get_attr_safe(first, indicator_col), get_attr_safe(last, indicator_col))
        user_change = self._format_change(getattr(first, "predicted_child_user", None),
                                          getattr(last, "predicted_child_user", None))

        lines = [
            "[지표 및 예측 데이터 요약]", f"자치구: {district}", f"연도 범위: {start_year}년 ~ {end_year}년", "",
            f"{indicator_label} 변화: {indicator_change}", f"예측 이용자 수 변화: {user_change}", "[지표 및 예측 데이터 요약 끝]"
        ]
        return "\n".join(lines) + "\n\n"