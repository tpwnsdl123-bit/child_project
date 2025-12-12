from transformers import pipeline
import torch

from pybo import db
from pybo.models import GenAIChatLog, RegionForecast

import re
from dataclasses import dataclass
from typing import Optional

DISTRICTS = [
    "종로구", "중구", "용산구", "성동구", "광진구", "동대문구", "중랑구", "성북구", "강북구", "도봉구",
    "노원구", "은평구", "서대문구", "마포구", "양천구", "강서구", "구로구", "금천구", "영등포구", "동작구",
    "관악구", "서초구", "강남구", "송파구", "강동구",]

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
    "인구 수": ("population", "자치구 인구수"),}

@dataclass
class QueryMeta: # 자연어 질의에서 추출한 메타 정보
    district: str = "전체"
    start_year: Optional[int] = None
    end_year: Optional[int] = None

# 생성형 AI 기능 모아둔 클래스
class GenAIService:

    def __init__(self) -> None:
        # GPU 있으면 0, 없으면 CPU(-1)
        device = 0 if torch.cuda.is_available() else -1

        # 텍스트 생성 파이프라인 (라마3로 교체 예정)
        self.report_generator = pipeline(
            "text-generation",
            model="skt/kogpt2-base-v2",
            tokenizer="skt/kogpt2-base-v2",
            device=device,
        )

        # NER 파이프라인
        self.ner_pipeline = pipeline(
            "ner",
            model="Davlan/bert-base-multilingual-cased-ner-hrl",
            tokenizer="Davlan/bert-base-multilingual-cased-ner-hrl",
            aggregation_strategy="simple",
            device=device,
        )

    # 메타/지표 관련 함수
    def _extract_query_meta(self, text: str) -> QueryMeta:
        q = (text or "").strip()
        meta = QueryMeta()

        # 자치구 찾기
        for gu in DISTRICTS:
            if gu in q:
                meta.district = gu
                break  # 첫 번째 매칭만 사용

        # 연도 범위
        range_pattern = r"(20\d{2})\s*[-~]\s*(20\d{2})"
        m = re.search(range_pattern, q)
        if m:
            y1 = int(m.group(1))
            y2 = int(m.group(2))
            meta.start_year = min(y1, y2)
            meta.end_year = max(y1, y2)
        else:
            # 단일 연도
            single_pattern = r"(20\d{2})\s*년?"
            m2 = re.search(single_pattern, q)
            if m2:
                y = int(m2.group(1))
                meta.start_year = y
                meta.end_year = y

        # 연도 2015~2030 범위로 제한
        if meta.start_year is not None and meta.end_year is not None:
            if meta.start_year < 2015:
                meta.start_year = 2015
            if meta.end_year > 2030:
                meta.end_year = 2030
            if meta.start_year > meta.end_year:
                meta.start_year, meta.end_year = meta.end_year, meta.start_year

        return meta

    def _build_meta_with_overrides(
        self,
        text: str,
        *,
        district: str | None,
        start_year: int | None,
        end_year: int | None,
    ) -> QueryMeta:
        meta = self._extract_query_meta(text)

        if district:
            meta.district = district.strip()
        if start_year is not None:
            meta.start_year = int(start_year)
        if end_year is not None:
            meta.end_year = int(end_year)

        return meta

    # 어떨 지표를 묻는지 추출
    def _detect_indicator(self, text: str) -> tuple[Optional[str], Optional[str]]:
        q = (text or "").strip().lower()
        for keyword, (col, label) in INDICATOR_MAP.items():
            if keyword.lower() in q:
                return col, label
        return None, None

    # 공통 유틸

    # 숫자를 받아서 A -> B (약 +C%) 문자열로 반환
    def _format_change(self, start, end) -> str:
        if start is None or end is None:
            return "데이터 없음"

        try:
            s = float(start)
            e = float(end)
        except Exception:
            return f"{start} → {end}"

        base = f"{int(round(s)):,} → {int(round(e)):,}"

        if s == 0:
            return base

        try:
            diff_ratio = (e - s) / s * 100.0
        except Exception:
            return base

        sign = "+" if diff_ratio >= 0 else ""
        return f"{base} (약 {sign}{diff_ratio:.1f}%)"

    # 질의응답 받은걸 DB저장
    def _save_chat_log(
        self,
        *,
        user_id: int | None,
        page: str | None,
        task_type: str,
        question: str,
        answer: str,
    ) -> None:

        log = GenAIChatLog(
            user_id=user_id,
            page=page,
            task_type=task_type,
            question=question,
            answer=answer,
        )
        db.session.add(log)
        db.session.commit()

    # DB에서 자치구,연도 범위로 조회
    def _query_forecast_rows(self, district: str, start_year: int, end_year: int) -> list[RegionForecast]:
        return (
            RegionForecast.query
            .filter(
                RegionForecast.district == district,
                RegionForecast.year >= start_year,
                RegionForecast.year <= end_year,
            )
            .order_by(RegionForecast.year.asc())
            .all()
        )

    # 보고서 탭
    def generate_report_with_data(
        self,
        user_prompt: str,
        *,
        district: str | None = None,
        start_year: int | None = None,
        end_year: int | None = None,
    ) -> str:

        user_prompt = (user_prompt or "").strip()

        # 메타 생성
        meta = self._build_meta_with_overrides(
            user_prompt,
            district=district,
            start_year=start_year,
            end_year=end_year,
        )

        # DB에서 예측/피처 요약 만들기
        context = self._build_forecast_context(meta)

        system_prefix = (
            "너는 서울시 지역아동센터 수요 예측 결과를 정책 담당자에게 설명하는 데이터 분석가야. "
            "핵심만 3~6문장 정도의 한국어 단락으로 정리해 줘. "
            "가능하다면 위에 제공된 예측 데이터 요약을 참고해서, "
            "연도별 증가/감소 추세와 정책적 시사점을 같이 설명해 줘."
        )

        full_prompt = ""
        if context:
            full_prompt += context + "\n"

        full_prompt += f"{system_prefix}\n\n요청: {user_prompt}\n\n보고서:"

        outputs = self.report_generator(
            full_prompt,
            max_new_tokens=256,
            do_sample=True,
            top_p=0.95,
            temperature=0.7,
            num_return_sequences=1,
            pad_token_id=self.report_generator.tokenizer.eos_token_id,
        )

        generated = outputs[0]["generated_text"]

        if generated.startswith(full_prompt):
            generated = generated[len(full_prompt):]

        return generated.strip()

    # 정책 탭
    def generate_policy(
        self,
        prompt: str,
        *,
        district: str | None = None,
        start_year: int | None = None,
        end_year: int | None = None,
    ) -> str:
        user_prompt = (prompt or "").strip()

        meta = self._build_meta_with_overrides(
            user_prompt,
            district=district,
            start_year=start_year,
            end_year=end_year,
        )

        context = self._build_forecast_context(meta)

        system_prefix = (
            "너는 서울시 지역아동센터 관련 정책을 기획하는 보조자야. "
            "아래에 제공된 예측 데이터 요약과 사용자 요청을 참고해서, "
            "현실적인 돌봄·지원 정책 아이디어를 한국어로 제안해 줘. "
            "각 아이디어는 번호를 붙여서 3개 정도로 정리해 줘. "
            "입력 문장을 그대로 반복하지 말고, 새로운 문장으로만 아이디어를 작성해. "
            "정확한 통계 수치는 모르면 새로 지어내지 말고, "
            "'통계 수치는 별도 통계 참고 필요'라고 말해."
        )

        full_prompt = ""
        if context:
            full_prompt += context + "\n"

        full_prompt += (
            f"{system_prefix}\n\n"
            f"[사용자 요청]\n{user_prompt}\n\n"
            "정책 아이디어:\n"
        )

        outputs = self.report_generator(
            full_prompt,
            max_length=256,
            do_sample=True,
            top_p=0.9,
            temperature=0.6,
            num_return_sequences=1,
            pad_token_id=self.report_generator.tokenizer.eos_token_id,
        )

        generated = outputs[0]["generated_text"]
        if generated.startswith(full_prompt):
            generated = generated[len(full_prompt):]

        return generated.strip()

    # 지표 설명 탭
    def explain_indicator(
        self,
        prompt: str,
        *,
        district: str | None = None,
        start_year: int | None = None,
        end_year: int | None = None,
    ) -> str:
        user_prompt = (prompt or "").strip()

        # 어떤 지표를 묻는지 감지
        indicator_col, indicator_label = self._detect_indicator(user_prompt)

        # 메타 생성
        meta = self._build_meta_with_overrides(
            user_prompt,
            district=district,
            start_year=start_year,
            end_year=end_year,
        )

        # 지표를 못 찾으면: 기존 방식(개념 설명만)
        if not indicator_col:
            system_prefix = (
                "너는 서울시 지역아동센터 수요 예측 모델에 들어가는 지표를 설명하는 데이터 분석가야. "
                "입력된 지표 이름이나 질문에 대해, "
                "지표의 의미와 해석 방법, 그리고 돌봄 수요와 어떤 관련이 있을 수 있는지를 "
                "3~6문장 정도의 한국어 단락으로 쉽게 설명해 줘. "
                "너무 어려운 통계 용어는 풀어서 설명해."
            )

            full_prompt = (
                f"{system_prefix}\n\n"
                f"질문:\n{user_prompt}\n\n"
                "설명:\n"
            )

            outputs = self.report_generator(
                full_prompt,
                max_length=512,
                do_sample=True,
                top_p=0.9,
                temperature=0.7,
                num_return_sequences=1,
                pad_token_id=self.report_generator.tokenizer.eos_token_id,
            )

            generated = outputs[0]["generated_text"]
            if generated.startswith(full_prompt):
                generated = generated[len(full_prompt):]
            return generated.strip()

        # 지표 인식된 경우: 해당 지표 + 예측 이용자 수 변화를 컨텍스트로 붙임
        context = self._build_indicator_context(meta, indicator_col, indicator_label)

        system_prefix = (
            "너는 서울시 지역아동센터 수요 예측 모델에 들어가는 지표를 설명하는 데이터 분석가야. "
            "위에 제공된 지표 및 예측 데이터 요약과 아래 질문을 참고해서, "
            "해당 지표의 의미, 해석 방법, 그리고 돌봄 수요와의 관련성을 설명해 줘. "
            "너무 어려운 통계 용어는 풀어서 쉽게 설명하고, "
            "3~6문장 정도의 한국어 단락으로 답해."
        )

        full_prompt = ""
        if context:
            full_prompt += context + "\n"

        full_prompt += (
            f"{system_prefix}\n\n"
            f"질문:\n{user_prompt}\n\n"
            "설명:\n"
        )

        outputs = self.report_generator(
            full_prompt,
            max_length=512,
            do_sample=True,
            top_p=0.9,
            temperature=0.7,
            num_return_sequences=1,
            pad_token_id=self.report_generator.tokenizer.eos_token_id,
        )

        generated = outputs[0]["generated_text"]
        if generated.startswith(full_prompt):
            generated = generated[len(full_prompt):]

        return generated.strip()

    # NER 탭
    def analyze_ner(self, text: str) -> list[dict]:
        """NER 분석 탭용."""
        sentence = (text or "").strip()
        if not sentence:
            return []

        raw_entities = self.ner_pipeline(sentence)

        results: list[dict] = []
        for ent in raw_entities:
            results.append(
                {
                    "word": ent.get("word"),
                    "type": ent.get("entity_group"),
                    "score": float(ent.get("score", 0.0)),
                    "start": int(ent.get("start", 0)),
                    "end": int(ent.get("end", 0)),
                }
            )
        return results

    # Q&A 탭
    def answer_qa(
        self,
        question: str,
        *,
        district: str | None = None,
        start_year: int | None = None,
        end_year: int | None = None,
    ) -> str:
        user_q = (question or "").strip()

        meta = self._build_meta_with_overrides(
            user_q,
            district=district,
            start_year=start_year,
            end_year=end_year,
        )

        context = self._build_forecast_context(meta)

        system_prefix = (
            "너는 서울시 지역아동센터 수요 예측 결과와 관련된 질문에 답하는 "
            "데이터 분석 보조자야. "
            "위에 제공된 예측 데이터 요약과 아래 질문을 참고해서, "
            "예측 추세, 관련 지표, 정책적 시사점을 "
            "3~6문장 정도의 한국어 단락으로 설명해 줘. "
            "정확한 연도별 수치나 구체적인 숫자는 지금 알 수 없으니, "
            "숫자를 지어내지 말고 방향성 위주로 설명해."
        )

        full_prompt = ""
        if context:
            full_prompt += context + "\n"

        full_prompt += (
            f"{system_prefix}\n\n"
            f"질문:\n{user_q}\n\n"
            "답변:\n"
        )

        outputs = self.report_generator(
            full_prompt,
            max_length=512,
            do_sample=True,
            top_p=0.9,
            temperature=0.7,
            num_return_sequences=1,
            pad_token_id=self.report_generator.tokenizer.eos_token_id,
        )

        generated = outputs[0]["generated_text"]
        if generated.startswith(full_prompt):
            generated = generated[len(full_prompt):]

        return generated.strip()

    def answer_qa_with_log(
        self,
        question: str,
        *,
        user_id: int | None = None,
        page: str | None = None,
        district: str | None = None,
        start_year: int | None = None,
        end_year: int | None = None,
    ) -> str:
        """Q&A + 로그 저장."""
        user_q = (question or "").strip()

        answer = self.answer_qa(
            user_q,
            district=district,
            start_year=start_year,
            end_year=end_year,
        )

        self._save_chat_log(
            user_id=user_id,
            page=page,
            task_type="qa",
            question=user_q,
            answer=answer,
        )

        return answer

    # 컨텍스트 빌더들

    # 예측 데이터 요약 생성
    def _build_forecast_context(self, meta: QueryMeta) -> str:
        district = (meta.district or "").strip()

        if not district or district == "전체":
            return ""

        # 연도 기본값 지정 안 되었으면 2023~2030 사용
        start_year = meta.start_year if meta.start_year is not None else 2023
        end_year = meta.end_year if meta.end_year is not None else 2030

        rows = self._query_forecast_rows(district, start_year, end_year)
        if not rows:
            return ""

        # 연도별 예측 이용자 수 나열
        lines_predict: list[str] = []
        for r in rows:
            try:
                val = int(round(r.predicted_child_user))
                val_str = f"{val:,}"
            except Exception:
                val_str = str(r.predicted_child_user)
            lines_predict.append(f"- {r.year}년: 약 {val_str}명")

        first = rows[0]
        last = rows[-1]

        def get_attr_safe(obj, name):
            return getattr(obj, name, None)

        feature_summaries: list[str] = []

        feature_summaries.append(
            f"예측 이용자 수: {self._format_change(first.predicted_child_user, last.predicted_child_user)}"
        )
        feature_summaries.append(
            f"한부모 가구 수: {self._format_change(get_attr_safe(first, 'single_parent'), get_attr_safe(last, 'single_parent'))}"
        )
        feature_summaries.append(
            f"기초생활수급자 수: {self._format_change(get_attr_safe(first, 'basic_beneficiaries'), get_attr_safe(last, 'basic_beneficiaries'))}"
        )
        feature_summaries.append(
            f"다문화 가구 수: {self._format_change(get_attr_safe(first, 'multicultural_hh'), get_attr_safe(last, 'multicultural_hh'))}"
        )
        feature_summaries.append(
            f"학원 수: {self._format_change(get_attr_safe(first, 'academy_cnt'), get_attr_safe(last, 'academy_cnt'))}"
        )
        feature_summaries.append(
            f"1인당 GRDP: {self._format_change(get_attr_safe(first, 'grdp'), get_attr_safe(last, 'grdp'))}"
        )
        feature_summaries.append(
            f"자치구 인구수: {self._format_change(get_attr_safe(first, 'population'), get_attr_safe(last, 'population'))}"
        )

        context_lines: list[str] = []

        context_lines.append("[예측 데이터 요약]")
        context_lines.append(f"자치구: {district}")
        context_lines.append(f"연도 범위: {start_year}년 ~ {end_year}년")
        context_lines.append("")
        context_lines.append("연도별 지역아동센터 예측 이용자 수:")
        context_lines.extend(lines_predict)
        context_lines.append("")
        context_lines.append("주요 지표 변화(기간 전체 기준):")
        context_lines.extend(f"- {fs}" for fs in feature_summaries)
        context_lines.append("[예측 데이터 요약 끝]")

        return "\n".join(context_lines) + "\n\n"

    # 지표 요약해서 프롬포트 앞에 붙일 문자열로 만듬
    def _build_indicator_context(self, meta: QueryMeta, indicator_col: str, indicator_label: str) -> str:
        district = (meta.district or "").strip()
        if not district or district == "전체":
            return ""

        start_year = meta.start_year if meta.start_year is not None else 2023
        end_year = meta.end_year if meta.end_year is not None else 2030

        rows = self._query_forecast_rows(district, start_year, end_year)
        if not rows:
            return ""

        first = rows[0]
        last = rows[-1]

        def get_attr_safe(obj, name):
            return getattr(obj, name, None)

        indicator_start = get_attr_safe(first, indicator_col)
        indicator_end = get_attr_safe(last, indicator_col)

        user_start = getattr(first, "predicted_child_user", None)
        user_end = getattr(last, "predicted_child_user", None)

        indicator_change = self._format_change(indicator_start, indicator_end)
        user_change = self._format_change(user_start, user_end)

        lines: list[str] = []
        lines.append("[지표 및 예측 데이터 요약]")
        lines.append(f"자치구: {district}")
        lines.append(f"연도 범위: {start_year}년 ~ {end_year}년")
        lines.append("")
        lines.append(f"{indicator_label} 변화(기간 전체 기준): {indicator_change}")
        lines.append(f"예측 이용자 수 변화(기간 전체 기준): {user_change}")
        lines.append("[지표 및 예측 데이터 요약 끝]")

        return "\n".join(lines) + "\n\n"
