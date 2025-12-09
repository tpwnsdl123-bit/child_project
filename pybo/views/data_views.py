from flask import Blueprint, jsonify, request
from pybo.service.data_service import DataService

bp = Blueprint("data", __name__, url_prefix="/data")
data_service = DataService()

@bp.route("/test")
def test():
    return "data_views 정상 작동"

#  대시보드 데이터 API
@bp.route("/dashboard-data")
def dashboard_data():
    district = request.args.get("district", default="전체", type=str)
    start_year = request.args.get("start_year", type=int)
    end_year = request.args.get("end_year", type=int)

    data = data_service.get_dashboard_data(
        district=district,
        start_year=start_year,
        end_year=end_year,
    )
    return jsonify(data) # dict -> JSON 변환


#  자치구 목록 API
@bp.route("/districts")
def get_districts():
    data = data_service.get_districts()
    return jsonify(data)

# 예측 요약 카드, 표 API
@bp.route("/predict-data")
def predict_data():
    year = request.args.get("year", type=int)
    if year is None:
        return jsonify({"success": False, "error": "year is required"}), 400 # JSON, HTTP 상태코드 400 = Bad Requst

    district = request.args.get("district", default="전체", type=str)

    data = data_service.get_predict_data(year=year, district=district)

    return jsonify(data)

#  예측 그래프 API
@bp.route("/predict-series")
def predict_series():
    district = request.args.get('district', default="전체", type=str)

    data = data_service.get_predict_series(district=district)

    return jsonify(data)
