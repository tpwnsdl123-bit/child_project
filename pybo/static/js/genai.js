document.addEventListener("DOMContentLoaded", function () {
    // 보고서 생성 탭
    const reportInput = document.getElementById("report-input");
    const reportBtn = document.getElementById("report-generate-btn");
    const reportResultBox = document.getElementById("report-result");

    if (reportBtn && reportInput && reportResultBox) {
        reportBtn.addEventListener("click", async function () {
            const text = (reportInput.value || "").trim();

            if (!text) {
                alert("요청 내용을 입력해 주세요.");
                reportInput.focus();
                return;
            }

            reportBtn.disabled = true;
            const originalText = reportBtn.innerText;
            reportBtn.innerText = "생성 중...";
            reportResultBox.textContent = "보고서를 생성하는 중입니다...";

            try {
                const resp = await fetch("/genai-api/report", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({ prompt: text }),
                });

                const data = await resp.json();

                if (data.success) {
                    reportResultBox.textContent = data.result;
                } else {
                    reportResultBox.textContent =
                        data.error || "보고서 생성 중 오류가 발생했습니다.";
                }
            } catch (err) {
                console.error(err);
                reportResultBox.textContent =
                    "요청 처리 중 오류가 발생했습니다.";
            } finally {
                reportBtn.disabled = false;
                reportBtn.innerText = originalText;
            }
        });
    }

    // 정책 아이디어 탭
    const policyInput = document.getElementById("policy-input");
    const policyBtn = document.getElementById("policy-generate-btn");
    const policyResultBox = document.getElementById("policy-result");

    if (policyBtn && policyInput && policyResultBox) {
        policyBtn.addEventListener("click", async function () {
            const text = (policyInput.value || "").trim();

            if (!text) {
                alert("요청 내용을 입력해 주세요.");
                policyInput.focus();
                return;
            }

            policyBtn.disabled = true;
            const originalText = policyBtn.innerText;
            policyBtn.innerText = "생성 중...";
            policyResultBox.textContent = "정책 아이디어를 생성하는 중입니다...";

            try {
                const resp = await fetch("/genai-api/policy", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({ prompt: text }),
                });

                const data = await resp.json();

                if (data.success) {
                    policyResultBox.textContent = data.result;
                } else {
                    policyResultBox.textContent =
                        data.error || "정책 아이디어 생성 중 오류가 발생했습니다.";
                }
            } catch (err) {
                console.error(err);
                policyResultBox.textContent =
                    "요청 처리 중 오류가 발생했습니다.";
            } finally {
                policyBtn.disabled = false;
                policyBtn.innerText = originalText;
            }
        });
    }
});

// 지표 설명 생성
const explainInput = document.getElementById("explain-input");
const explainBtn = document.getElementById("explain-generate-btn");
const explainResult = document.getElementById("explain-result");

if (explainBtn && explainInput && explainResult) {
    explainBtn.addEventListener("click", async () => {
        const text = explainInput.value.trim();
        if (!text) {
            explainResult.innerText = "지표나 질문을 입력해 주세요.";
            return;
        }

        explainResult.innerText = "생성 중...";

        try {
            const resp = await fetch("/genai-api/explain", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ prompt: text }),
            });

            const data = await resp.json();

            if (data.success) {
                explainResult.innerText = data.result || "(응답이 비어 있습니다.)";
            } else {
                explainResult.innerText = data.error || "지표 설명 생성 중 오류가 발생했습니다.";
            }
        } catch (err) {
            console.error(err);
            explainResult.innerText = "서버 통신 중 오류가 발생했습니다.";
        }
    });
}

// NER 분석
const nerInput = document.getElementById("ner-input");
const nerBtn = document.getElementById("ner-generate-btn");
const nerResult = document.getElementById("ner-result");

if (nerInput && nerBtn && nerResult) {
    nerBtn.addEventListener("click", async () => {
        const text = nerInput.value.trim();
        if (!text) {
            nerResult.innerText = "분석할 문장을 입력해 주세요.";
            return;
        }

        nerResult.innerText = "분석 중...";

        try {
            const resp = await fetch("/genai-api/ner", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ text: text }),
            });

            const data = await resp.json();

            if (!data.success) {
                nerResult.innerText =
                    data.error || "NER 분석 중 오류가 발생했습니다.";
                return;
            }

            const items = data.items || [];
            if (items.length === 0) {
                nerResult.innerText = "인식된 개체명이 없습니다.";
                return;
            }

            // 간단한 리스트 HTML로 렌더링
            let html = "<ul class=\"mb-0\">";
            for (const ent of items) {
                const word = ent.word || "";
                const type = ent.type || "";
                const score = ent.score != null ? ent.score.toFixed(4) : "";
                html += `<li><strong>${word}</strong> (${type}) - score: ${score}</li>`;
            }
            html += "</ul>";
            nerResult.innerHTML = html;
        } catch (err) {
            console.error(err);
            nerResult.innerText = "서버 통신 중 오류가 발생했습니다.";
        }
    });
}

// AI Q&A
const qaInput = document.getElementById("qa-input");
const qaBtn = document.getElementById("qa-generate-btn");
const qaResult = document.getElementById("qa-result");

if (qaInput && qaBtn && qaResult) {
    qaBtn.addEventListener("click", async () => {
        const question = qaInput.value.trim();
        if (!question) {
            qaResult.innerText = "질문을 입력해 주세요.";
            return;
        }

        qaResult.innerText = "생성 중...";

        try {
            const resp = await fetch("/genai-api/qa", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    question: question,
                    page: "genai"
                }),
            });

            const data = await resp.json();

            if (data.success) {
                qaResult.innerText = data.result || "(응답이 비어 있습니다.)";
            } else {
                qaResult.innerText = data.error || "AI Q&A 생성 중 오류가 발생했습니다.";
            }
        } catch (err) {
            console.error(err);
            qaResult.innerText = "서버 통신 중 오류가 발생했습니다.";
        }
    });
}

