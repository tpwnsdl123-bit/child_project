from flask import Blueprint, request, jsonify, render_template, current_app, g
import requests
import os
from pybo.service.genai_service import get_genai_service

# Blueprint 설정 (URL 프리픽스 확인: /genai-api)
bp = Blueprint("genai_api", __name__, url_prefix="/genai-api")

genai_service = get_genai_service()


# 모델 변경
@bp.route("/switch-model", methods=["POST"])
def switch_model():
    data = request.get_json()
    try:
        # 런포드 서버의 /switch_model 엔드포인트 호출
        runpod_url = os.getenv("RUNPOD_API_URL").replace("/generate", "/switch_model")
        res = requests.post(runpod_url, json=data, timeout=60)
        return jsonify({"success": True, "result": res.json()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# 보고서 생성
@bp.route("/report", methods=["POST"])
def generate_report():
    data = request.get_json() or {}
    district = (data.get("district") or "").strip()
    start_year = data.get("start_year", 2023) # JS에서 보낸 값 사용
    end_year = data.get("end_year")
    model_ver = data.get("model_version", "final") # 모델 버전 추가

    if not district or not end_year:
        return jsonify({"success": False, "error": "자치구와 연도를 모두 선택해주세요."}), 400

    try:
        # model_version 파라미터 전달 추가
        result_text = genai_service.generate_report_with_data(
            user_prompt="report",
            district=district,
            start_year=int(start_year),
            end_year=int(end_year),
            model_version=model_ver
        )
        return jsonify({"success": True, "result": result_text})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# 정책 아이디어 생성
@bp.route("/policy", methods=["POST"])
def generate_policy():
    data = request.get_json() or {}
    prompt = (data.get("prompt") or "").strip()
    model_ver = data.get("model_version", "final") # 모델 버전 추가

    try:
        text = genai_service.generate_policy(prompt, model_version=model_ver)
        return jsonify({"success": True, "result": text})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# AI Q&A (지표 설명 + QA 통합)
@bp.route("/qa", methods=["POST"])
def qa():
    data = request.get_json() or {}
    question = (data.get("question") or "").strip()

    if not question:
        return jsonify({"success": False, "error": "질문을 입력해 주세요."}), 400

    # 로그인 사용자 ID 확인 (선택 사항)
    user_id = None
    if hasattr(g, "user_id") and getattr(g, "user", None):
        user_id = g.user.id

    try:
        answer = genai_service.answer_qa_with_log(
            question=question,
            user_id=user_id,
            page="genai"
        )
        return jsonify({"success": True, "result": answer})
    except Exception as e:
        current_app.logger.error(f"qa error: {e}")
        return jsonify({"success": False, "error": "답변 생성 중 오류가 발생했습니다."}), 500


# 설정 변경 API (JSON 반환으로 변경됨)
@bp.route("/config", methods=["POST"])
def config():
    data = request.get_json() or {}

    try:
        new_temp = float(data.get("temperature", 0.35))
        new_tokens = int(data.get("max_tokens", 600))

        # 서비스의 설정값 업데이트
        genai_service.update_settings({
            "temperature": new_temp,
            "max_tokens": new_tokens
        })

        return jsonify({"success": True, "message": "설정 변경 완료"})

    except ValueError:
        return jsonify({"success": False, "error": "잘못된 숫자 형식입니다."}), 400

# 텍스트 요약
@bp.route("/summarize", methods=["POST"])
def summarize():
    data = request.get_json() or {}
    text = (data.get("text") or "").strip()

    if not text:
        return jsonify({"success": False, "error": "요약할 본문을 입력해 주세요."}), 400

    try:
        summary = genai_service.summarize_text(text)
        return jsonify({"success": True, "result": summary})
    except Exception as e:
        current_app.logger.error(f"summarize error: {e}")
        return jsonify({"success": False, "error": "요약 생성 중 오류가 발생했습니다."}), 500