const form = document.getElementById("profileForm");
const saveProfileButton = document.getElementById("saveProfileButton");
const loadSeedButton = document.getElementById("loadSeedButton");
const toggleJsonButton = document.getElementById("toggleJsonButton");
const profileJsonPreview = document.getElementById("profileJsonPreview");
const uploadForm = document.getElementById("uploadForm");
const runAutofillButton = document.getElementById("runAutofillButton");
const uploadStatus = document.getElementById("uploadStatus");
const uploadResultSummary = document.getElementById("uploadResultSummary");
const progressCard = document.getElementById("uploadProgressCard");
const progressBarFill = document.getElementById("progressBarFill");
const progressPercent = document.getElementById("progressPercent");
const progressStage = document.getElementById("progressStage");
const progressMeta = document.getElementById("progressMeta");
const progressElapsed = document.getElementById("progressElapsed");
const progressEta = document.getElementById("progressEta");
const progressSteps = Array.from(document.querySelectorAll(".progress-step"));
const downloadButtons = document.getElementById("downloadButtons");
const downloadHint = document.getElementById("downloadHint");
const renderedDraft = document.getElementById("renderedDraft");
const filledResultMeta = document.getElementById("filledResultMeta");
const liveFillPreview = document.getElementById("liveFillPreview");
const answerList = document.getElementById("answerList");
const missingBlock = document.getElementById("missingBlock");
const missingList = document.getElementById("missingList");
const documentPreview = document.getElementById("documentPreview");
const documentMeta = document.getElementById("documentMeta");
const llmStatus = document.getElementById("llmStatus");
const modelName = document.getElementById("modelName");
const modelSelect = document.getElementById("modelSelect");
const modelDescription = document.getElementById("modelDescription");
const profileStatus = document.getElementById("profileStatus");

const STAGE_ORDER = ["queued", "parse_document", "generate_ai", "export_result", "completed"];
let currentJobToken = 0;
let liveFillAnimationToken = 0;

