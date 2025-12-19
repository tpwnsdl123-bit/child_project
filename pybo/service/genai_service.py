import requests
import json
import re
import os
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import Optional

from transformers import pipeline

from pybo import db
from pybo.models import GenAIChatLog, RegionForecast
from pybo.service.rag_service import RagService

# .env 파일 로드
load_dotenv()

DISTRICTS = [
    "종로구", "중구", "용산구", "성동구", "광진구", "동대문구", "중랑구", "성북구", "강북구", "도봉구",
    "노원구", "은평구", "서대문구", "마포구", "양천구", "강서구", "구로구", "금천구", "영등포구", "동작구",
    "관악구", "서초구", "강남구", "송파구", "강동구",
]

INDICATOR_MAP = {
    "한부모": ("single_parent", "한부모 가구 수"),
    "기초생활": ("basic_beneficiaries", "기초생활수급자 수"),
    "다문화": ("multicultural_hh", "다문화 가구 수"),
    "학원": ("academy_cnt", "학원 수"),
    "grdp": ("grdp", "1인당 GRDP"),
    "인구": ("population", "자치구 인구수"),
}


@dataclass
class QueryMeta:
    district: str = "전체"
    start_year: Optional[int] = None
    end_year: Optional[int] = None


class GenAIService:
    # 서버 메모리에 저장되는 기본 하이퍼파라미터
    settings = {
        "temperature": 0.35,
        "max_tokens": 600,
        "system_prompt_report": (
            "너는 서울시 아동 돌봄 정책 전문 데이터 분석가야. "
            "주어진 [데이터 요약]을 바탕으로 정책 담당자용 보고서를 작성해.\n"
            "**반드시 아래 JSON 형식으로만 답변해야 해.** 설명이나 사족을 붙이지 마.\n\n"
            "{\n"
            '  "title": "보고서 제목",\n'
            '  "summary": "핵심 내용 3줄 요약",\n'
            '  "content": "상세 분석 내용 (평서문으로 작성)"\n'
            "}"
        )
    }

    def __init__(self) -> None:
        self.api_url = os.getenv("RUNPOD_API_URL")
        self.timeout = 180
        self.rag_service = RagService()

        if not self.api_url:
            print("경고: .env 파일에서 RUNPOD_API_URL을 찾을 수 없습니다.")

        print("NER 모델을 로딩 중입니다...")
        try:
            self.ner_pipeline = pipeline("ner", model="Leo97/KoELECTRA-small-v3-modu-ner")
            print("NER 모델 로딩 완료!")
        except Exception as e:
            print(f"NER 모델 로딩 실패: {e}")
            self.ner_pipeline = None

    def update_settings(self, new_settings: dict):
        if "temperature" in new_settings:
            self.settings["temperature"] = new_settings["temperature"]
        if "max_tokens" in new_settings:
            self.settings["max_tokens"] = new_settings["max_tokens"]

        training_args_config = {
            "max_steps": new_settings.get("max_steps", 300),
            "evaluation_strategy": new_settings.get("evaluation_strategy", "steps"),
            "save_strategy": new_settings.get("save_strategy", "steps"),
            "learning_rate": new_settings.get("learning_rate", "1e-4"),
            "optim": new_settings.get("optim", "paged_adamw_8bit"),
            "weight_decay": new_settings.get("weight_decay", 0.01),
            "warmup_steps": new_settings.get("warmup_steps", 20),
            "eval_steps": new_settings.get("eval_steps", 20),
            "save_steps": new_settings.get("save_steps", 40),
            "logging_steps": new_settings.get("logging_steps", 1),
            "per_device_train_batch_size": 1,
            "gradient_accumulation_steps": 8,
            "output_dir": "/workspace/finetune/outputs_llama3_c2",
            "load_best_model_at_end": True,
            "metric_for_best_model": "eval_loss",
            "greater_is_better": False,
            "bf16": True,
            "report_to": "none"
        }

        try:
            with open("training_config.json", "w", encoding="utf-8") as f:
                json.dump(training_args_config, f, indent=4)
        except Exception as e:
            print(f"파일 저장 실패: {e}")

    def _call_llama3(self, instruction: str, input_text: str, max_tokens: int = None) -> str:
        final_max_tokens = max_tokens if max_tokens else self.settings["max_tokens"]
        headers = {'Content-Type': 'application/json'}
        payload = {
            "instruction": instruction,
            "input": input_text,
            "max_new_tokens": final_max_tokens,
            "temperature": self.settings["temperature"],
            "do_sample": True
        }

        try:
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
            return result.get("text", "").strip().replace('\r', '')
        except Exception as e:
            print(f"RunPod Error: {e}")
            return "죄송합니다. AI 서버와 연결할 수 없습니다."

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
            meta.start_year, meta.end_year = min(y1, y2), max(y1, y2)
        else:
            single_pattern = r"(20\d{2})"
            m2 = re.search(single_pattern, q)
            if m2:
                y = int(m2.group(1))
                meta.start_year, meta.end_year = y, y
            else:
                meta.start_year, meta.end_year = 2023, 2030
        return meta

    def _build_meta_with_overrides(self, text: str, **kwargs) -> QueryMeta:
        meta = self._extract_query_meta(text)
        if kwargs.get('district') and kwargs['district'] != "전체": meta.district = kwargs['district'].strip()
        if kwargs.get('start_year') is not None: meta.start_year = int(kwargs['start_year'])
        if kwargs.get('end_year') is not None: meta.end_year = int(kwargs['end_year'])
        return meta

    def _format_change(self, start, end) -> str:
        if start is None or end is None: return "데이터 없음"
        s, e = float(start), float(end)
        base = f"{int(round(s)):,} -> {int(round(e)):,}"
        if s == 0: return base
        diff = (e - s) / s * 100.0
        return f"{base} ({'+' if diff >= 0 else ''}{diff:.1f}%)"

    def _save_chat_log(self, **kwargs) -> None:
        try:
            log = GenAIChatLog(**kwargs)
            db.session.add(log)
            db.session.commit()
        except Exception as e:
            print(f"로그 저장 실패: {e}")
            db.session.rollback()

    def generate_report_with_data(self, user_prompt: str, **kwargs) -> str:
        meta = self._build_meta_with_overrides(user_prompt, **kwargs)
        context = self._build_forecast_context(meta)
        instruction = self.settings["system_prompt_report"]
        input_text = f"{context}\n\n[사용자 요청]: {meta.district}의 {meta.start_year}~{meta.end_year}년 예측 데이터를 분석해줘."
        return self._call_llama3(instruction, input_text)

    def generate_policy(self, prompt: str, **kwargs) -> str:
        meta = self._build_meta_with_overrides(prompt, **kwargs)
        context = self._build_forecast_context(meta)
        instruction = "서울시 지역아동센터 정책 기획 보조자로서 현실적인 정책 아이디어 3개를 줄글로 제안해줘."
        input_text = f"{context}\n\n[사용자 요청]: {prompt}"
        return self._call_llama3(instruction, input_text, max_tokens=500)

    def answer_qa(self, question: str, **kwargs) -> str:
        user_q = (question or "").strip()
        meta = self._build_meta_with_overrides(user_q, **kwargs)
        pdf_context = self.rag_service.get_relevant_context(user_q)

        # 보고서 형식의 성공 사례를 적용한 구조적 인스트럭션
        # 답변의 형식을 강제하여 모델의 이탈을 방지함
        instruction = (
            "당신은 서울시 아동복지 정책 전문 안내원입니다. "
            "반드시 제공된 [운영 지침 및 법령 자료]를 바탕으로 답변 형식을 엄격히 준수하여 작성하십시오.\n\n"
            "작성 형식:\n"
            "**[핵심 답변]**: 질문에 대한 직접적인 답을 한 문장으로 요약\n"
            "**[상세 안내]**: 자료에 명시된 수치와 규칙을 포함한 구체적 설명\n"
            "**[근거 지침]**: 인용된 지침의 명칭이나 조항 번호\n\n"
            "주의 사항:\n"
            "- 제공된 자료에 없는 숫자를 임의로 생성하지 마십시오.\n"
            "- 자료에 직접적인 답이 없다면 관련 있는 유사 지침을 안내하십시오.\n"
            "- 답변에 ASSISTANT와 같은 추가 라벨을 붙이지 마십시오."
        )

        # 모델이 구조를 인식하기 쉽도록 입력 텍스트 설계
        # 보고서 프롬프트처럼 명확한 데이터와 요청을 구분함
        input_text = (
            f"### [운영 지침 및 법령 자료]\n{pdf_context}\n\n"
            f"### [사용자 질문]\n{user_q}\n\n"
            "위 자료를 분석하여 정책 안내 형식에 맞춰 답변하십시오.\n"
            "정책 전문가 답변:"
        )

        # 가독성을 위해 토큰 길이를 800으로 유지
        return self._call_llama3(instruction, input_text, max_tokens=800)

    def answer_qa_with_log(self, question: str, **kwargs) -> str:
        answer = self.answer_qa(question, **kwargs)
        self._save_chat_log(user_id=kwargs.get('user_id'), page=kwargs.get('page'), task_type="qa", question=question, answer=answer)
        return answer

    def _build_forecast_context(self, meta: QueryMeta) -> str:
        district = (meta.district or "").strip()
        if not district or district == "전체": return ""
        rows = RegionForecast.query.filter(RegionForecast.district == district, RegionForecast.year >= meta.start_year, RegionForecast.year <= meta.end_year).order_by(RegionForecast.year.asc()).all()
        if not rows: return ""
        first, last = rows[0], rows[-1]
        feature_summaries = [
            f"예측 이용자 수: {self._format_change(first.predicted_child_user, last.predicted_child_user)}",
            f"한부모 가구: {self._format_change(first.single_parent, last.single_parent)}",
            f"기초생활수급: {self._format_change(first.basic_beneficiaries, last.basic_beneficiaries)}",
            f"다문화 가구: {self._format_change(first.multicultural_hh, last.multicultural_hh)}",
            f"학원 수: {self._format_change(first.academy_cnt, last.academy_cnt)}",
            f"1인당 GRDP: {self._format_change(first.grdp, last.grdp)}"
        ]
        return "\n".join(["[데이터 요약]", f"자치구: {district}, 기간: {meta.start_year}~{meta.end_year}", "주요 지표 변화:", *[f"- {fs}" for fs in feature_summaries]])