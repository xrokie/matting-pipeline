const $ = (id) => document.getElementById(id)

const state = {
  projectId: null,
  files: {},
  imageNaturalWidth: 0,
  imageNaturalHeight: 0,
  dragStart: null,
  dragEnd: null,
  currentJobId: null,
  polling: null,
  elapsedTimer: null,
  jobStartedAt: null,
}

function log(message, data = null) {
  const line = data ? `${message}\n${JSON.stringify(data, null, 2)}` : message
  $("log").textContent = `[${new Date().toLocaleTimeString()}] ${line}\n\n${$("log").textContent}`
}

function cacheBust(url) {
  if (!url) return url
  return `${url}${url.includes("?") ? "&" : "?"}t=${Date.now()}`
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options)
  const text = await response.text()
  let data = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = { raw: text }
  }
  if (!response.ok) {
    throw new Error(JSON.stringify(data, null, 2))
  }
  return data
}

function setApiStatus(ok, text) {
  const el = $("apiStatus")
  el.textContent = text
  el.className = `status-pill ${ok ? "ok" : "bad"}`
}

function formatDuration(ms) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000))
  const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, "0")
  const seconds = String(totalSeconds % 60).padStart(2, "0")
  return `${minutes}:${seconds}`
}

function setProgress(progress, text, running = false) {
  const percent = Math.max(0, Math.min(100, Math.round((progress || 0) * 100)))
  $("progressText").textContent = text || `${percent}%`
  $("progressBar").style.width = `${percent}%`
  $("progressBar").classList.toggle("running", running)
}

function startElapsedTimer(startedAt = Date.now()) {
  stopElapsedTimer()
  state.jobStartedAt = startedAt
  $("elapsedTime").textContent = "用时 00:00"
  state.elapsedTimer = setInterval(() => {
    $("elapsedTime").textContent = `用时 ${formatDuration(Date.now() - state.jobStartedAt)}`
  }, 1000)
}

function stopElapsedTimer() {
  if (state.elapsedTimer) {
    clearInterval(state.elapsedTimer)
    state.elapsedTimer = null
  }
}

async function checkHealth() {
  try {
    const data = await requestJson("/health")
    setApiStatus(true, "API 正常")
    log("health ok", data)
  } catch (error) {
    setApiStatus(false, "API 异常")
    log("health failed", error.message)
  }
}

function updateFromProject(data) {
  state.projectId = data.project_id
  state.files = data.files || {}
  $("currentProject").textContent = `project: ${state.projectId} / ${data.status}`
  if (state.files.first_frame) {
    showImage(state.files.final_overlay || state.files.subject_overlay || state.files.first_frame)
  }
  updateResultLinks(data)
  updateMaskChips(data.state || {})
}

function chip(label, type) {
  const el = document.createElement("span")
  el.className = `chip ${type || ""}`
  el.textContent = label
  return el
}

function describeSource(source, fallback) {
  if (!source) return fallback
  if (source.mode === "text" && source.text) return source.text
  if (source.mode === "box") return fallback || "box mask"
  return fallback
}

function updateMaskChips(projectState) {
  $("subjectChips").replaceChildren()
  $("foregroundChips").replaceChildren()

  const history = projectState.history || []
  const subjectHistory = history.filter((item) => item.action === "set_subject")
  const latestSubject = subjectHistory[subjectHistory.length - 1]
  if (projectState.subject_mask) {
    $("subjectChips").appendChild(
      chip(describeSource(latestSubject?.payload, "subject_mask"), "subject"),
    )
  }

  const foregroundHistory = history.filter((item) => item.action === "add_foreground")
  const foregroundMasks = projectState.foreground_masks || []
  foregroundMasks.forEach((_, index) => {
    const payload = foregroundHistory[index]?.payload
    $("foregroundChips").appendChild(
      chip(describeSource(payload, `mask_${index + 1}`), "foreground"),
    )
  })
}

function updateResultLinks(data) {
  const files = data.files || {}
  const links = [
    ["alphaLink", files.alpha],
    ["foregroundLink", files.foreground],
    ["greenLink", files.green],
    ["replacedLink", files.replaced],
  ]
  for (const [id, url] of links) {
    const el = $(id)
    if (url) {
      el.href = url
      el.style.display = "inline"
    } else {
      el.removeAttribute("href")
      el.style.display = "none"
    }
  }
  $("roundStatus").textContent = files.round_count ? `已生成 ${files.round_count} 轮绿幕` : "尚无绿幕轮次"
  if (files.green) {
    $("greenVideo").src = cacheBust(files.green)
    $("greenVideo").style.display = "block"
  }
  if (files.replaced) {
    $("resultVideo").src = cacheBust(files.replaced)
    $("resultVideo").style.display = "block"
  }
}

function showImage(url) {
  if (!url) return
  const img = $("previewImage")
  img.onload = () => {
    state.imageNaturalWidth = img.naturalWidth
    state.imageNaturalHeight = img.naturalHeight
    $("emptyPreview").style.display = "none"
    img.style.display = "block"
    drawBox()
  }
  img.src = cacheBust(url)
}

