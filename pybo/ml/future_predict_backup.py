import os
import pandas as pd
import joblib
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))   
DATA_DIR = os.path.join(BASE_DIR, "..", "..", "data")
ML_DIR = BASE_DIR

MASTER_CSV_PATH = os.path.join(DATA_DIR, "master_2015_2022.csv")
df = pd.read_csv(MASTER_CSV_PATH, encoding="utf-8")

MODEL_PATH = os.path.join(ML_DIR, "model_xgb.pkl")
model = joblib.load(MODEL_PATH)

# 모델에서 필요한 정보 불러오기
district_ohe_cols = model.district_ohe_cols
base_features = model.base_features
feature_cols = base_features + district_ohe_cols

# 기간 설정
base_year = 2015
last_year = 2022
future_start = 2023
future_end = 2030


def calc_cagr(series, start_year, end_year):

    # 연평균 성장률 계산 함수
    v0 = series.loc[start_year]
    v1 = series.loc[end_year]
    if v0 <= 0 or v1 <= 0:
        return 0.0
    n = end_year - start_year
    return (v1 / v0) ** (1 / n) - 1


# 미래 Feature 생성

future_rows = []
districts = df["district"].unique()

for district in districts:
    df_dist = df[df["district"] == district].copy()
    df_period = df_dist[df_dist["year"].between(base_year, last_year)]

    # year 제외한 base_features에 대해 성장률 계산
    growth_rates = {col: 0.0 for col in base_features if col != "year"}

    for col in growth_rates.keys():
        yearly_sum = df_period.groupby("year")[col].sum()

        if base_year not in yearly_sum.index or last_year not in yearly_sum.index:
            growth_rates[col] = 0.0
            continue

        rate = calc_cagr(yearly_sum, base_year, last_year)

        growth_rates[col] = rate

    base_row = df_dist[df_dist["year"] == last_year].iloc[0]

    for year in range(future_start, future_end + 1):
        years_ahead = year - last_year

        new_row = {
            "district": district,
            "year": year,
        }

        # 각 feature를 CAGR 기반으로 증가시킴
        for col in growth_rates.keys():
            base_val = base_row[col]
            rate = growth_rates[col]
            new_row[col] = base_val * ((1 + rate) ** years_ahead)

        future_rows.append(new_row)

# DataFrame 변환
future_df = pd.DataFrame(future_rows)

# district 원핫 인코딩
for ohe_col in district_ohe_cols:
    gu_name = ohe_col.replace("district_", "")
    future_df[ohe_col] = (future_df["district"] == gu_name).astype(int)

# 최종 X_future 구성
X_future = future_df[feature_cols]

# 연간 증감률 제한
MAX_YEAR_RATIO = 2.0 # 전년 대비 최대 +30%
MIN_YEAR_RATIO = 0.5 # 전년 대비 최소 -30%

# 절대 상한: 과거 정상 구간 최대값의 1.5배
ABS_MULT = 3.0

future_df["child_user_raw"] = np.expm1(model.predict(X_future))

future_df = future_df.sort_values(["district", "year"]).reset_index(drop=True)
future_df["child_user"] = future_df["child_user_raw"]

for district in districts:
    # 과거 데이터 (2015~2022)
    hist = (
        df[(df["district"] == district) & (df["year"] <= last_year)]
        .sort_values("year")
        .copy()
    )
    if hist.empty:
        continue

    # 전년 기준값 (2022 실제값)
    last_row = hist[hist["year"] == last_year]
    if last_row.empty:
        continue
    prev_val = float(last_row.iloc[0]["child_user"])

    normal_hist = hist[(hist["year"] >= 2017) & (hist["year"] <= last_year)]
    normal_hist = normal_hist.dropna(subset=["child_user"])
    if normal_hist.empty:
        normal_hist = hist.dropna(subset=["child_user"])

    if normal_hist.empty:
        abs_max = None
    else:
        max_normal = float(normal_hist["child_user"].max())
        abs_max = max_normal * ABS_MULT   # 이 구의 절대 상한

    # 이 구의 2023~2030 예측 rows
    mask = (future_df["district"] == district)
    gu_future = future_df[mask].sort_values("year")

    for idx, row in gu_future.iterrows():
        year_val = int(row["year"])
        raw = float(row["child_user_raw"])

        # (a) 모든 미래연도: 전년 대비 ±30% 안에서만 움직이기
        if prev_val <= 0:
            capped = raw
        else:
            ratio = raw / prev_val

            if ratio > MAX_YEAR_RATIO:
                capped = prev_val * MAX_YEAR_RATIO
            elif ratio < MIN_YEAR_RATIO:
                capped = prev_val * MIN_YEAR_RATIO
            else:
                capped = raw

        if abs_max is not None and capped > abs_max:
            # prev_val에서 상한 쪽으로 30%만 이동
            capped = prev_val + (abs_max - prev_val) * 0.3
            if capped > abs_max:
                capped = abs_max

        # 최종 값 저장 & 다음 해 기준 갱신
        future_df.at[idx, "child_user"] = capped
        prev_val = capped

OUTPUT_PATH = os.path.join(DATA_DIR, "predicted_child_user_2023_2030.csv")
future_df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

print("미래 예측 CSV 생성 완료:", OUTPUT_PATH)
print(future_df.head(10))


# 캡핑이 적용된 비율 (raw랑 다른 행 비율)
diff_rate = (future_df["child_user"] != future_df["child_user_raw"]).mean()
print("캡핑 걸린 비율:", diff_rate)

# 어느 정도로 바뀌었는지 보기 (몇 개만)
future_df["ratio"] = future_df["child_user"] / future_df["child_user_raw"]
print(future_df[["district", "year", "child_user_raw", "child_user", "ratio"]].head(30))