function splitCommaValues(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function formatDuration(seconds) {
  const rounded = Math.max(0, Math.round(Number(seconds || 0)));
  const minutes = Math.floor(rounded / 60);
  const remain = rounded % 60;
  if (minutes <= 0) {
    return `${remain}초`;
  }
  return `${minutes}분 ${remain}초`;
}

function stageGroup(stageCode) {
  if (["queued"].includes(stageCode)) {
    return "queued";
  }
  if (["parse_document", "store_document"].includes(stageCode)) {
    return "parse_document";
  }
  if (["generate_ai"].includes(stageCode)) {
    return "generate_ai";
  }
  if (["export_result", "save_history"].includes(stageCode)) {
    return "export_result";
  }
  if (["completed"].includes(stageCode)) {
    return "completed";
  }
  return "queued";
}

function updateProgressSteps(stageCode, status) {
  const activeGroup = stageGroup(stageCode);
  const activeIndex = STAGE_ORDER.indexOf(activeGroup);

  for (const step of progressSteps) {
    const group = step.dataset.stageGroup;
    const stepIndex = STAGE_ORDER.indexOf(group);
    step.classList.remove("is-active", "is-complete", "is-failed");

    if (status === "failed") {
      if (stepIndex < activeIndex) {
        step.classList.add("is-complete");
      } else if (stepIndex === activeIndex) {
        step.classList.add("is-failed");
      }
      continue;
    }

    if (stepIndex < activeIndex) {
      step.classList.add("is-complete");
    } else if (stepIndex === activeIndex) {
      step.classList.add(status === "completed" ? "is-complete" : "is-active");
    }
  }
}

function renderProgress(job) {
  if (!job) {
    progressCard.setAttribute("hidden", "");
    return;
  }

  progressCard.removeAttribute("hidden");
  progressCard.dataset.state = job.status || "queued";

  const progressValue = Math.max(0, Math.min(100, Number(job.progress || 0)));
  progressBarFill.style.width = `${progressValue}%`;
  progressPercent.textContent = `${progressValue}%`;
  progressStage.textContent = job.stage_label || "처리 중";
  progressMeta.textContent = job.original_name
    ? `${job.original_name} · ${job.status === "completed" ? "완료" : job.status === "failed" ? "실패" : "진행 중"}`
    : (job.status === "completed" ? "완료" : job.status === "failed" ? "실패" : "진행 중");
  progressElapsed.textContent = `경과 ${formatDuration(job.elapsed_seconds)}`;

  if (job.status === "completed") {
    progressEta.textContent = "작업이 완료되었습니다.";
  } else if (job.status === "failed") {
    progressEta.textContent = job.detail || "작업 중 오류가 발생했습니다.";
  } else if (job.estimated_remaining_seconds != null) {
    progressEta.textContent = `예상 남은 시간 약 ${formatDuration(job.estimated_remaining_seconds)}`;
  } else {
    progressEta.textContent = "예상 시간을 초과했지만 계속 처리 중입니다.";
  }

  updateProgressSteps(job.stage_code || "queued", job.status || "queued");
}

function collectProfileForm() {
  return {
    "이름": form.elements["이름"].value.trim(),
    "생년월일": form.elements["생년월일"].value.trim(),
    "나이": form.elements["나이"].value.trim(),
    "취미": splitCommaValues(form.elements["취미"].value),
    "경력": form.elements["경력"].value.trim(),
    "기술스택": splitCommaValues(form.elements["기술스택"].value),
    "이메일": form.elements["이메일"].value.trim(),
    "전화번호": form.elements["전화번호"].value.trim(),
    "주소": form.elements["주소"].value.trim(),
    "학력": {
      "대학교": form.elements["학력.대학교"].value.trim(),
      "전공": form.elements["학력.전공"].value.trim(),
      "학점": form.elements["학력.학점"].value.trim(),
      "졸업년도": form.elements["학력.졸업년도"].value.trim(),
    },
    "자격증": splitCommaValues(form.elements["자격증"].value),
    "희망직무": form.elements["희망직무"].value.trim(),
    "추가메모": form.elements["추가메모"].value.trim(),
  };
}

function populateProfileForm(profile) {
  const data = profile || {};
  const education = data["학력"] || {};
  form.elements["이름"].value = data["이름"] || "";
  form.elements["생년월일"].value = data["생년월일"] || "";
  form.elements["나이"].value = data["나이"] || "";
  form.elements["취미"].value = (data["취미"] || []).join(", ");
  form.elements["경력"].value = data["경력"] || "";
  form.elements["기술스택"].value = (data["기술스택"] || []).join(", ");
  form.elements["이메일"].value = data["이메일"] || "";
  form.elements["전화번호"].value = data["전화번호"] || "";
  form.elements["주소"].value = data["주소"] || "";
  form.elements["학력.대학교"].value = education["대학교"] || "";
  form.elements["학력.전공"].value = education["전공"] || "";
  form.elements["학력.학점"].value = education["학점"] || "";
  form.elements["학력.졸업년도"].value = education["졸업년도"] || "";
  form.elements["자격증"].value = (data["자격증"] || []).join(", ");
  form.elements["희망직무"].value = data["희망직무"] || "";
  form.elements["추가메모"].value = data["추가메모"] || "";
  profileJsonPreview.textContent = JSON.stringify(data, null, 2);
}

function renderState(payload) {
  populateProfileForm(payload.profile || {});
  renderModelSelector(payload.llm || {});
  llmStatus.textContent = payload.llm.available
    ? payload.llm.installed
      ? "연결됨"
      : "서버 연결됨 / 모델 미설치"
    : "미연결";
  profileStatus.textContent = payload.profile && payload.profile["이름"]
    ? `${payload.profile["이름"]} 저장됨`
    : "저장된 프로필 없음";
}

function renderModelSelector(llm) {
  const options = Array.isArray(llm.model_options) ? llm.model_options : [];
  const currentModel = llm.model || "";
  modelName.textContent = currentModel || "-";
  modelSelect.innerHTML = "";

  if (!options.length) {
    const option = document.createElement("option");
    option.value = currentModel;
    option.textContent = currentModel || "모델 없음";
    modelSelect.appendChild(option);
    modelSelect.disabled = true;
    modelDescription.textContent = llm.available
      ? "선택 가능한 로컬 모델이 없습니다."
      : "Ollama 서버에 연결할 수 없습니다.";
    return;
  }

  modelSelect.disabled = false;
  let selectedOption = options.find((item) => item.selected) || options.find((item) => item.name === currentModel) || options[0];

  for (const item of options) {
    const option = document.createElement("option");
    option.value = item.name;
    option.textContent = `${item.label} · ${item.name}`;
    option.dataset.description = item.description || "";
    modelSelect.appendChild(option);
  }

  modelSelect.value = selectedOption.name;
  modelDescription.textContent = selectedOption.description || "Ollama에 설치된 로컬 모델입니다.";
}

async function selectModel(model) {
  if (!model) {
    return;
  }

  const previous = modelName.textContent;
  modelSelect.disabled = true;
  modelDescription.textContent = "모델을 변경하는 중입니다.";

  const response = await fetch("/api/llm/model", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ model }),
  });
  const payload = await response.json();

  if (!response.ok) {
    alert(payload.detail || payload.error || "모델 변경에 실패했습니다.");
    modelSelect.value = previous;
    await fetchState();
    return;
  }

  renderState(payload);
}

