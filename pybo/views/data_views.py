from flask import Blueprint, jsonify, request
from sqlalchemy import func, distinct
from pybo.models import RegionData, RegionForecast

bp = Blueprint("data", __name__, url_prefix="/data")


@bp.route("/test")
def test():
    return "data_views 정상 작동"

#  대시보드 데이터 API

@bp.route("/dashboard-data")
def dashboard_data():
    district = request.args.get("district", default="전체", type=str)
    start_year = request.args.get("start_year", type=int)
    end_year = request.args.get("end_year", type=int)

    query = RegionData.query

    # 자치구 필터
    if district and district != "전체":
        query = query.filter(RegionData.district == district)

    # 연도 범위 필터
    if start_year:
        query = query.filter(RegionData.year >= start_year)
    if end_year:
        query = query.filter(RegionData.year <= end_year)

    # 연도별 합계 (서울 전체 혹은 선택 구의 합계)
    results = (
        query.with_entities(
            RegionData.year.label("year"),
            func.sum(RegionData.child_user).label("child_user"),
            func.sum(RegionData.child_facility).label("child_facility"),
        )
        .group_by(RegionData.year)
        .order_by(RegionData.year)
        .all()
    )

    items = [
        {
            "year": r.year,
            "child_user": int(r.child_user) if r.child_user is not None else 0,
            "child_facility": int(r.child_facility) if r.child_facility is not None else 0,
        }
        for r in results
    ]

    return jsonify({
        "success": True,
        "district": district,
        "start_year": start_year,
        "end_year": end_year,
        "items": items,
    })


#  자치구 목록 API

@bp.route("/districts")
def get_districts():
    rows = (
        RegionData.query
        .with_entities(distinct(RegionData.district))
        .order_by(RegionData.district)
        .all()
    )

    # None / 공백 제거
    districts = [r[0] for r in rows if r[0] not in (None, "", " ")]

    return jsonify({"success": True, "districts": districts})


#  (이전) 단순 차트용 API

@bp.route("/predict-chart")
def predict_chart():
    district = request.args.get("district", type=str, default=None)

    query = RegionData.query.filter(RegionData.year >= 2015)

    if district and district != "전체":
        query = query.filter(RegionData.district == district)

    rows = (
        query.with_entities(
            RegionData.year.label("year"),
            func.sum(RegionData.child_user).label("child_user"),
        )
        .group_by(RegionData.year)
        .order_by(RegionData.year)
        .all()
    )

    items = [
        {
            "year": r.year,
            "child_user": float(r.child_user or 0),
        }
        for r in rows
    ]

    return jsonify({"success": True, "items": items})

#  예측 요약 카드 + 표 API

def _extract_features(row):
    """
    모델에 들어간 주요 피처를 한 번에 dict로 뽑는 유틸 함수.
    컬럼 이름은 실제 models 정의에 맞춰 사용.
    (없는 컬럼이면 getattr 기본값으로 None 들어감)
    """
    if not row:
        return None

    return {
        "single_parent":       getattr(row, "single_parent", None),
        "basic_beneficiaries": getattr(row, "basic_beneficiaries", None),
        "multicultural_hh":    getattr(row, "multicultural_hh", None),
        "academy_cnt":         getattr(row, "academy_cnt", None),
        "grdp":                getattr(row, "grdp", None),
        # "population":       getattr(row, "population", None),  # 필요하면 추가
    }


