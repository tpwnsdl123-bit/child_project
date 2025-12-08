import os
import pandas as pd
from pybo import create_app, db
from pybo.models import RegionForecast  # RegionData는 안 써서 빼도 됨

app = create_app()
app.app_context().push()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
csv_path = os.path.join(DATA_DIR, "predicted_child_user_2023_2030.csv")

# 기존 미래 예측 삭제
deleted = (
    RegionForecast.query
    .filter(RegionForecast.year >= 2023)
    .delete(synchronize_session=False)
)
db.session.commit()
print(f"기존 미래 예측 데이터 삭제: {deleted}건")

df = pd.read_csv(csv_path, encoding="utf-8-sig")

insert_count = 0

for _, row in df.iterrows():
    forecast = RegionForecast(
        district      = row["district"],
        year          = row["year"],
        predicted_child_user = row["child_user"],
        single_parent        = row["single_parent"],
        basic_beneficiaries  = row["basic_beneficiaries"],
        multicultural_hh     = row["multicultural_hh"],
        academy_cnt          = row["academy_cnt"],
        grdp                 = row["grdp"],
    )
    db.session.add(forecast)

    insert_count += 1

db.session.commit()

print(f"{insert_count}건 미래 예측 데이터 삽입")