function renderDownloadButtons(downloads) {
  downloadButtons.innerHTML = "";
  if (!downloads || !downloads.length) {
    downloadHint.textContent = "다운로드 가능한 결과 파일이 없습니다.";
    return;
  }

  downloadHint.textContent = "생성된 결과 문서를 다운로드할 수 있습니다.";
  for (const file of downloads) {
    const anchor = document.createElement("a");
    anchor.href = file.download_url;
    anchor.download = file.download_name;
    anchor.className = "download-button";
    anchor.textContent = file.label;
    downloadButtons.appendChild(anchor);
  }
}

function resetLiveFillPreview(message = "업로드하면 원본 문항을 읽고 채워지는 과정을 표시합니다.") {
  liveFillAnimationToken += 1;
  liveFillPreview.innerHTML = "";
  const empty = document.createElement("div");
  empty.className = "live-fill-empty";
  empty.textContent = message;
  liveFillPreview.appendChild(empty);
}

function renderLiveStatus(title, message, docInfo) {
  liveFillAnimationToken += 1;
  liveFillPreview.innerHTML = "";

  const shell = document.createElement("div");
  shell.className = "live-document";

  const header = document.createElement("div");
  header.className = "live-document-head";

  const heading = document.createElement("strong");
  heading.textContent = title;

  const meta = document.createElement("span");
  meta.textContent = docInfo
    ? `${docInfo.original_name || "업로드 문서"} · ${(docInfo.character_count || 0).toLocaleString()} chars`
    : "처리 중";

  header.appendChild(heading);
  header.appendChild(meta);

  const body = document.createElement("p");
  body.className = "live-document-message";
  body.textContent = message;

  shell.appendChild(header);
  shell.appendChild(body);
  liveFillPreview.appendChild(shell);
}

function renderPendingFieldPreview(docInfo) {
  liveFillAnimationToken += 1;
  liveFillPreview.innerHTML = "";

  const fields = Array.isArray(docInfo?.fields) ? docInfo.fields : [];
  const shell = document.createElement("div");
  shell.className = "live-document";

  const header = document.createElement("div");
  header.className = "live-document-head";

  const heading = document.createElement("strong");
  heading.textContent = "원본 양식 분석 완료";

  const meta = document.createElement("span");
  meta.textContent = `${docInfo?.original_name || "업로드 문서"} · ${fields.length}개 후보`;

  header.appendChild(heading);
  header.appendChild(meta);
  shell.appendChild(header);

  if (!fields.length) {
    const message = document.createElement("p");
    message.className = "live-document-message";
    message.textContent = "문서 텍스트는 읽었지만 화면에 표시할 문항 후보가 적습니다. AI 답변 생성 후 결과를 표시합니다.";
    shell.appendChild(message);
    liveFillPreview.appendChild(shell);
    return;
  }

  const list = document.createElement("div");
  list.className = "live-field-list";

  fields.forEach((field, index) => {
    const row = document.createElement("article");
    row.className = "live-field";
    if (index === 0) {
      row.classList.add("is-filling");
    }

    const rowHead = document.createElement("div");
    rowHead.className = "live-field-head";

    const label = document.createElement("strong");
    label.textContent = field.label || `문항 후보 ${index + 1}`;

    const state = document.createElement("span");
    state.textContent = index === 0 ? "AI 분석 중" : "대기";

    rowHead.appendChild(label);
    rowHead.appendChild(state);

    const answer = document.createElement("div");
    answer.className = "live-field-answer is-pending";
    answer.textContent = "AI 답변 생성 대기 중";

    row.appendChild(rowHead);
    row.appendChild(answer);
    list.appendChild(row);
  });

  shell.appendChild(list);
  liveFillPreview.appendChild(shell);
}

