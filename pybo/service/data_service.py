from pybo.service.region_repository import RegionRepository

# 대시보드, 머신러닝 예측 관련 데이터를 DB에서 조회하고 가공하는 서비스 클래스
class DataService:

    def __init__(self):
        self.region_repo = RegionRepository()

    # 공통 피처 추출 함수
    def _extract_features(self, row):

        if not row:
            return None

        return {
            "single_parent": getattr(row, "single_parent", None),
            "basic_beneficiaries": getattr(row, "basic_beneficiaries", None),
            "multicultural_hh": getattr(row, "multicultural_hh", None),
            "academy_cnt": getattr(row, "academy_cnt", None),
            "grdp": getattr(row, "grdp", None),
            "population": getattr(row, "population", None),
        }

    # 대시보드 데이터
    def get_dashboard_data(self, district: str | None, start_year: int | None, end_year: int | None) -> dict:
        rows = self.region_repo.get_dashboard_rows(district, start_year, end_year)

        items = [
            {
                "year": r.year,
                "child_user": int(r.child_user) if r.child_user is not None else 0,
                "child_facility": int(r.child_facility) if r.child_facility is not None else 0
            }
            for r in rows
        ]

        return {
            "success": True,
            "district": district,
            "start_year": start_year,
            "end_year": end_year,
            "items": items,
        }

    # 자치구 목록
    def get_districts(self) -> dict:

        # DB접근 repo사용
        rows = self.region_repo.get_district_rows()

        # None, 공백 문자열 제거
        districts = [r[0] for r in rows if r[0] not in (None, "", " ")]

        return {
            "success": True,
            "districts": districts,
        }

    # 머신러닝 예측 요약 카드, 표
    def get_predict_data(self, year: int, district: str) -> dict:

        child_user = 0
        child_facility = 0
        feature_values = None

        # 현재 연도 값 처리
        if district and district != "전체":
            if year <= 2022:
                cur_row = self.region_repo.get_region_row(year=year, district=district) #실측
                if cur_row:
                    child_user = int(cur_row.child_user or 0)
                    child_facility = int(cur_row.child_facility or 0)
                    feature_values = self._extract_features(cur_row)

            else:
                cur_forecast = self.region_repo.get_forecast_row(year=year, district=district) # 예측
                if cur_forecast:
                    child_user = int(cur_forecast.predicted_child_user or 0)
                    feature_values = self._extract_features(cur_forecast)
                else:
                    feature_values = None
                child_facility = 0
        else: # 전체 합계를 선택한 경우
            if year <= 2022: # 실측 연도 구간
                cur_result = self.region_repo.get_total_region_child_user_facility(year=year)
                child_user = (
                    int(cur_result.child_user)
                    if cur_result and cur_result.child_user is not None
                    else 0
                )
                child_facility = (
                    int(cur_result.child_facility)
                    if cur_result and cur_result.child_facility is not None
                    else 0
                )
            else:
                cur_result = self.region_repo.get_total_forecast_child_user(year=year)
                child_user = (
                    int(cur_result.child_user)
                    if cur_result and cur_result.child_user is not None
                    else 0
                )

                child_facility = 0

        # 전년 값 처리
        prev_child_user = None
        prev_year = year - 1

        if prev_year >= 2015:
            if district and district != "전체":

                if prev_year <= 2022:
                    prev_row = self.region_repo.get_region_row(year=prev_year, district=district)
                    if prev_row and prev_row.child_user is not None:
                        prev_child_user = int(prev_row.child_user)
                else:
                    prev_row = self.region_repo.get_forecast_row(year=prev_year, district=district)
                    if prev_row and prev_row.predicted_child_user is not None:
                        prev_child_user = int(prev_row.predicted_child_user)

            else: # 전체 선택 시 전년 합계 조회
                if prev_year <= 2022:
                    prev_result = self.region_repo.get_region_sum_child_user(year=prev_year)
                else:
                    prev_result = self.region_repo.get_forecast_sum_child_user(year=prev_year)

                if prev_result and prev_result.child_user is not None:
                    prev_child_user = int(prev_result.child_user)

        # 자치구당 평균 계산
        seoul_avg_child_user = None
        seoul_district_count = 0

        if year <= 2022:
            avg_row = self.region_repo.get_seoul_avg_region(year=year)
        else:
            avg_row = self.region_repo.get_seoul_avg_forecast(year=year)

        if avg_row:
            total_child_user = avg_row.total_child_user or 0
            seoul_district_count = int(avg_row.district_count or 0)
            if seoul_district_count > 0:
                seoul_avg_child_user = total_child_user / seoul_district_count # 평균 값 계산
            # 최종 결과
        return {
            "success": True,
            "district": district,
            "year": year,
            "child_user": child_user,
            "child_facility": child_facility,
            "prev_child_user": prev_child_user,
            "seoul_avg_child_user": seoul_avg_child_user,
            "seoul_district_count": seoul_district_count,
            "features": feature_values,
        }

    # 예측 그래프 데이터
    def get_predict_series(self, district: str) -> dict:

        items: list[dict] = []

        if district and district != "전체":

            actual_row = self.region_repo.get_region_series_actual(district)
            for r in actual_row:
                if r.child_user is None:
                    continue
                items.append({
                    "year": int(r.year),
                    "child_user": int(r.child_user),
                    "is_pred": False,
                })

            pred_rows = self.region_repo.get_region_series_forecast(district)
            for r in pred_rows:
                if r.predicted_child_user is None:
                    continue
                items.append({
                    "year": int(r.year),
                    "child_user": int(r.predicted_child_user),
                    "is_pred": True,
                })
        else:
            actual_rows = self.region_repo.get_total_series_actual()
            for r in actual_rows:
                if r.child_user is None:
                    continue
                items.append({
                    "year": int(r.year),
                    "child_user": int(r.child_user),
                    "is_pred": False,
                })

            pred_rows = self.region_repo.get_total_series_forecast()
            for r in pred_rows:
                if r.child_user is None:
                    continue
                items.append({
                    "year": int(r.year),
                    "child_user": int(r.child_user),
                    "is_pred": True,
                })
        items.sort(key=lambda x: x["year"]) # 마지막으로 순서 점검 year기준으로 정렬

        return {
            "success": True,
            "district": district,
            "items": items,
        }