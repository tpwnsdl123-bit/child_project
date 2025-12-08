import os
import pandas as pd
import numpy as np
import joblib

from xgboost import XGBRegressor
from sklearn.model_selection import train_test_split, RandomizedSearchCV
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
ML_DIR   = os.path.join(BASE_DIR, "pybo", "ml")

os.makedirs(ML_DIR, exist_ok=True)


csv_path = os.path.join(DATA_DIR, "master_2015_2022.csv")
df = pd.read_csv(csv_path)

# district 원핫 인코딩
df = pd.get_dummies(df, columns=["district"], drop_first=False)

district_ohe_cols = [c for c in df.columns if c.startswith("district_")]


# Feature 설정
base_features = [
    "year",
    "single_parent",
    "basic_beneficiaries",
    "multicultural_hh",
    "academy_cnt",
    "grdp",
    "population"
]

features = base_features + district_ohe_cols
target = "child_user"

# Train/Test Split
train = df[df["year"] <= 2020]
test  = df[df["year"] >= 2021]

X_train = train[features]
y_train = train[target]

X_test = test[features]
y_test = test[target]

y_train_log=np.log1p(y_train)

# Hyperparameter Search
param_grid_local = {
    "max_depth": [4, 5, 6],
    "learning_rate": [0.03, 0.05, 0.07],
    "n_estimators": [600, 700, 800],
    "subsample": [0.5, 0.6, 0.7],
    "colsample_bytree": [0.5, 0.6, 0.7],
    "gamma": [0.1, 0.3, 0.5],
    "reg_lambda": [1.0, 1.5, 2.0],
    "reg_alpha": [0, 0.1, 0.3]
}

xgb_model_local = XGBRegressor(
    random_state=42,
    tree_method="hist"
)

search_local = RandomizedSearchCV(
    estimator=xgb_model_local,
    param_distributions=param_grid_local,
    n_iter=30,
    scoring="r2",
    cv=3,
    verbose=2,
    n_jobs=-1,
    random_state=42
)

search_local.fit(X_train, y_train_log)

best_xgb_local = XGBRegressor(
    **search_local.best_params_,
    random_state=42
)
best_xgb_local.fit(X_train, y_train_log)

best_xgb_local.district_ohe_cols = district_ohe_cols
best_xgb_local.base_features = base_features

pred_local_log = best_xgb_local.predict(X_test)
pred_local = np.expm1(pred_local_log)

print("TRAIN_ROWS:", X_train.shape[0])
print("TEST_ROWS :", X_test.shape[0])

print("FEATURE_COUNT:", len(features))

print("Best Params:", search_local.best_params_)
print("MAE :", mean_absolute_error(y_test, pred_local))
print("RMSE:", np.sqrt(mean_squared_error(y_test, pred_local)))
print("R² :", r2_score(y_test, pred_local))

MODEL_PATH = os.path.join(ML_DIR, "model_xgb.pkl")
joblib.dump(best_xgb_local, MODEL_PATH)

print(f"\n 모델 저장 완료 {MODEL_PATH}")
