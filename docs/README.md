# Agentic AI를 활용한 지역아동센터 수요 예측 서비스

서울시 **자치구별 사회·인구·복지 지표**를 기반으로  
**XGBoost 회귀 모델**로 지역아동센터 이용자 수(2015~2030)를 예측하고,  
예측 결과를 **Flask + Oracle DB + 웹 UI**로 제공하는 서비스입니다.

> 현재 저장소는 **1차 프로젝트 결과물**로,  
> 데이터 전처리 → 모델 학습 → DB 적재 → 대시보드/예측 UI 연동까지 완료된 상태입니다.  
> 2차 프로젝트에서 Agentic AI / LLM 기반 지원 기능을 추가할 예정입니다.

---

## 1. 프로젝트 구조

```text
flask_basic/
 ├── data/
 │    ├── master_2015_2022.csv                # 실제 관측 데이터 (2015~2022)
 │    └── predicted_child_user_2023_2030.csv  # XGBoost 예측값 (2023~2030)
 │
 ├── pybo/
 │    ├── ml/
 │    │    ├── model_xgb.pkl        # 학습 완료된 XGBoost 모델
 │    │    ├── predictor.py         # /predict API에서 사용하는 예측 함수
 │    │    └── future_predict.py    # 2023~2030 예측 CSV 생성 스크립트
 │    │
 │    ├── static/
 │    │    ├── style.css            # 전체 공통 스타일
 │    │    ├── bootstrap-icons.css  # 아이콘 폰트 스타일
 │    │    ├── fonts/
 │    │    │    ├── bootstrap-icons.woff
 │    │    │    └── bootstrap-icons.woff2
 │    │    └── images/
 │    │         └── Seoul_districts.svg   # 자치구별 SVG 지도
 │    │
 │    ├── templates/
 │    │    ├── base.html             # 공통 레이아웃(헤더/푸터/네비게이션)
 │    │    ├── main/
 │    │    │    ├── introduce.html   # 프로젝트 소개 페이지
 │    │    │    ├── dashboard.html   # 통계 대시보드(연도/자치구별 지표 시각화)
 │    │    │    └── predict.html     # 예측 결과 + 서울 지도 시각화
 │    │    ├── question/
 │    │    │    └── qna.html         # Q&A 게시판 화면
 │    │    └── partials/
 │    │         └── seoul_map.svg    # 템플릿에서 include하는 SVG 지도 파셜
 │    │
 │    ├── views/
 │    │    ├── main_views.py         # 메인/소개/대시보드/예측 페이지 라우팅
 │    │    ├── predict_views.py      # POST /predict API 엔드포인트
 │    │    ├── data_views.py         # /data/* 통계/테스트용 API
 │    │    └── question_views.py     # Q&A 게시판 관련 라우팅
 │    │
 │    ├── models.py                  # SQLAlchemy 모델 정의
 │    ├── __init__.py                # create_app() Flask App Factory
 │    └── ...
 │
 ├── insert_region_data.py           # 2015~2022 데이터 Oracle DB 삽입
 ├── insert_future_region_data.py    # 2023~2030 예측 데이터 DB 삽입
 ├── train_model.py                  # 모델 학습 및 model_xgb.pkl 저장
 ├── check_db.py                     # DB 상태/레코드 수 점검용 유틸
 │
 ├── migrations/                     # Flask-Migrate(Alembic) 마이그레이션 파일
 │    └── README                     # (자동 생성) Single-database configuration for Flask.
 │
 ├── .flaskenv                       # Flask 환경 변수 설정 (FLASK_APP 등)
 ├── .gitignore                      # Git 제외 파일 설정
 ├── requirements.txt                # Python 패키지 의존성 리스트
 ├── config.py                       # Flask / SQLAlchemy / Oracle 설정
 └── README.md                       # (현재 문서)

2. 개발환경 세팅
2-1. 가상환경 생성
# (Windows 기준)
python -m venv venv
venv\Scripts\activate

2-2. 패키지 설치
pip install -r requirements.txt

2-3. Oracle XE 준비

서비스명: xe

유저: child

비밀번호: child1234

config.py / .flaskenv 에서 SQLALCHEMY_DATABASE_URI가 다음과 같이 설정되어야 합니다.

oracle+cx_oracle://child:child1234@localhost:1521/xe

3. 데이터 & DB 초기 세팅
3-1. 실제 데이터 삽입 (2015~2022)
python insert_region_data.py

3-2. 미래 예측 CSV 생성 (2023~2030)
python pybo/ml/future_predict.py


master_2015_2022.csv를 기반으로 XGBoost 모델을 사용하여
predicted_child_user_2023_2030.csv를 생성합니다.

3-3. 미래 예측 데이터 DB 삽입
python insert_future_region_data.py


CSV에 있는 2023~2030 자치구별 예측값을 Oracle DB에 적재합니다.

이후 웹 대시보드/예측 페이지는 DB에서 직접 조회해서 사용합니다.

4. 모델 재학습 (선택)

새로운 데이터나 피처를 추가한 뒤 모델을 다시 학습하려면:

python train_model.py


학습 완료 후 모델은 자동으로 pybo/ml/model_xgb.pkl로 저장됩니다.

predictor.py에서 이 파일을 로드하여 /predict API에서 사용합니다.

5. Flask 서버 실행

.flaskenv 덕분에 FLASK_APP 등은 자동 설정됩니다.

flask run

주요 URL

메인 페이지 / 소개 / 대시보드 / 예측

http://127.0.0.1:5000/

테스트용 데이터 API

http://127.0.0.1:5000/data/test

예측 API

POST http://127.0.0.1:5000/predict

6. 예측 API 명세 (Frontend 용)
✔ 엔드포인트
POST /predict
Content-Type: application/json

요청(JSON)
{
  "single_parent": 1500,
  "basic_beneficiaries": 8000,
  "multicultural_hh": 2000,
  "academy_cnt": 120.5,
  "grdp": 18000000
}


각 필드는 다음을 의미합니다.

single_parent : 자치구별 한부모 가구 수

basic_beneficiaries : 기초생활수급자 수

multicultural_hh : 다문화 가구 수

academy_cnt : 사설 학원 수

grdp : 지역 총소득(또는 1인당 GRDP 기반 지표)

응답(JSON)
{
  "success": true,
  "prediction": 1234.56
}


prediction : 입력 피처를 기반으로 예측된 지역아동센터 이용자 수

7. 유틸 스크립트
데이터베이스 상태 점검
python check_db.py


DB 연결 상태, 주요 테이블 레코드 수 등을 확인하는 용도입니다.

8. 향후 계획 (2차 프로젝트)

Agentic AI / LLM 연동