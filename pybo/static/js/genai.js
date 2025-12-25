document.addEventListener("DOMContentLoaded", function () {

    // 모델 설정 데이터
    const modelHistory = {
        base:  { max_steps: 0,   readonly: true,  msg: "미학습 모델: Llama-3 순정 상태입니다." },
        cp100: { max_steps: 100, readonly: true,  msg: "초기 학습: 말투가 조금씩 변하기 시작합니다." },
        cp200: { max_steps: 200, readonly: true,  msg: "중간 학습: 지시 이행 능력이 향상되었습니다." },
        final: { max_steps: 300, readonly: false, msg: "최종 모델: 300스텝 학습이 완료된 최적화 상태입니다." }
    };

    // UI 요소 변수 선언
    const reportForm = document.getElementById("reportForm");
    const resultSection = document.getElementById("resultSection");
    const loadingSpinner = document.getElementById("loadingSpinner");
    const aiTitle = document.getElementById("aiTitle");
    const aiSummary = document.getElementById("aiSummary");
    const aiContent = document.getElementById("aiContent");

    // 모델 교체 및 UI 업데이트 함수 (수정됨)
    async function updateModelSettingsUI() {
        const selected = document.querySelector('input[name="modelVersion"]:checked');
        const ver = selected ? selected.value : "final";
        const config = modelHistory[ver];
        const reportBtn = reportForm ? reportForm.querySelector("button[type='submit']") : null;

        // 서버에 모델 교체 요청
        if (reportBtn) {
            reportBtn.disabled = true;
            reportBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> 모델 전환 중...';
        }

        try {
            console.log(`서버 모델 교체 요청: ${ver}`);
            const switchResp = await fetch("/genai-api/switch-model", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ model_version: ver })
            });
            const switchData = await switchResp.json();
            if (switchData.success) {
                console.log(`모델 교체 성공: ${ver}`);
            }
        } catch (err) {
            console.error("모델 교체 중 오류:", err);
        } finally {
            if (reportBtn) {
                reportBtn.disabled = false;
                reportBtn.innerHTML = '<i class="bi bi-magic mr-2"></i> 보고서 생성';
            }
        }

        // 기존 UI 제어 로직
        const trainingInputs = [
            "max_steps", "evaluation_strategy", "save_strategy",
            "learning_rate", "optim", "weight_decay",
            "warmup_steps", "eval_steps", "save_steps", "logging_steps"
        ];

        trainingInputs.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.disabled = config.readonly;
                if (id === "max_steps") el.value = config.max_steps;
            }
        });

        const badge = document.querySelector(".badge-danger");
        if (badge) {
            let msgEl = document.getElementById("model-status-msg") || document.createElement("span");
            if (!msgEl.id) {
                msgEl.id = "model-status-msg";
                msgEl.className = "ml-3 small font-italic text-secondary";
                badge.parentNode.appendChild(msgEl);
            }
            msgEl.textContent = config.msg;
        }
    }

    // 상단 라디오 버튼 클릭 시 UI 업데이트 이벤트 연결
    document.querySelectorAll('input[name="modelVersion"]').forEach(radio => {
        radio.addEventListener('change', updateModelSettingsUI);
    });

    // 초기 로드 시 한 번 실행하여 상태 맞춤
    updateModelSettingsUI();

    function getModelVer() {
        return document.querySelector('input[name="modelVersion"]:checked')?.value || "final";
    }

    // 연도 선택 로직 (기존 유지)
    const startSelect = document.getElementById('startYear');
    const endSelect = document.getElementById('endYear');
    if (startSelect && endSelect) {
        function updateEndYearOptions() {
            const startVal = parseInt(startSelect.value);
            const currentEndVal = parseInt(endSelect.value);
            endSelect.innerHTML = "";
            for (let y = startVal; y <= 2030; y++) {
                const option = document.createElement("option");
                option.value = y; option.textContent = y + "년";
                endSelect.appendChild(option);
            }
            endSelect.value = (currentEndVal >= startVal) ? currentEndVal : startVal;
        }
        startSelect.addEventListener('change', updateEndYearOptions);
        updateEndYearOptions();
    }

    // 보고서 생성 (기존 유지)
    if (reportForm) {
        reportForm.addEventListener("submit", async function (e) {
            e.preventDefault();
            const modelVer = getModelVer();
            const reportBtn = reportForm.querySelector("button[type='submit']");

            if(resultSection) resultSection.style.display = "none";
            if(loadingSpinner) loadingSpinner.style.display = "block";
            if(reportBtn) { reportBtn.disabled = true; reportBtn.innerHTML = "생성 중..."; }

            try {
                const resp = await fetch("/genai-api/report", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        district: document.getElementById("regionSelect").value,
                        start_year: parseInt(document.getElementById("startYear").value),
                        end_year: parseInt(document.getElementById("endYear").value),
                        model_version: modelVer,
                        prompt: "report"
                    }),
                });
                const data = await resp.json();
                if (data.success) {
                    let parsedData = { title: "분석 결과", summary: "정보 없음", content: data.result };
                    try {
                        const cleanJson = data.result.replace(/```json/g, "").replace(/```/g, "").trim();
                        parsedData = JSON.parse(cleanJson);
                    } catch (err) { parsedData.content = data.result; }

                    aiTitle.textContent = parsedData.title || "분석 보고서";
                    aiSummary.textContent = parsedData.summary || "요약 없음";
                    aiContent.innerText = parsedData.content || "";
                    resultSection.style.display = "block";
                } else { alert(data.error || "오류 발생"); }
            } catch (err) { alert("서버 통신 오류"); }
            finally {
                loadingSpinner.style.display = "none";
                if(reportBtn) { reportBtn.disabled = false; reportBtn.innerHTML = "보고서 생성"; }
            }
        });
    }

    // 정책 제안 및 Q&A (기존 유지)
    const policyBtn = document.getElementById("policy-btn");
    if (policyBtn) {
        policyBtn.addEventListener("click", async function () {
            const input = document.getElementById("policy-input");
            const resultArea = document.getElementById("policyResultArea");
            if (!input.value.trim()) return;
            policyBtn.disabled = true;
            resultArea.style.display = "block";
            resultArea.textContent = "생성 중...";
            try {
                const resp = await fetch("/genai-api/policy", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ prompt: input.value, model_version: getModelVer() }),
                });
                const data = await resp.json();
                resultArea.textContent = data.success ? data.result : data.error;
            } finally { policyBtn.disabled = false; }
        });
    }

    const qaBtn = document.getElementById("qa-btn");
    if (qaBtn) {
        qaBtn.addEventListener("click", async function () {
            const input = document.getElementById("qa-input");
            const chat = document.getElementById("qa-chat-window");
            if (!input.value.trim()) return;
            const q = input.value;
            chat.innerHTML += `<div class="chat-bubble user-bubble">${q}</div>`;
            input.value = "";
            try {
                const resp = await fetch("/genai-api/qa", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ question: q, model_version: getModelVer() }),
                });
                const data = await resp.json();
                chat.innerHTML += `<div class="chat-bubble ai-bubble">${data.success ? data.result : "오류"}</div>`;
                chat.scrollTop = chat.scrollHeight;
            } catch (err) { console.error(err); }
        });
    }

    // 설정 저장
    const configForm = document.getElementById("configForm");
    if (configForm) {
        configForm.addEventListener("submit", async function (e) {
            e.preventDefault();
            if (getModelVer() !== "final") { alert("최종 모델 모드에서만 가능합니다."); return; }
            const payload = {
                temperature: parseFloat(document.getElementById("temperature").value),
                max_tokens: parseInt(document.getElementById("max_tokens").value),
                max_steps: parseInt(document.getElementById("max_steps").value),
                learning_rate: document.getElementById("learning_rate").value,
                optim: document.getElementById("optim").value
            };
            try {
                const resp = await fetch("/genai-api/config", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload),
                });
                const data = await resp.json();
                alert(data.success ? "저장 완료" : "오류");
            } catch (err) { alert("서버 통신 오류"); }
        });
    }
});