@bp.route("/predict-data")
def predict_data():
    """
    - child_user            : 해당 조건 이용자 수
      (전체 선택 시 : 모든 구 합계, 특정 구 선택 시 : 그 구의 row 값)
    - child_facility        : 시설 수 (예측 연도는 0 또는 None 처리)
    - prev_child_user       : 전년 이용자 수 (없으면 None)
    - seoul_avg_child_user  : 해당 연도 서울 '구당' 평균 이용자 수
    - seoul_district_count  : 평균 계산에 쓰인 자치구 개수
    - features              : (특정 구 선택 시) 그 해의 주요 피처 값 dict
    """
    year = request.args.get("year", type=int)
    if year is None:
        return jsonify({"success": False, "error": "year is required"}), 400

    district = request.args.get("district", default="전체", type=str)

    child_user = 0
    child_facility = 0
    feature_values = None  # 이 해의 피처 값

    #  현재 연도 값
    if district and district != "전체":
        if year <= 2022:
            #  실측: RegionData 에서 모두
            cur_row = (
                RegionData.query
                .filter(RegionData.year == year,
                        RegionData.district == district)
                .first()
            )
            if cur_row:
                child_user = int(cur_row.child_user or 0)
                child_facility = int(cur_row.child_facility or 0)
                feature_values = _extract_features(cur_row)

        else:
            # 2015 이후, 예측 연도(2023~) : RegionForecast에서 이용자 + 피처 모두 가져오기
            cur_forecast = (
                RegionForecast.query
                .filter(RegionForecast.year == year,
                        RegionForecast.district == district)
                .first()
            )
            if cur_forecast:
                child_user = int(cur_forecast.predicted_child_user or 0)
                feature_values = _extract_features(cur_forecast)
            else:
                feature_values = None

            # 시설 수는 예측 안해서 0 처리
            child_facility = 0

    else:
        # "전체" 선택 시 : 모든 구 합계 (피처는 개별구 기준이라 제공 X)
        if year <= 2022:
            cur_result = (
                RegionData.query
                .filter(RegionData.year == year)
                .with_entities(
                    func.sum(RegionData.child_user).label("child_user"),
                    func.sum(RegionData.child_facility).label("child_facility"),
                )
                .first()
            )
            child_user = int(cur_result.child_user) if cur_result and cur_result.child_user is not None else 0
            child_facility = int(cur_result.child_facility) if cur_result and cur_result.child_facility is not None else 0
        else:
            cur_result = (
                RegionForecast.query
                .filter(RegionForecast.year == year)
                .with_entities(
                    func.sum(RegionForecast.predicted_child_user).label("child_user"),
                )
                .first()
            )
            child_user = int(cur_result.child_user) if cur_result and cur_result.child_user is not None else 0
            child_facility = 0
        # feature_values = None  그대로 (전체는 피처 표 안 보여줌)

    #  전년 값 (prev_child_user)
    prev_child_user = None
    prev_year = year - 1

    if prev_year >= 2015:  # 데이터 시작년도에 맞게
        if district and district != "전체":
            if prev_year <= 2022:
                prev_row = (
                    RegionData.query
                    .filter(RegionData.year == prev_year,
                            RegionData.district == district)
                    .first()
                )
                if prev_row and prev_row.child_user is not None:
                    prev_child_user = int(prev_row.child_user)
            else:
                prev_row = (
                    RegionForecast.query
                    .filter(RegionForecast.year == prev_year,
                            RegionForecast.district == district)
                    .first()
                )
                if prev_row and prev_row.predicted_child_user is not None:
                    prev_child_user = int(prev_row.predicted_child_user)
        else:
            # 전체 (합계)
            if prev_year <= 2022:
                prev_result = (
                    RegionData.query
                    .filter(RegionData.year == prev_year)
                    .with_entities(
                        func.sum(RegionData.child_user).label("child_user"),
                    )
                    .first()
                )
                if prev_result and prev_result.child_user is not None:
                    prev_child_user = int(prev_result.child_user)
            else:
                prev_result = (
                    RegionForecast.query
                    .filter(RegionForecast.year == prev_year)
                    .with_entities(
                        func.sum(RegionForecast.predicted_child_user).label("child_user"),
                    )
                    .first()
                )
                if prev_result and prev_result.child_user is not None:
                    prev_child_user = int(prev_result.child_user)

    #  서울 평균 (연도 기준, 선택 구와 무관)
    seoul_avg_child_user = None
    seoul_district_count = 0

    if year <= 2022:
        avg_row = (
            RegionData.query
            .filter(RegionData.year == year)
            .with_entities(
                func.sum(RegionData.child_user).label("total_child_user"),
                func.count(distinct(RegionData.district)).label("district_count"),
            )
            .first()
        )
    else:
        avg_row = (
            RegionForecast.query
            .filter(RegionForecast.year == year)
            .with_entities(
                func.sum(RegionForecast.predicted_child_user).label("total_child_user"),
                func.count(distinct(RegionForecast.district)).label("district_count"),
            )
            .first()
        )

    if avg_row:
        total_child_user = avg_row.total_child_user or 0
        seoul_district_count = int(avg_row.district_count or 0)
        if seoul_district_count > 0:
            seoul_avg_child_user = total_child_user / seoul_district_count

    return jsonify({
        "success": True,
        "district": district,
        "year": year,
        "child_user": child_user,
        "child_facility": child_facility,
        "prev_child_user": prev_child_user,
        "seoul_avg_child_user": seoul_avg_child_user,
        "seoul_district_count": seoul_district_count,
        "features": feature_values,
    })

#  예측 시계열 (그래프용) API

@bp.route("/predict-series")
def predict_series():
    district = request.args.get("district", default="전체", type=str)

    items = []

    if district and district != "전체":
        # 특정 구 - 실측(2015~2022)
        actual_rows = (
            RegionData.query
            .filter(RegionData.district == district)
            .filter(RegionData.year.between(2015, 2022))
            .order_by(RegionData.year.asc())
            .all()
        )

        for r in actual_rows:
            if r.child_user is None:
                continue
            items.append({
                "year": int(r.year),
                "child_user": int(r.child_user),
                "is_pred": False,
            })

        # 특정 구 - 예측(2023~)
        pred_rows = (
            RegionForecast.query
            .filter(RegionForecast.district == district)
            .filter(RegionForecast.year >= 2023)
            .order_by(RegionForecast.year.asc())
            .all()
        )

        for r in pred_rows:
            if r.predicted_child_user is None:
                continue
            items.append({
                "year": int(r.year),
                "child_user": int(r.predicted_child_user),
                "is_pred": True,
            })

    else:
        # 전체 - 실측 합계
        actual_rows = (
            RegionData.query
            .with_entities(
                RegionData.year.label("year"),
                func.sum(RegionData.child_user).label("child_user"),
            )
            .filter(RegionData.year.between(2015, 2022))
            .group_by(RegionData.year)
            .order_by(RegionData.year.asc())
            .all()
        )

        for r in actual_rows:
            if r.child_user is None:
                continue
            items.append({
                "year": int(r.year),
                "child_user": int(r.child_user),
                "is_pred": False,
            })

        # 전체 - 예측 합계
        pred_rows = (
            RegionForecast.query
            .with_entities(
                RegionForecast.year.label("year"),
                func.sum(RegionForecast.predicted_child_user).label("child_user"),
            )
            .filter(RegionForecast.year >= 2023)
            .group_by(RegionForecast.year)
            .order_by(RegionForecast.year.asc())
            .all()
        )

        for r in pred_rows:
            if r.child_user is None:
                continue
            items.append({
                "year": int(r.year),
                "child_user": int(r.child_user),
                "is_pred": True,
            })

    # 연도 순으로 정렬 보장
    items.sort(key=lambda x: x["year"])

    return jsonify({
        "success": True,
        "district": district,
        "items": items,
    })
