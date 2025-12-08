import os
import pandas as pd
from pybo import create_app, db
from pybo.models import RegionData

app = create_app()

with app.app_context():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # flask_basic
    DATA_DIR = os.path.join(BASE_DIR, "data")
    csv_path = os.path.join(DATA_DIR, "master_2015_2022.csv")

    df = pd.read_csv(csv_path, encoding="utf-8")

    RegionData.query.delete()

    for _, row in df.iterrows():
        data = RegionData(
            district=row["district"],
            year=row["year"],
            grdp=row["grdp"],
            basic_beneficiaries=row["basic_beneficiaries"],
            multicultural_hh=row["multicultural_hh"],
            population=row["population"],
            divorce=row["divorce"],
            child_facility=row["child_facility"],
            child_user=row["child_user"],
            single_parent=row["single_parent"],
            birth_cnt=row["birth_cnt"],
            academy_cnt=row["academy_cnt"]
        )
        db.session.add(data)

    db.session.commit()
    print("RegionData 데이터 삽입 완료!")
