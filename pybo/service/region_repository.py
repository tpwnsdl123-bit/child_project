# RegionData / RegionForecast 테이블에 직접적으로 가는 계층
from sqlalchemy import func, distinct
from pybo.models import RegionData, RegionForecast

class RegionRepository: # 대시보드, 자치구 목록 등 지역 관련 데이트 조회하기 위한 클래스 (서비스 계층에서 사용)

    # 대시보드용 집계 데이터
    def get_dashboard_rows(self, district: str | None, start_year: int | None, end_year: int | None):

        query = RegionData.query

        if district and district != "전체":
            query = query.filter(RegionData.district == district)

        if start_year:
            query = query.filter(RegionData.year >= start_year)
        if end_year:
            query = query.filter(RegionData.year <= end_year)
        # 연도별 합계 쿼리
        rows = (
            query.with_entities(
                RegionData.year.label("year"),
                func.sum(RegionData.child_user).label("child_user"),
                func.sum(RegionData.child_facility).label("child_facility"),
            )
            .group_by(RegionData.year)
            .order_by(RegionData.year)
            .all()
        )
        return rows

    # 자치구 목록
    def get_district_rows(self):
        rows = (
            RegionData.query
            .with_entities(distinct(RegionData.district))
            .order_by(RegionData.district)
            .all()
        )
        return rows

    # 특정 구 1건 실측
    def get_region_row(self, year: int, district: str):
        return(
            RegionData.query
            .filter(RegionData.year == year,
                    RegionData.district == district)
            .first()
        )

    # 특정 구 1건 예측
    def get_forecast_row(self, year: int, district: str):
        return(
            RegionForecast.query
            .filter(RegionForecast.year == year,
                    RegionForecast.district == district)
            .first()
        )

    # 전체 합계 (실측: 이용자, 시설)
    def get_total_region_child_user_facility(self, year: int):
        return(
            RegionData.query
            .filter(RegionData.year == year)
            .with_entities(
                func.sum(RegionData.child_user).label("child_user"),
                func.sum(RegionData.child_facility).label("child_facility"),
            )
            .first()
        )

    # 전체 예측 합계
    def get_total_forecast_child_user(self, year: int):
        return (
            RegionForecast.query
            .filter(RegionForecast.year == year)
            .with_entities(
                func.sum(RegionForecast.predicted_child_user).label("child_user"),
            )
            .first()
        )

    # 전년 전체 합계 (실측)
    def get_region_sum_child_user(self, year: int):
        return (
            RegionData.query
            .filter(RegionData.year == year)
            .with_entities(
                func.sum(RegionData.child_user).label("child_user"),
            )
            .first()
        )

    # 전년 전체 합계 (예측)
    def get_forecast_sum_child_user(self, year:int):
        return (
            RegionForecast.query
            .filter(RegionForecast.year == year)
            .with_entities(
                func.sum(RegionForecast.predicted_child_user).label("child_user"),
            )
            .first()
        )

    # 서울평균 (실측)
    def get_seoul_avg_region(self, year: int):
        return (
            RegionData.query
            .filter(RegionData.year == year)
            .with_entities(
                func.sum(RegionData.child_user).label("total_child_user"),
                func.count(distinct(RegionData.district)).label("district_count"),
            )
            .first()
        )

    # 서울평균 (예측)
    def get_seoul_avg_forecast(self, year: int):
        return (
            RegionForecast.query
            .filter(RegionForecast.year == year)
            .with_entities(
                func.sum(RegionForecast.predicted_child_user).label("total_child_user"),
                func.count(distinct(RegionForecast.district)).label("district_count")
            )
            .first()
        )

    # 특정 구 실측 시계열(2015~2022)
    def get_region_series_actual(self, district: str):
        return (
            RegionData.query
            .filter(RegionData.district == district)
            .filter(RegionData.year.between(2015, 2022))
            .order_by(RegionData.year.asc())
            .all()
        )

    # 특정 구 예측 시계열(2023~)
    def get_region_series_forecast(self, district: str):
        return (
            RegionForecast.query
            .filter(RegionForecast.district == district)
            .filter(RegionForecast.year >= 2023)
            .order_by(RegionForecast.year.asc())
            .all()
        )

    # 전체 실측 합계 시계열(2015~2022)
    def get_total_series_actual(self):
        return (
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

    # 전체 예측 합계 시계열(2023~)
    def get_total_series_forecast(self):
        return (
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