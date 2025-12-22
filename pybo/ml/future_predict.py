
import os
import pandas as pd
import joblib
import numpy as np


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "..", "data")
ML_DIR = BASE_DIR

MASTER_CSV_PATH = os.path.join(DATA_DIR, "master_2015_2022.csv")
MODEL_PATH = os.path.join(ML_DIR, "model_xgb.pkl")
OUTPUT_PATH = os.path.join(DATA_DIR, "predicted_child_user_2023_2030.csv")

df = pd.read_csv(MASTER_CSV_PATH, encoding="utf-8")
model = joblib.load(MODEL_PATH)

district_ohe_cols = model.district_ohe_cols
base_features = model.base_features
feature_cols = base_features + district_ohe_cols

# 기간 설정
base_year = 2015
last_year = 2022
future_start = 2023
future_end = 2030

# CAGR 계산
# Compound Annaul Growth Ratio (연평균 성장률)
def calc_cagr(series, start_year, end_year):

    v0 = series.loc[start_year]
    v1 = series.loc[end_year]
    if v0 <= 0 or v1 <= 0:
        return 0.0
    n = end_year - start_year
    return (v1 / v0) ** (1 / n) - 1

# data driven

# 2015~2022 데이터의 CAGR을 분석해 2023~2030 CAGR범위 capping에 사용
# child_user CAGR 분석 (district)

cagr_list = []

for gu, df_gu in df.groupby("district"):
    s = (
        df_gu
        .set_index("year")["child_user"]
        .sort_index()
    )
    if base_year in s.index and last_year in s.index:
        r = calc_cagr(s, base_year, last_year)
        if np.isfinite(r):
            cagr_list.append(r)

cagr_arr = np.array(cagr_list)

# 양쪽 5% 제거: 중앙 90% 범위를 신뢰 구간으로 사용
MIN_CAGR = np.quantile(cagr_arr, 0.05)   # 하위 5%
MAX_CAGR = np.quantile(cagr_arr, 0.95)   # 상위 5%


# 2015~2022 데이터의 child_user를 분석해 2023~2030 pred_user_child capping에 사용
# child_user 연간 증가율 분석

ratio_list = []

for gu, df_gu in df.groupby("district"):
    df_gu_sorted = df_gu.sort_values("year")
    vals = df_gu_sorted["child_user"].values

    for i in range(1, len(vals)):
        prev = vals[i - 1]
        curr = vals[i]
        if prev > 0 and np.isfinite(prev) and np.isfinite(curr):
            ratio_list.append(curr / prev)

ratio_arr = np.array(ratio_list)

# y capping 범위
MIN_YEAR_RATIO = np.quantile(ratio_arr, 0.005)  # 하위 0.5%
MAX_YEAR_RATIO = np.quantile(ratio_arr, 0.995)  # 상위 0.5%


# 미래 feature 생성 (CAGR 기반)

future_rows = []
districts = df["district"].unique()

for district in districts:
    df_dist = df[df["district"] == district].copy()
    df_period = df_dist[df_dist["year"].between(base_year, last_year)]

    growth_rates = {col: 0.0 for col in base_features if col != "year"}

    for col in growth_rates.keys():
        yearly_sum = df_period.groupby("year")[col].sum()

        if base_year not in yearly_sum.index or last_year not in yearly_sum.index:
            growth_rates[col] = 0.0
            continue

        rate = calc_cagr(yearly_sum, base_year, last_year)

        # CAGR 캡핑 적용 
        if not np.isfinite(rate):
            rate = 0.0
        else:
            rate = max(min(rate, MAX_CAGR), MIN_CAGR)

        growth_rates[col] = rate

    # 기준이 되는 마지막 해(2022)의 값
    base_row = df_dist[df_dist["year"] == last_year].iloc[0]

    for year in range(future_start, future_end + 1):
        years_ahead = year - last_year

        new_row = {
            "district": district,
            "year": year,
        }

        # 각 feature를 CAGR 기반으로 증가/감소
        for col in growth_rates.keys():
            base_val = base_row[col]
            rate = growth_rates[col]
            new_row[col] = base_val * ((1 + rate) ** years_ahead)

        future_rows.append(new_row)


# 미래 데이터프레임 구성 + 원핫 인코딩

future_df = pd.DataFrame(future_rows)

for ohe_col in district_ohe_cols:
    gu_name = ohe_col.replace("district_", "")
    future_df[ohe_col] = (future_df["district"] == gu_name).astype(int)

X_future = future_df[feature_cols]


# 모델 예측 (log1p → expm1 역변환)

future_df["child_user_raw"] = np.expm1(model.predict(X_future))
future_df = future_df.sort_values(["district", "year"]).reset_index(drop=True)

# 예측값 컬럼(캡핑 후 값) 초기화 + dtype 통일
future_df["child_user"] = future_df["child_user_raw"].astype("float64")



# 연간 child_user 비율 기반 캡핑

for district in districts:
    # 과거 데이터 (2015~2022)
    hist = (
        df[(df["district"] == district) & (df["year"] <= last_year)]
        .sort_values("year")
        .copy()
    )
    if hist.empty:
        continue

    # 전년 기준값: 2022 실제값
    last_row = hist[hist["year"] == last_year]
    if last_row.empty:
        continue
    prev_val = float(last_row.iloc[0]["child_user"])

    # 이 구의 2023~2030 예측
    mask = (future_df["district"] == district)
    gu_future = future_df[mask].sort_values("year")

    for idx, row in gu_future.iterrows():
        raw = float(row["child_user_raw"])

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

        future_df.at[idx, "child_user"] = float(capped)
        prev_val = capped



# CSV 저장

future_df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

print("미래 예측 CSV 생성 완료:", OUTPUT_PATH)
print(future_df.head(10))