function displayedImageRect() {
  const img = $("previewImage")
  const wrap = img.parentElement.getBoundingClientRect()
  if (!state.imageNaturalWidth || !state.imageNaturalHeight) {
    return null
  }

  const scale = Math.min(
    wrap.width / state.imageNaturalWidth,
    wrap.height / state.imageNaturalHeight,
  )
  const width = state.imageNaturalWidth * scale
  const height = state.imageNaturalHeight * scale
  const x = (wrap.width - width) / 2
  const y = (wrap.height - height) / 2
  return { x, y, width, height, scale }
}

function canvasPointToImagePoint(event) {
  const canvas = $("boxCanvas")
  const bounds = canvas.getBoundingClientRect()
  const rect = displayedImageRect()
  if (!rect) return null

  const x = event.clientX - bounds.left
  const y = event.clientY - bounds.top
  const ix = Math.round((x - rect.x) / rect.scale)
  const iy = Math.round((y - rect.y) / rect.scale)

  return {
    x: Math.max(0, Math.min(state.imageNaturalWidth, ix)),
    y: Math.max(0, Math.min(state.imageNaturalHeight, iy)),
  }
}

function normalizedBox() {
  if (!state.dragStart || !state.dragEnd) return null
  const x1 = Math.min(state.dragStart.x, state.dragEnd.x)
  const y1 = Math.min(state.dragStart.y, state.dragEnd.y)
  const x2 = Math.max(state.dragStart.x, state.dragEnd.x)
  const y2 = Math.max(state.dragStart.y, state.dragEnd.y)
  if (x2 - x1 < 4 || y2 - y1 < 4) return null
  return [x1, y1, x2, y2]
}

function drawBox() {
  const canvas = $("boxCanvas")
  const ctx = canvas.getContext("2d")
  const bounds = canvas.getBoundingClientRect()
  canvas.width = Math.round(bounds.width)
  canvas.height = Math.round(bounds.height)
  ctx.clearRect(0, 0, canvas.width, canvas.height)

  const rect = displayedImageRect()
  const box = normalizedBox()
  if (!rect || !box) return

  const [x1, y1, x2, y2] = box
  const sx1 = rect.x + x1 * rect.scale
  const sy1 = rect.y + y1 * rect.scale
  const sx2 = rect.x + x2 * rect.scale
  const sy2 = rect.y + y2 * rect.scale

  ctx.strokeStyle = "#ff2d2d"
  ctx.lineWidth = 3
  ctx.strokeRect(sx1, sy1, sx2 - sx1, sy2 - sy1)
  ctx.fillStyle = "rgba(255, 45, 45, 0.14)"
  ctx.fillRect(sx1, sy1, sx2 - sx1, sy2 - sy1)
}

async function refreshProject() {
  if (!state.projectId) return
  const data = await requestJson(`/api/projects/${state.projectId}`)
  updateFromProject(data)
  return data
}

async function createProject() {
  const video = $("videoInput").files[0]
  const background = $("backgroundInput").files[0]
  if (!video || !background) {
    alert("请先选择原视频和背景图")
    return
  }

  const form = new FormData()
  form.append("project_id", $("projectId").value.trim())
  form.append("video", video)
  form.append("background", background)

  log("创建项目中")
  const data = await requestJson("/api/projects", {
    method: "POST",
    body: form,
  })
  updateFromProject(data)
  log("项目创建成功", data)
}

