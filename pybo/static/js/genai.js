document.addEventListener("DOMContentLoaded", function () {

    // 연도 선택 스마트 로직 (시작 연도에 따라 종료 연도 자동 변경)
    const startSelect = document.getElementById('startYear');
    const endSelect = document.getElementById('endYear');
    const MAX_YEAR = 2030;

    if (startSelect && endSelect) {
        function updateEndYearOptions() {
            const startVal = parseInt(startSelect.value);
            const currentEndVal = parseInt(endSelect.value);

            endSelect.innerHTML = "";

            for (let y = startVal; y <= MAX_YEAR; y++) {
                const option = document.createElement("option");
                option.value = y;
                option.textContent = y + "년";
                endSelect.appendChild(option);
            }

            if (!isNaN(currentEndVal) && currentEndVal >= startVal) {
                endSelect.value = currentEndVal;
            } else {
                endSelect.value = startVal;
            }
        }
        startSelect.addEventListener('change', updateEndYearOptions);
        updateEndYearOptions();
    }

    // 보고서 생성 탭
    const reportForm = document.getElementById("reportForm");
    const resultSection = document.getElementById("resultSection");
    const loadingSpinner = document.getElementById("loadingSpinner");
    const aiTitle = document.getElementById("aiTitle");
    const aiSummary = document.getElementById("aiSummary");
    const aiContent = document.getElementById("aiContent");

    if (reportForm) {
        reportForm.addEventListener("submit", async function (e) {
            e.preventDefault();

            const region = document.getElementById("regionSelect").value;
            const startYearVal = document.getElementById("startYear").value;
            const endYearVal = document.getElementById("endYear").value;
            const reportBtn = reportForm.querySelector("button[type='submit']");

            // 유효성 검사
            if (parseInt(startYearVal) > parseInt(endYearVal)) {
                alert("시작 연도는 종료 연도보다 클 수 없습니다.");
                return;
            }

            // UI 초기화
            if(resultSection) resultSection.style.display = "none";
            if(loadingSpinner) loadingSpinner.style.display = "block";
            if(reportBtn) {
                reportBtn.disabled = true;
                reportBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> 생성 중...';
            }

            try {
                const resp = await fetch("/genai-api/report", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        district: region,
                        start_year: parseInt(startYearVal),
                        end_year: parseInt(endYearVal),
                        prompt: "report"
                    }),
                });

                const data = await resp.json();

                if (data.success) {
                    let parsedData = { title: "분석 결과", summary: "요약 정보 없음", content: data.result };
                    try {
                        let cleanJson = data.result.replace(/```json/g, "").replace(/```/g, "").trim();
                        parsedData = JSON.parse(cleanJson);
                    } catch (err) {
                        console.warn("JSON 파싱 실패:", err);
                        parsedData.content = data.result;
                    }

                    if(aiTitle) aiTitle.textContent = parsedData.title || "분석 보고서";
                    if(aiSummary) aiSummary.textContent = parsedData.summary || "요약된 내용이 없습니다.";
                    if(aiContent) aiContent.innerText = parsedData.content || "";

                    if(loadingSpinner) loadingSpinner.style.display = "none";
                    if(resultSection) resultSection.style.display = "block";

                } else {
                    alert(data.error || "오류가 발생했습니다.");
                    if(loadingSpinner) loadingSpinner.style.display = "none";
                }
            } catch (err) {
                console.error(err);
                alert("서버 통신 중 오류가 발생했습니다.");
                if(loadingSpinner) loadingSpinner.style.display = "none";
            } finally {
                if(reportBtn) {
                    reportBtn.disabled = false;
                    reportBtn.innerHTML = '<i class="bi bi-magic"></i> 보고서 생성';
                }
            }
        });
    }

    // [정책 아이디어 탭]
    const policyBtn = document.getElementById("policy-btn");
    const policyInput = document.getElementById("policy-input");
    const policyResultBox = document.getElementById("policy-result");

    if (policyBtn && policyInput && policyResultBox) {
        policyBtn.addEventListener("click", async function () {
            const text = (policyInput.value || "").trim();
            if (!text) { alert("요청 내용을 입력해 주세요."); policyInput.focus(); return; }

            policyBtn.disabled = true;
            const originalText = policyBtn.innerHTML;
            policyBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> 생성 중...';
            policyResultBox.textContent = "정책 아이디어를 생성하고 있습니다...";

            try {
                const resp = await fetch("/genai-api/policy", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ prompt: text }),
                });
                const data = await resp.json();

                if (data.success) policyResultBox.textContent = data.result;
                else policyResultBox.textContent = data.error || "오류 발생";

            } catch (err) {
                console.error(err);
                policyResultBox.textContent = "서버 통신 오류";
            } finally {
                policyBtn.disabled = false;
                policyBtn.innerHTML = originalText;
            }
        });
    }

    // Q&A 탭
    const qaBtn = document.getElementById("qa-btn");
    const qaInput = document.getElementById("qa-input");
    const qaResult = document.getElementById("qa-result");

    if (qaBtn && qaInput && qaResult) {
        qaBtn.addEventListener("click", async function () {
            const question = qaInput.value.trim();
            if (!question) { alert("질문을 입력해 주세요."); qaInput.focus(); return; }

            qaBtn.disabled = true;
            const originalText = qaBtn.innerHTML;
            qaBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> 답변 중...';
            qaResult.textContent = "데이터를 분석하여 답변을 생성 중입니다...";

            try {
                const resp = await fetch("/genai-api/qa", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ question: question }),
                });
                const data = await resp.json();

                if (data.success) qaResult.textContent = data.result;
                else qaResult.textContent = data.error || "오류 발생";

            } catch (err) {
                console.error(err);
                qaResult.textContent = "서버 통신 오류";
            } finally {
                qaBtn.disabled = false;
                qaBtn.innerHTML = originalText;
            }
        });
    }

    const configForm = document.getElementById("configForm");

    if (configForm) {
        configForm.addEventListener("submit", async function (e) {
            e.preventDefault();

            const payload = {
                // [추론 파라미터]
                temperature: parseFloat(document.getElementById("temperature").value) || 0.35,
                max_tokens: parseInt(document.getElementById("max_tokens").value) || 600,

                // [학습 파라미터 - 요청하신 10개 항목]
                max_steps: parseInt(document.getElementById("max_steps").value),
                evaluation_strategy: document.getElementById("evaluation_strategy").value,
                save_strategy: document.getElementById("save_strategy").value,

                learning_rate: document.getElementById("learning_rate").value,
                optim: document.getElementById("optim").value,
                weight_decay: parseFloat(document.getElementById("weight_decay").value),

                warmup_steps: parseInt(document.getElementById("warmup_steps").value),
                eval_steps: parseInt(document.getElementById("eval_steps").value),
                save_steps: parseInt(document.getElementById("save_steps").value),
                logging_steps: parseInt(document.getElementById("logging_steps").value)
            };

            const btn = configForm.querySelector("button[type='submit']");
            const alertBox = document.getElementById("configAlert");

            btn.disabled = true;
            btn.innerHTML = '<i class="bi bi-hourglass-split"></i> 저장 중...';

            try {
                const resp = await fetch("/genai-api/config", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload),
                });
                const data = await resp.json();

                if (data.success) {
                    alertBox.style.display = "block";
                    alertBox.className = "alert alert-success text-center";
                    alertBox.textContent = "✅ 설정 파일(training_config.json)이 생성되었습니다!";
                    setTimeout(() => { alertBox.style.display = "none"; }, 3000);
                } else {
                    alert("오류: " + data.error);
                }
            } catch (err) {
                console.error(err);
                alert("서버 통신 오류");
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<i class="bi bi-save"></i> 설정 저장 및 Config 파일 생성';
            }
        });
    }
});