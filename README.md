# Agentic AI를 활용한 지역아동센터 수요 예측 서비스

서울시 **자치구별 사회·인구·복지 지표**를 기반으로 **XGBoost 회귀 모델**로 지역아동센터 이용자 수를 예측하고, **LLM(Llama3) 및 RAG 기술**을 도입하여 정책 제안, 분석 보고서 생성, 법령 Q&A를 제공하는 지능형 웹 서비스입니다.

> **주요 업데이트**: 
> - 기존 예측 모델에 **Generative AI** 기능을 통합하여 단순 통계를 넘어선 **인사이트**를 제공합니다.
> - **MSA 지향적 구조** (Service 레이어 분리) 및 **Docker** 배포 환경을 지원합니다.

---

## 1. 프로젝트 구조

```text
flask_basic_oop/
 ├── data/
 │    ├── master_2015_2022.csv                # 학습용 관측 데이터
 │    ├── predicted_child_user_2023_2030.csv  # 예측 결과 데이터
 │    └── chroma_db/                          # RAG용 벡터 데이터베이스 (ChromaDB)
 │
 ├── pybo/
 │    ├── ml/                                 # 머신러닝 관련 (예측 모델)
 │    │    ├── model_xgb.pkl                  # 학습된 XGBoost 모델
 │    │    └── predictor.py
 │    │
 │    ├── service/                            # 비즈니스 로직 (Service Layer)
 │    │    ├── genai_service.py               # Llama3 연동 및 프롬프트 엔지니어링
 │    │    ├── rag_service.py                 # RAG (검색 증강 생성) 로직
 │    │    └── data_service.py                # 통계/예측 데이터 처리
 │    │
 │    ├── views/                              # API 엔드포인트 (Controller)
 │    │    ├── main_views.py                  # 페이지 라우팅
 │    │    ├── genai_views.py                 # 생성형 AI 관련 API (/genai-api)
 │    │    └── predict_views.py               # 수요 예측 API
 │    │
 │    ├── templates/                          # Jinja2 HTML 템플릿
 │    ├── static/                             # CSS, JS, Images
 │    └── models.py                           # DB 모델 (User, RegionForecast 등)
 │
 ├── docker-compose.yml                       # Docker 배포 설정
 ├── Dockerfile                               # Flask 앱 이미지 빌드 설정
 ├── requirements.web.txt                     # 웹 서비스용 경량 의존성
 ├── requirements.llm.txt                     # AI/RAG용 추가 의존성 (Torch, Transformers 등)
 ├── config.py                                # 환경 설정
 └── README.md                                # 프로젝트 문서
```

---

## 2. 주요 기능

### 2.1. 수요 예측 (Prediction)
- **알고리즘**: XGBoost Regressor
- **기능**: 2030년까지의 자치구별 지역아동센터 이용 아동 수 예측
- **활용**: 인프라 확충이 시급한 지역 식별

### 2.2. 지능형 분석 보고서 (AI Report)
- **모델**: Llama3 (RunPod Serverless Endpoint 연동)
- **기능**: 특정 자치구의 예측 데이터를 분석하여 "요약 - 원인 분석 - 추가 필요 데이터" 형태의 구조화된 보고서 자동 생성

### 2.3. 정책 제안 (Policy Idea)
- **기능**: 지역별 통계 특성을 바탕으로 맞춤형 아동 복지 정책 아이디어 3가지 제안
- **프롬프트**: 전문가 페르소나를 부여하여 구체적이고 실현 가능한 정책 도출

### 2.4. 법령/지침 Q&A (RAG Chatbot)
- **기술**: RAG (Retrieval-Augmented Generation)
- **데이터**: 서울시 아동복지 관련 법령 및 지침 문서 (PDF/Txt -> ChromaDB 임베딩)
- **기능**: 사용자의 질문에 대해 관련 법령을 검색(Retrieval)하여 근거 기반의 정확한 답변 생성

### 2.5. 텍스트 요약 (Summarization)
- **모델**: KoBART (Local Model)
- **기능**: 긴 정책 문서나 게시글 내용을 3줄 요약

---

## 3. 개발 및 배포 환경 설정

### 방법 A. Docker Compose (권장)
복잡한 환경 설정(Oracle DB, Python 패키지 등)을 한 번에 해결할 수 있습니다.

1. **Docker 실행**
   ```bash
   docker-compose up -d --build
   ```
   - Oracle XE 11g 데이터베이스와 Flask 애플리케이션 컨테이너가 실행됩니다.
   - DB 데이터는 `./oracle_data` 폴더에 영구 저장됩니다.

2. **접속**
   - 웹 서비스: `http://localhost:5000`
   - Oracle DB: `localhost:1521` (User: `child`, PW: `oracle` / 설정 참고)

### 방법 B. 로컬 개발 환경 (Manual)

1. **가상환경 생성 및 활성화**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Mac/Linux
   source venv/bin/activate
   ```

2. **패키지 설치**
   가벼운 웹 개발만 할 경우 `web`, AI 기능까지 개발할 경우 `llm`을 설치합니다.
   ```bash
   # 기본 웹 구동
   pip install -r requirements.web.txt
   
   # AI/RAG 기능 포함 (PyTorch 등 포함되어 설치 오래 걸림)
   pip install -r requirements.llm.txt
   ```

3. **환경 변수 설정 (.env)**
   프로젝트 루트에 `.env` 파일을 생성하고 키를 설정해야 AI 기능이 작동합니다.
   ```ini
   FLASK_APP=pybo
   FLASK_DEBUG=1
   RUNPOD_API_URL=https://api.runpod.ai/v2/YOUR_ENDPOINT_ID/runsync
   # 기타 DB 설정 등
   ```

4. **실행**
   ```bash
   flask run
   ```

---

## 4. API 명세 (GenAI)

AI 기능은 `/genai-api` 접두사를 가집니다.

| 기능 | Method | 엔드포인트 | 중요 파라미터 |
|------|--------|------------|---------------|
| **분석 보고서** | POST | `/genai-api/report` | `district` (자치구명), `start_year`, `end_year` |
| **정책 제안** | POST | `/genai-api/policy` | `district` (자치구명), `prompt` (추가요청) |
| **AI Q&A** | POST | `/genai-api/qa` | `question` (사용자 질문) |
| **텍스트 요약** | POST | `/genai-api/summarize` | `text` (원문) |
| **모델 설정** | POST | `/genai-api/config` | `temperature`, `max_tokens` |

---

## 5. 향후 계획
- [ ] LLM 모델 답변 고도화
- [ ] Llama3 파인튜닝
- [ ] RAG 품질 개선
- [ ] 머신러닝 변수 데이터 추가 예측 결과 품질 향상 