async function postJson(url, payload = {}) {
  return requestJson(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
}

async function setSubject() {
  if (!state.projectId) return alert("请先创建项目")
  const data = await postJson(`/api/projects/${state.projectId}/subject/text`, {
    text: $("subjectText").value.trim(),
  })
  updateFromProject(data)
  showImage(data.files.final_overlay || data.files.subject_overlay)
  log("主体已设置", data)
}

async function setSubjectBox() {
  if (!state.projectId) return alert("请先创建项目")
  const raw = $("boxInput").value.trim().split(/\s+/).map(Number)
  if (raw.length !== 4 || raw.some(Number.isNaN)) {
    alert("请先在首帧上拖拽主体区域，或输入 x1 y1 x2 y2")
    return
  }
  const data = await postJson(`/api/projects/${state.projectId}/subject/box`, {
    box: raw,
  })
  updateFromProject(data)
  showImage(data.files.final_overlay || data.files.subject_overlay)
  log("主体框选已设置", data)
}

async function addForegroundText() {
  if (!state.projectId) return alert("请先创建项目")
  const data = await postJson(`/api/projects/${state.projectId}/foreground/text`, {
    text: $("foregroundText").value.trim(),
  })
  updateFromProject(data)
  showImage(data.files.final_overlay)
  log("前景文字已添加", data)
}

async function addForegroundBox() {
  if (!state.projectId) return alert("请先创建项目")
  const raw = $("boxInput").value.trim().split(/\s+/).map(Number)
  if (raw.length !== 4 || raw.some(Number.isNaN)) {
    alert("请先拖拽生成有效 box，或输入 x1 y1 x2 y2")
    return
  }
  const data = await postJson(`/api/projects/${state.projectId}/foreground/box`, {
    box: raw,
  })
  updateFromProject(data)
  showImage(data.files.final_overlay)
  log("前景框选已添加", data)
}

async function undoForeground() {
  if (!state.projectId) return alert("请先创建项目")
  const data = await postJson(`/api/projects/${state.projectId}/foreground/undo`)
  updateFromProject(data)
  showImage(data.files.final_overlay)
  log("已撤销最后一个前景", data)
}

async function undoMattingRound() {
  if (!state.projectId) return alert("请先创建项目")
  const data = await postJson(`/api/projects/${state.projectId}/matting/undo`)
  updateFromProject(data)
  log("已撤销上一轮绿幕", data)
}

async function startMatting() {
  if (!state.projectId) return alert("请先创建项目")
  const payload = mattingPayload()
  const job = await postJson(`/api/projects/${state.projectId}/matting`, payload)
  state.currentJobId = job.job_id
  $("jobStatus").textContent = `${job.job_id}: ${job.status}`
  startElapsedTimer()
  setProgress(job.progress || 0.05, "绿幕生成中", true)
  log("绿幕 Matting 任务已启动", job)
  pollJob()
}

function mattingPayload() {
  return {
    warmup: Number($("warmup").value),
    erode: Number($("erode").value),
    dilate: Number($("dilate").value),
    max_size: Number($("maxSize").value),
    save_image: $("saveImage").checked,
  }
}

async function pollJob() {
  if (!state.currentJobId) return
  if (state.polling) clearInterval(state.polling)

  state.polling = setInterval(async () => {
    try {
      const job = await requestJson(`/api/jobs/${state.currentJobId}`)
      $("jobStatus").textContent = `${job.job_id}: ${job.status} / ${job.message}`
      const running = job.status === "running" || job.status === "queued"
      const label = running ? `${job.stage || "running"} / ${job.message || "运行中"}` : job.status
      setProgress(job.progress || (running ? 0.05 : 0), label, running)
      if (job.status === "succeeded") {
        clearInterval(state.polling)
        state.polling = null
        stopElapsedTimer()
        setProgress(1, "完成", false)
        log("绿幕 Matting 任务完成", job)
        if (job.result) {
          updateFromProject(job.result)
        } else {
          const project = await refreshProject()
          updateResultLinks(project)
        }
      }
      if (job.status === "failed") {
        clearInterval(state.polling)
        state.polling = null
        stopElapsedTimer()
        setProgress(1, "失败", false)
        log("绿幕 Matting 任务失败", job)
      }
    } catch (error) {
      log("轮询任务失败", error.message)
    }
  }, 3000)
}

function bindEvents() {
  $("createProjectBtn").addEventListener("click", () => createProject().catch((e) => log("创建项目失败", e.message)))
  $("setSubjectBtn").addEventListener("click", () => setSubject().catch((e) => log("设置主体失败", e.message)))
  $("setSubjectBoxBtn").addEventListener("click", () => setSubjectBox().catch((e) => log("设置主体框选失败", e.message)))
  $("addForegroundTextBtn").addEventListener("click", () => addForegroundText().catch((e) => log("添加前景失败", e.message)))
  $("addForegroundBoxBtn").addEventListener("click", () => addForegroundBox().catch((e) => log("添加框选失败", e.message)))
  $("undoForegroundBtn").addEventListener("click", () => undoForeground().catch((e) => log("撤销失败", e.message)))
  $("startMattingBtn").addEventListener("click", () => startMatting().catch((e) => log("启动 Matting 失败", e.message)))
  $("undoMattingRoundBtn").addEventListener("click", () => undoMattingRound().catch((e) => log("撤销绿幕轮次失败", e.message)))

  $("showFirstFrameBtn").addEventListener("click", () => showImage(state.files.first_frame))
  $("showSubjectBtn").addEventListener("click", () => showImage(state.files.subject_overlay || state.files.subject_mask))
  $("showFinalBtn").addEventListener("click", () => showImage(state.files.final_overlay || state.files.final_mask))

  const canvas = $("boxCanvas")
  canvas.addEventListener("mousedown", (event) => {
    const point = canvasPointToImagePoint(event)
    if (!point) return
    state.dragStart = point
    state.dragEnd = point
    drawBox()
  })
  canvas.addEventListener("mousemove", (event) => {
    if (!state.dragStart) return
    const point = canvasPointToImagePoint(event)
    if (!point) return
    state.dragEnd = point
    const box = normalizedBox()
    if (box) $("boxInput").value = box.join(" ")
    drawBox()
  })
  window.addEventListener("mouseup", () => {
    if (!state.dragStart) return
    const box = normalizedBox()
    if (box) $("boxInput").value = box.join(" ")
    state.dragStart = null
  })
  window.addEventListener("resize", drawBox)
}

bindEvents()
checkHealth()