function renderJobLivePreview(job) {
  if (!job) {
    return;
  }

  const livePreview = job.live_preview || null;
  if (livePreview && livePreview.phase === "document_ready") {
    renderPendingFieldPreview(livePreview.document);
    return;
  }

  if (job.stage_code === "parse_document" || job.stage_code === "store_document") {
    renderLiveStatus("원본 문서 읽는 중", job.message || "업로드 문서의 텍스트와 양식 구조를 추출하고 있습니다.");
    return;
  }

  if (job.stage_code === "generate_ai") {
    renderLiveStatus("AI 답변 생성 중", job.message || "문항별 답변 초안을 생성하고 있습니다.");
  }
}

function renderLiveFillBoard(payload, activeIndex = -1) {
  const answers = payload.autofill_result?.answers || [];
  const summary = payload.autofill_summary || {};
  const docInfo = payload.document || {};

  liveFillPreview.innerHTML = "";

  const board = document.createElement("div");
  board.className = "live-document";

  const header = document.createElement("div");
  header.className = "live-document-head";

  const title = document.createElement("strong");
  title.textContent = docInfo.original_name || "업로드 문서";

  const meta = document.createElement("span");
  meta.textContent = `${summary.document_type || "문서"} · ${answers.length}개 항목`;

  header.appendChild(title);
  header.appendChild(meta);
  board.appendChild(header);

  if (!answers.length) {
    const empty = document.createElement("div");
    empty.className = "live-fill-empty";
    empty.textContent = "AI가 채울 수 있는 항목을 찾지 못했습니다.";
    board.appendChild(empty);
    liveFillPreview.appendChild(board);
    return;
  }

  const list = document.createElement("div");
  list.className = "live-field-list";

  answers.forEach((item, index) => {
    const row = document.createElement("article");
    row.className = "live-field";
    if (index < activeIndex) {
      row.classList.add("is-filled");
    } else if (index === activeIndex) {
      row.classList.add("is-filling");
    }

    const rowHead = document.createElement("div");
    rowHead.className = "live-field-head";

    const question = document.createElement("strong");
    question.textContent = item.question || `항목 ${index + 1}`;

    const state = document.createElement("span");
    state.textContent = index < activeIndex
      ? "채움 완료"
      : index === activeIndex
        ? "입력 중"
        : "대기";

    rowHead.appendChild(question);
    rowHead.appendChild(state);

    const answer = document.createElement("div");
    answer.className = "live-field-answer";
    answer.textContent = index <= activeIndex ? item.answer || "" : "빈칸";

    row.appendChild(rowHead);
    row.appendChild(answer);
    list.appendChild(row);
  });

  board.appendChild(list);
  liveFillPreview.appendChild(board);
}

async function animateLiveFillResult(payload, token) {
  const animationToken = ++liveFillAnimationToken;
  const answers = payload.autofill_result?.answers || [];
  if (!answers.length) {
    renderLiveFillBoard(payload, -1);
    return;
  }

  for (let index = 0; index < answers.length; index += 1) {
    if (currentJobToken !== token || liveFillAnimationToken !== animationToken) {
      return;
    }
    renderLiveFillBoard(payload, index);
    await sleep(260);
  }

  if (currentJobToken === token && liveFillAnimationToken === animationToken) {
    renderLiveFillBoard(payload, answers.length);
  }
}

