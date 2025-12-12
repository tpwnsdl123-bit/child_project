from flask import Blueprint, request, jsonify, current_app, g
from pybo.service.genai_service import GenAIService

bp = Blueprint("genai_api", __name__, url_prefix="/genai-api")

genai_service = GenAIService()


@bp.route("/report", methods=["POST"])
def generate_report(): # 보고서 생성
    data = request.get_json() or {}
    prompt = (data.get("prompt") or "").strip()

    district = (data.get("district") or "").strip() or None
    start_year = data.get("start_year")
    end_year = data.get("end_year")

    if not prompt:
        return jsonify({"success": False, "error": "요청 내용을 입력해 주세요."}), 400

    try:
        result_text = genai_service.generate_report_with_data(
            prompt,
            district=district,
            start_year=start_year,
            end_year=end_year,
        )
        return jsonify({"success": True, "result": result_text})
    except Exception as e:
        print("generate_report error:", e, flush=True)
        return (
            jsonify({"success": False, "error": "보고서 생성 중 오류가 발생했습니다."}),
            500,
        )

@bp.route("/policy", methods=["POST"])
def generate_policy():  # 정책 아이디어
    data = request.get_json() or {}
    prompt = (data.get("prompt") or "").strip()

    # 선택적으로 자치구 / 연도 받기 (UI에서 안 보내면 전부 None)
    district = (data.get("district") or "").strip() or None
    start_year = data.get("start_year")
    end_year = data.get("end_year")

    if not prompt:
        return jsonify({"success": False, "error": "prompt is required"}), 400

    try:
        text = genai_service.generate_policy(
            prompt,
            district=district,
            start_year=start_year,
            end_year=end_year,
        )
        return jsonify({"success": True, "result": text})
    except Exception:
        current_app.logger.exception("genai policy error")
        return jsonify({"success": False, "error": "정책 아이디어 생성 중 오류가 발생했습니다."}), 500

@bp.route("/explain", methods=["POST"])
def explain():  # 지표 설명
    data = request.get_json() or {}
    prompt = (data.get("prompt") or "").strip()

    district = (data.get("district") or "").strip() or None
    start_year = data.get("start_year")
    end_year = data.get("end_year")

    if not prompt:
        return jsonify({"success": False, "error": "지표나 질문을 입력해 주세요."}), 400

    try:
        text = genai_service.explain_indicator(
            prompt,
            district=district,
            start_year=start_year,
            end_year=end_year,
        )
        return jsonify({"success": True, "result": text})
    except Exception as e:
        current_app.logger.exception("genai explain error")
        return jsonify({"success": False, "error": "지표 설명 생성 중 오류가 발생했습니다."}), 500


@bp.route("/ner", methods=["POST"])
def ner(): # NER 분석
    data = request.get_json() or {}
    text = (data.get("text") or "").strip()

    if not text:
        return jsonify({"success": False, "error": "분석할 문장을 입력해 주세요."}), 400

    try:
        items = genai_service.analyze_ner(text)
        return jsonify({"success": True, "items": items})
    except Exception:
        current_app.logger.exception("genai ner error")
        return jsonify({"success": False, "error": "NER 분석 중 오류가 발생했습니다."}), 500

@bp.route("/qa", methods=["POST"])
def qa():  # Q&A
    data = request.get_json() or {}

    question = (data.get("question") or "").strip()
    page = (data.get("page") or "").strip() or None

    district = (data.get("district") or "").strip() or None
    start_year = data.get("start_year")
    end_year = data.get("end_year")

    if not question:
        return jsonify({"success": False, "error": "질문을 입력해주세요."}), 400

    user_id = None
    if hasattr(g, "user_id") and g.user:
        user_id = g.user.id

    try:
        answer = genai_service.answer_qa_with_log(
            question=question,
            user_id=user_id,
            page=page,
            district=district,
            start_year=start_year,
            end_year=end_year,
        )
        return jsonify({"success": True, "result": answer})
    except Exception:
        current_app.logger.exception("genai qa error")
        return jsonify({"success": False, "error": "Q&A 생성 중 오류가 발생했습니다."}), 500
