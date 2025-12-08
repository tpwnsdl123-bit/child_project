import os
import joblib
import numpy as np

MODEL_PATH = os.path.join(os.path.dirname(__file__), "model_xgb.pkl")
model = joblib.load(MODEL_PATH)

base_features = getattr(model, "base_features", None)
district_ohe_cols = getattr(model, "district_ohe_cols", None)

if base_features is None or district_ohe_cols is None:
    raise RuntimeError(
        "model_xgb.pkl 에 base_features 또는 district_ohe_cols 속성이 없습니다. "
        "train_model.py 를 다시 실행해서 모델을 저장하세요."
    )

# 최종적으로 모델에 넣을 컬럼 순서
feature_cols = list(base_features) + list(district_ohe_cols)


def predict_child_user(input_data: dict) -> float:

    # 필수 키 체크
    required_keys = set(base_features) | {"district"}
    missing = [k for k in required_keys if k not in input_data]

    if missing:
        raise ValueError(f"필수 입력 누락: {', '.join(missing)}")

    # 숫자 피처 값 변환
    row = {}
    for col in base_features:
        try:
            row[col] = float(input_data[col])
        except (TypeError, ValueError):
            raise ValueError(
                f"입력 값이 숫자가 아닙니다: '{col}' = {input_data[col]!r}"
            )

    # district 원-핫 인코딩
    district_name = str(input_data["district"])

    if district_name == "전체":
        raise ValueError(
            "district 에는 실제 자치구 이름(예: '강남구')를 넣어야 합니다. '전체'는 사용할 수 없습니다."
        )

    for col in district_ohe_cols:
        gu_name = col.replace("district_", "")
        row[col] = 1.0 if gu_name == district_name else 0.0

    x = np.array([[row[c] for c in feature_cols]])

    # pred = model.predict(x)[0]
    # return float(pred)

    pred_log = model.predict(x)[0]
    pred = np.expm1(pred_log)
    return float(pred)
