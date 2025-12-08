from pybo import create_app, db
from pybo.models import RegionData
from sqlalchemy import func

app = create_app()

with app.app_context():
    total_rows = db.session.query(func.count(RegionData.id)).scalar()
    year_min, year_max = db.session.query(
        func.min(RegionData.year),
        func.max(RegionData.year)
    ).one()

    district_cnt = db.session.query(func.count(func.distinct(RegionData.district))).scalar()

    print("총 행 개수:", total_rows)
    print("연도 범위:", year_min, "~", year_max)
    print("구 개수:", district_cnt)

    sample = db.session.query(RegionData).filter_by(district="종로구").order_by(RegionData.year).all()
    print("\n[종로구 연도별 데이터]")
    for row in sample:
        print(row.year, row.child_user)