function renderAutofillResult(autofillResult, summary) {
  answerList.innerHTML = "";
  missingList.innerHTML = "";
  missingBlock.hidden = true;

  if (!autofillResult) {
    renderedDraft.textContent = "아직 생성된 결과가 없습니다.";
    filledResultMeta.textContent = "아직 생성된 결과가 없습니다.";
    return;
  }

  renderedDraft.textContent = autofillResult.rendered_draft || "생성된 초안이 없습니다.";
  filledResultMeta.textContent = `${summary.document_type} · 답변 ${summary.answer_count}개 · 추가 확인 ${summary.missing_count}개`;

  for (const item of autofillResult.answers || []) {
    const article = document.createElement("article");
    article.className = "result-item";

    const head = document.createElement("div");
    head.className = "result-item-head";

    const title = document.createElement("strong");
    title.textContent = item.question || "이름 없는 항목";

    const meta = document.createElement("span");
    meta.textContent = `${item.section || "기타"} · ${item.confidence || "medium"}`;

    head.appendChild(title);
    head.appendChild(meta);

    const answer = document.createElement("p");
    answer.className = "answer-text";
    answer.textContent = item.answer || "";

    article.appendChild(head);
    article.appendChild(answer);

    if (item.reason) {
      const reason = document.createElement("p");
      reason.className = "reason-text";
      reason.textContent = `사유: ${item.reason}`;
      article.appendChild(reason);
    }

    if (item.source && item.source.length) {
      const source = document.createElement("p");
      source.className = "source-text";
      source.textContent = `근거: ${item.source.join(", ")}`;
      article.appendChild(source);
    }

    answerList.appendChild(article);
  }

  const missingItems = autofillResult.missing_information || [];
  if (missingItems.length) {
    missingBlock.hidden = false;
    for (const item of missingItems) {
      const li = document.createElement("li");
      li.textContent = `${item.question || "항목"}: ${item.reason || "추가 확인 필요"}`;
      missingList.appendChild(li);
    }
  }
}

function resetUploadOutput() {
  downloadButtons.innerHTML = "";
  downloadHint.textContent = "업로드 후 생성됩니다.";
  renderedDraft.textContent = "아직 생성된 결과가 없습니다.";
  filledResultMeta.textContent = "아직 생성된 결과가 없습니다.";
  resetLiveFillPreview();
  answerList.innerHTML = "";
  missingList.innerHTML = "";
  missingBlock.hidden = true;
}

async function fetchState() {
  const response = await fetch("/api/state");
  const payload = await response.json();
  renderState(payload);
}

async function saveProfile() {
  const response = await fetch("/api/profile/save", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ profile: collectProfileForm() }),
  });
  const payload = await response.json();
  if (!response.ok) {
    alert(payload.error || "프로필 저장에 실패했습니다.");
    return;
  }
  await fetchState();
  profileStatus.textContent = `${payload.profile["이름"] || "프로필"} 저장 완료`;
}

async function loadSeedProfile() {
  const response = await fetch("/api/profile/load-seed", {
    method: "POST",
  });
  const payload = await response.json();
  if (!response.ok) {
    alert(payload.error || "샘플 불러오기에 실패했습니다.");
    return;
  }
  await fetchState();
}

async function startUploadJob(formData) {
  const response = await fetch("/api/forms/upload-and-fill/start", {
    method: "POST",
    body: formData,
  });
  const payload = await response.json();
  if (!response.ok) {
    const error = new Error(payload.detail || payload.error || "작업 시작에 실패했습니다.");
    error.payload = payload;
    throw error;
  }
  return payload;
}

async function pollUploadJob(jobId, token) {
  while (currentJobToken === token) {
    const response = await fetch(`/api/forms/upload-and-fill/jobs/${jobId}`, {
      cache: "no-store",
    });
    const payload = await response.json();
    if (!response.ok) {
      const error = new Error(payload.detail || payload.error || "작업 상태 조회에 실패했습니다.");
      error.payload = payload;
      throw error;
    }

    renderProgress(payload);
    renderJobLivePreview(payload);
    if (payload.status === "completed") {
      return payload.result;
    }
    if (payload.status === "failed") {
      const error = new Error(payload.detail || "문서 처리에 실패했습니다.");
      error.payload = payload;
      throw error;
    }

    await sleep(1200);
  }

  throw new Error("새 작업이 시작되어 이전 작업 대기를 중단했습니다.");
}

