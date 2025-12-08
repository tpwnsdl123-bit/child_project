from flask import Blueprint, request, jsonify
from pybo.ml.predictor import predict_child_user

# API 전용 prefix
bp = Blueprint("predict_api", __name__, url_prefix="/api")


@bp.route('/predict', methods=['GET', 'POST'])
def predict_api():

    # GET 요청 처리
    if request.method == 'GET':
        return jsonify({
            "message": "predict API is running. Use POST with JSON body."
        })

    # POST 요청 처리
    data = request.get_json()

    if data is None:
        return jsonify({
            "success": False,
            "error": "JSON body is missing."
        }), 400

    try:
        pred_value = predict_child_user(data)
        return jsonify({
            "success": True,
            "prediction": pred_value
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