async function submitUpload(event) {
  event.preventDefault();
  const formData = new FormData(uploadForm);
  if (!formData.get("file") || !formData.get("file").name) {
    alert("업로드할 파일을 선택하세요.");
    return;
  }

  const token = ++currentJobToken;
  runAutofillButton.disabled = true;
  runAutofillButton.textContent = "처리 중...";

  uploadStatus.textContent = "업로드 중";
  uploadResultSummary.textContent = "문서를 서버에 전송하고 작업을 준비하고 있습니다.";
  resetUploadOutput();
  renderLiveStatus("업로드 준비 중", "파일을 서버에 전송하고 작업 대기열을 생성하고 있습니다.", {
    original_name: formData.get("file").name,
    character_count: 0,
  });
  renderProgress({
    status: "queued",
    progress: 4,
    stage_code: "queued",
    stage_label: "업로드 확인 중",
    message: "서버에 파일을 전송하고 있습니다.",
    elapsed_seconds: 0,
    original_name: formData.get("file").name,
    estimated_remaining_seconds: null,
  });

  try {
    const job = await startUploadJob(formData);
    uploadStatus.textContent = "진행 중";
    uploadResultSummary.textContent = `${job.original_name} 자동 작성 작업을 시작했습니다.`;
    renderProgress(job);

    const payload = await pollUploadJob(job.job_id, token);
    uploadStatus.textContent = "완료";
    documentPreview.textContent = payload.document.preview || "";
    documentMeta.textContent = `${payload.document.original_name} · ${payload.document.extension} · ${payload.document.character_count.toLocaleString()} chars`;
    uploadResultSummary.textContent = `${payload.autofill_summary.document_type} · ${payload.autofill_summary.summary} · 답변 ${payload.autofill_summary.answer_count}개`;
    renderDownloadButtons(payload.downloads || []);
    renderAutofillResult(payload.autofill_result, payload.autofill_summary);
    void animateLiveFillResult(payload, token);

    if (payload.download_error) {
      downloadHint.textContent = payload.download_error;
    }
  } catch (error) {
    uploadStatus.textContent = "실패";
    uploadResultSummary.textContent = error.payload?.detail || error.payload?.error || error.message || "문서 처리에 실패했습니다.";
    if (error.payload && error.payload.status) {
      renderProgress(error.payload);
    } else {
      progressEta.textContent = error.message || "오류가 발생했습니다.";
      progressCard.dataset.state = "failed";
    }
    renderedDraft.textContent = "생성에 실패했습니다.";
    filledResultMeta.textContent = "결과 없음";
    alert(error.payload?.detail || error.payload?.error || error.message || "문서 처리에 실패했습니다.");
  } finally {
    if (currentJobToken === token) {
      runAutofillButton.disabled = false;
      runAutofillButton.textContent = "파일 분석 및 자동 작성";
    }
  }
}

saveProfileButton.addEventListener("click", saveProfile);
loadSeedButton.addEventListener("click", loadSeedProfile);
uploadForm.addEventListener("submit", submitUpload);
modelSelect.addEventListener("change", () => {
  selectModel(modelSelect.value).catch((error) => {
    console.error(error);
    alert(error.message || "모델 변경에 실패했습니다.");
    fetchState().catch((stateError) => console.error(stateError));
  });
});

toggleJsonButton.addEventListener("click", () => {
  const isHidden = profileJsonPreview.hasAttribute("hidden");
  if (isHidden) {
    profileJsonPreview.removeAttribute("hidden");
    profileJsonPreview.textContent = JSON.stringify(collectProfileForm(), null, 2);
    toggleJsonButton.textContent = "숨기기";
  } else {
    profileJsonPreview.setAttribute("hidden", "");
    toggleJsonButton.textContent = "표시";
  }
});

form.addEventListener("input", () => {
  if (!profileJsonPreview.hasAttribute("hidden")) {
    profileJsonPreview.textContent = JSON.stringify(collectProfileForm(), null, 2);
  }
});

fetchState().catch((error) => {
  console.error(error);
  llmStatus.textContent = "상태 조회 실패";
});
