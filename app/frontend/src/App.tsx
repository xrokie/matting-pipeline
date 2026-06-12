import {
  CircleDot,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ImagePlus,
  Loader2,
  RotateCcw,
  Sparkles,
  Upload,
  Wand2,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  addMaskBox,
  addMaskPoint,
  addMaskText,
  clearMasks,
  fileUrl,
  getHealth,
  getJob,
  startMatting,
  undoMask,
  uploadBackground,
  uploadVideoProject,
} from "./api";
import type { JobResponse, MattingSettings, Point, ProjectResponse, WorkflowStage } from "./types";

const defaultSettings: MattingSettings = {
  warmup: 10,
  erode: 10,
  dilate: 10,
  max_size: 720,
  save_image: false,
};

const steps: Array<{ id: WorkflowStage; label: string; caption: string }> = [
  { id: "upload", label: "上传视频", caption: "截取首帧" },
  { id: "mask", label: "保留对象", caption: "文本或点选" },
  { id: "review", label: "检查绿幕", caption: "MatAnyone2" },
  { id: "background", label: "替换背景", caption: "上传图片" },
  { id: "done", label: "完成", caption: "导出结果" },
];

function App() {
  const [stage, setStage] = useState<WorkflowStage>("upload");
  const [apiOk, setApiOk] = useState<boolean | null>(null);
  const [projectId, setProjectId] = useState("avatar_demo");
  const [project, setProject] = useState<ProjectResponse | null>(null);
  const [taskLabel, setTaskLabel] = useState("等待开始");
  const [taskProgress, setTaskProgress] = useState(0);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [maskPrompt, setMaskPrompt] = useState("person");
  const [selectedPoint, setSelectedPoint] = useState<Point | null>(null);
  const [settings, setSettings] = useState<MattingSettings>(defaultSettings);
  const [showAdvancedSettings, setShowAdvancedSettings] = useState(false);
  const [showGenSettings, setShowGenSettings] = useState(false);
  const [boxMode, setBoxMode] = useState(false);
  const [boxStart, setBoxStart] = useState<Point | null>(null);
  const [boxEnd, setBoxEnd] = useState<Point | null>(null);
  const [imageVersion, setImageVersion] = useState(0);
  const [activity, setActivity] = useState<string[]>([]);
  const [naturalSize, setNaturalSize] = useState({ width: 0, height: 0 });

  function updateProject(p: ProjectResponse) {
    setProject(p);
    setImageVersion((v) => v + 1);
  }

  const imageRef = useRef<HTMLImageElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stageRef = useRef<HTMLDivElement | null>(null);

  const files = project?.files ?? {};
  const hasMask = Boolean(files.final_overlay || files.subject_overlay);
  const mainImage = fileUrl(files.final_overlay || files.subject_overlay || files.first_frame);
  const greenVideo = fileUrl(files.green);
  const resultVideo = fileUrl(files.replaced);

  useEffect(() => {
    getHealth()
      .then(() => setApiOk(true))
      .catch(() => setApiOk(false));
  }, []);

  useEffect(() => {
    drawCanvas();
  }, [selectedPoint, boxStart, boxEnd, boxMode, naturalSize, mainImage]);

  const stageIndex = useMemo(() => activeStepIndex(stage), [stage]);
  const completedStepIndex = useMemo(() => completedIndex(project), [project]);
  const accessibleStepIndex = useMemo(() => accessibleIndex(project), [project]);

  function pushActivity(message: string) {
    setActivity((items) => [`${new Date().toLocaleTimeString()}  ${message}`, ...items].slice(0, 8));
  }

  function setTask(progress: number, label: string, busy = false) {
    setTaskProgress(Math.max(0, Math.min(1, progress)));
    setTaskLabel(label);
    setIsBusy(busy);
  }

  async function handleError(action: string, callback: () => Promise<void>) {
    setError(null);
    try {
      await callback();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      setTask(1, `${action}失败`, false);
      pushActivity(`${action}失败`);
    }
  }

  async function createProject(video?: File) {
    if (!video) {
      setError("请选择一个原视频");
      return;
    }

    setTask(0.05, "上传视频中", true);
    pushActivity("开始上传视频");
    const response = await uploadVideoProject(projectId.trim(), video, (progress) => {
      setTask(0.05 + progress * 0.55, "上传视频中", true);
    });
    updateProject(response);
    setProjectId(response.project_id);
    setStage("mask");
    setTask(1, "首帧已准备好", false);
    pushActivity("首帧截取完成");
  }

  async function addRetainedMaskByText() {
    if (!project) return;
    if (!maskPrompt.trim()) {
      setError("请输入英文提示词");
      return;
    }

    setTask(0.08, "SAM3.1 正在识别保留对象", true);
    pushActivity("开始添加保留对象");
    const response = await addMaskText(project.project_id, maskPrompt.trim());
    updateProject(response);
    setTask(1, "保留对象已添加", false);
    pushActivity("保留对象已添加");
  }

  async function addRetainedMaskByPoint(point: Point) {
    if (!project) return;
    setSelectedPoint(point);
    setTask(0.08, "SAM2.1 正在识别点击对象", true);
    pushActivity(`开始点选保留对象 (${point.x}, ${point.y})`);
    const response = await addMaskPoint(project.project_id, point);
    updateProject(response);
    setSelectedPoint(null);
    setTask(1, "保留对象已添加", false);
    pushActivity("点选对象已添加");
  }

  async function undoLastMask() {
    if (!project) return;
    setTask(0.1, "正在回退抠像", true);
    const response = await undoMask(project.project_id);
    updateProject(response);
    setTask(1, "已回到上一步抠像", false);
    pushActivity("抠像已撤销一步");
  }

  async function clearMasksAndReturnToMask() {
    if (!project) return;
    setTask(0.1, "正在清空抠像", true);
    pushActivity("保留绿幕，清空抠像");
    const response = await clearMasks(project.project_id);
    updateProject(response);
    setStage("mask");
    setTask(1, "已清空抠像，请重新选择对象", false);
    pushActivity("可以重新选择对象了");
  }

  async function runMatting() {
    if (!project || !project.state.final_mask) {
      setError("请先添加至少一个保留对象");
      return;
    }
    setStage("matting");
    setTask(0.05, "MatAnyone2 排队中", true);
    pushActivity("开始生成绿幕");
    const job = await startMatting(project.project_id, settings);
    await pollJob(job, "MatAnyone2 推理中", (result) => {
      updateProject(result);
      setStage("review");
      setTask(1, "绿幕视频已生成，请检查结果", false);
      pushActivity("绿幕视频已生成");
    });
  }

  async function submitBackground(background?: File) {
    if (!project) return;
    if (!background) {
      setError("请选择替换背景图");
      return;
    }

    setTask(0.06, "上传背景图中", true);
    pushActivity("开始上传背景图");
    const job = await uploadBackground(project.project_id, background, (progress) => {
      setTask(0.06 + progress * 0.34, "上传背景图中", true);
    });
    await pollJob(job, "正在合成新背景", (result) => {
      updateProject(result);
      setStage("done");
      setTask(1, "背景替换完成", false);
      pushActivity("背景替换完成");
    });
  }

  async function pollJob(
    job: JobResponse,
    fallbackLabel: string,
    onSuccess: (result: ProjectResponse) => void,
  ) {
    let currentJob = job;
    setTask(currentJob.progress || 0.05, currentJob.message || fallbackLabel, true);

    while (currentJob.status === "queued" || currentJob.status === "running") {
      await new Promise((resolve) => window.setTimeout(resolve, 1800));
      currentJob = await getJob(currentJob.job_id);
      setTask(currentJob.progress || 0.05, currentJob.message || fallbackLabel, true);
    }

    if (currentJob.status === "failed") {
      throw new Error(currentJob.error?.message || "任务失败");
    }
    if (currentJob.result) {
      onSuccess(currentJob.result);
    }
  }

  function displayedImageRect() {
    const image = imageRef.current;
    const stageEl = stageRef.current;
    if (!image || !stageEl || !naturalSize.width || !naturalSize.height) return null;
    const bounds = stageEl.getBoundingClientRect();
    const scale = Math.min(bounds.width / naturalSize.width, bounds.height / naturalSize.height);
    const width = naturalSize.width * scale;
    const height = naturalSize.height * scale;
    return {
      x: (bounds.width - width) / 2,
      y: (bounds.height - height) / 2,
      width,
      height,
      scale,
    };
  }

  function eventToImagePoint(event: React.PointerEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current;
    const rect = displayedImageRect();
    if (!canvas || !rect) return null;
    const bounds = canvas.getBoundingClientRect();
    const x = event.clientX - bounds.left;
    const y = event.clientY - bounds.top;
    return {
      x: Math.max(0, Math.min(naturalSize.width, Math.round((x - rect.x) / rect.scale))),
      y: Math.max(0, Math.min(naturalSize.height, Math.round((y - rect.y) / rect.scale))),
    };
  }

  function drawCanvas() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const bounds = canvas.getBoundingClientRect();
    canvas.width = Math.round(bounds.width);
    canvas.height = Math.round(bounds.height);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const rect = displayedImageRect();
    if (!rect) return;

    // Box-drawing preview
    if (boxMode && boxStart && boxEnd) {
      const x1 = rect.x + boxStart.x * rect.scale;
      const y1 = rect.y + boxStart.y * rect.scale;
      const x2 = rect.x + boxEnd.x * rect.scale;
      const y2 = rect.y + boxEnd.y * rect.scale;
      ctx.strokeStyle = "#f45d48";
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 4]);
      ctx.fillStyle = "rgba(244, 93, 72, 0.10)";
      ctx.fillRect(x1, y1, x2 - x1, y2 - y1);
      ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
      ctx.setLineDash([]);
      return;
    }

    // Point marker (brief flash on click)
    if (!selectedPoint || boxMode) return;
    const x = rect.x + selectedPoint.x * rect.scale;
    const y = rect.y + selectedPoint.y * rect.scale;
    ctx.strokeStyle = "#f45d48";
    ctx.lineWidth = 3;
    ctx.fillStyle = "rgba(244, 93, 72, 0.16)";
    ctx.beginPath();
    ctx.arc(x, y, 13, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(x, y, 3.5, 0, Math.PI * 2);
    ctx.fillStyle = "#f45d48";
    ctx.fill();
  }

  function onPointerDown(event: React.PointerEvent<HTMLCanvasElement>) {
    if (stage !== "mask") return;
    if (isBusy) return;
    const point = eventToImagePoint(event);
    if (!point) return;

    if (boxMode) {
      setBoxStart(point);
      setBoxEnd(point);
    }
  }

  function onPointerMove(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!boxMode || !boxStart || isBusy) return;
    const point = eventToImagePoint(event);
    if (!point) return;
    setBoxEnd(point);
  }

  async function onPointerUp(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!boxMode || !boxStart || isBusy) return;
    const point = eventToImagePoint(event);
    if (!point) return;
    const finalEnd = point;
    setBoxEnd(finalEnd);

    // Only trigger if box is large enough (>10px in both dimensions)
    const minX = Math.min(boxStart.x, finalEnd.x);
    const minY = Math.min(boxStart.y, finalEnd.y);
    const maxX = Math.max(boxStart.x, finalEnd.x);
    const maxY = Math.max(boxStart.y, finalEnd.y);
    if (maxX - minX < 10 || maxY - minY < 10) {
      setBoxStart(null);
      setBoxEnd(null);
      return;
    }

    await handleError("添加框选对象", () =>
      addRetainedMaskByBox([minX, minY, maxX, maxY])
    );
    setBoxStart(null);
    setBoxEnd(null);
  }

  async function onCanvasClick(event: React.PointerEvent<HTMLCanvasElement>) {
    // Point mode: click triggers immediate SAM2 prediction
    if (boxMode || isBusy || stage !== "mask") return;
    if (boxStart) return; // was a box drag, not a click
    const point = eventToImagePoint(event);
    if (!point) return;
    await handleError("添加点选对象", () => addRetainedMaskByPoint(point));
  }

  async function addRetainedMaskByBox(box: [number, number, number, number]) {
    if (!project) return;
    setTask(0.08, "SAM3.1 正在识别框选区域", true);
    pushActivity(`框选区域 [${box.join(",")}]`);
    const response = await addMaskBox(project.project_id, box);
    updateProject(response);
    setTask(1, "框选对象已添加", false);
    pushActivity("框选对象已添加");
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">SAM3.1 + MatAnyone2</p>
          <h1>视频背景替换</h1>
        </div>
        <div className={`api-pill ${apiOk === false ? "bad" : apiOk ? "ok" : ""}`}>
          {apiOk === null ? "检查服务" : apiOk ? "API 正常" : "API 异常"}
        </div>
      </header>

      <nav className="stepper" aria-label="工作流阶段">
        {steps.map((item, index) => (
          <button
            className={`step ${index <= completedStepIndex ? "done" : ""} ${index === stageIndex ? "active" : ""} ${
              index > accessibleStepIndex || isBusy ? "locked" : ""
            }`}
            disabled={index > accessibleStepIndex || isBusy}
            key={item.id}
            onClick={() => setStage(item.id)}
          >
            <div className="step-mark">{index <= completedStepIndex ? <CheckCircle2 size={16} /> : index + 1}</div>
            <div>
              <strong>{item.label}</strong>
              <span>{item.caption}</span>
            </div>
          </button>
        ))}
      </nav>

      <main className="workspace">
        <section className="side-panel">
          <div className="panel-header">
            <span>当前任务</span>
            {isBusy ? <Loader2 className="spin" size={18} /> : <Sparkles size={18} />}
          </div>
          <h2>{taskTitle(stage)}</h2>
          <p className="support">{taskDescription(stage)}</p>
          <div className="progress-block">
            <div className="progress-copy">
              <span>{taskLabel}</span>
              <span>{Math.round(taskProgress * 100)}%</span>
            </div>
            <div className="progress-track">
              <div className={`progress-bar ${isBusy ? "busy" : ""}`} style={{ width: `${taskProgress * 100}%` }} />
            </div>
          </div>

          {stage === "upload" && (
            <UploadPanel
              projectId={projectId}
              setProjectId={setProjectId}
              onUpload={(file) => handleError("创建项目", () => createProject(file))}
            />
          )}

          {stage === "mask" && (
            <MaskPanel
              hasMask={hasMask}
              labels={maskLabels(project)}
              maskPrompt={maskPrompt}
              setMaskPrompt={setMaskPrompt}
              isBusy={isBusy}
              boxMode={boxMode}
              setBoxMode={setBoxMode}
              onMaskText={() => handleError("添加保留对象", addRetainedMaskByText)}
              onUndo={() => handleError("撤销抠像", undoLastMask)}
              onNext={() => handleError("生成绿幕", runMatting)}
              settings={settings}
              setSettings={setSettings}
              showAdvancedSettings={showAdvancedSettings}
              setShowAdvancedSettings={setShowAdvancedSettings}
              showGenSettings={showGenSettings}
              setShowGenSettings={setShowGenSettings}
            />
          )}

          {stage === "matting" && (
            <div className="quiet-box">
              <Loader2 className="spin" size={20} />
              <span>正在把首帧抠像传播到整段视频。</span>
            </div>
          )}

          {stage === "review" && (
            <ReviewPanel
              onBack={() => setStage("mask")}
              onClearAndReturn={() => handleError("清空抠像", clearMasksAndReturnToMask)}
              onNext={() => setStage("background")}
            />
          )}

          {stage === "background" && (
            <BackgroundPanel onUpload={(file) => handleError("背景替换", () => submitBackground(file))} />
          )}

          {stage === "done" && <DonePanel files={files} onRestart={() => window.location.reload()} />}

          {error && <pre className="error-box">{error}</pre>}
        </section>

        <section className="stage-panel">
          <div className="stage-toolbar">
            <div>
              <span className="stage-label">主舞台</span>
              <strong>{stageMediaTitle(stage)}</strong>
            </div>
            <span>{project ? project.project_id : "尚未创建项目"}</span>
          </div>
          <div className="media-stage" ref={stageRef}>
            {(stage === "upload" || !project) && (
              <div className="empty-state">
                <Upload size={40} />
                <strong>选择原视频后开始</strong>
                <span>系统会自动截取首帧并进入抠像阶段。</span>
              </div>
            )}

            {(stage === "mask" || stage === "matting") && mainImage && (
              <>
                <img
                  key={imageVersion}
                  ref={imageRef}
                  src={mainImage}
                  alt="首帧或抠像预览"
                  onLoad={(event) =>
                    setNaturalSize({
                      width: event.currentTarget.naturalWidth,
                      height: event.currentTarget.naturalHeight,
                    })
                  }
                />
                <canvas
                  ref={canvasRef}
                  className={`box-canvas${stage === "mask" ? " active" : ""}${boxMode ? " box-mode" : ""}`}
                  style={boxMode ? { cursor: "crosshair" } : undefined}
                  onPointerDown={onPointerDown}
                  onPointerMove={onPointerMove}
                  onPointerUp={onPointerUp}
                  onClick={onCanvasClick}
                />
              </>
            )}

            {(stage === "review" || stage === "background") && greenVideo && <video src={greenVideo} controls autoPlay muted />}
            {stage === "done" && resultVideo && <video src={resultVideo} controls autoPlay />}
          </div>
          <footer className="result-strip">
            <AssetLink href={files.alpha} label="alpha" />
            <AssetLink href={files.green} label="绿幕视频" />
            <AssetLink href={files.replaced} label="最终视频" />
          </footer>
        </section>

        <aside className="activity-panel">
          <h2>任务记录</h2>
          <div className="activity-list">
            {activity.length === 0 ? <span>操作后会在这里显示状态。</span> : activity.map((item) => <p key={item}>{item}</p>)}
          </div>
        </aside>
      </main>
    </div>
  );
}

function taskTitle(stage: WorkflowStage) {
  return {
    upload: "上传原视频",
    mask: "添加要保留的对象",
    matting: "生成绿幕视频",
    review: "检查绿幕结果",
    background: "上传替换背景",
    done: "替换完成",
  }[stage];
}

function taskDescription(stage: WorkflowStage) {
  return {
    upload: "只需要选择视频。首帧截取会在后台自动完成。",
    mask: "用英文提示词或直接点击画面，把需要保留的对象加入列表。",
    matting: "系统正在传播抠像结果，完成后会展示绿幕视频。",
    review: "先检查绿幕。如果缺少对象，可以返回继续添加后再重新生成。",
    background: "选择一张背景图，系统会自动合成最终视频。",
    done: "可以播放结果，或打开文件链接交给上游系统继续处理。",
  }[stage];
}

function stageMediaTitle(stage: WorkflowStage) {
  return {
    upload: "等待视频",
    mask: "首帧保留对象",
    matting: "抠像处理中",
    review: "绿幕视频检查",
    background: "绿幕预览",
    done: "背景替换结果",
  }[stage];
}

function activeStepIndex(stage: WorkflowStage) {
  if (stage === "matting") return steps.findIndex((item) => item.id === "review");
  return steps.findIndex((item) => item.id === stage);
}

function completedIndex(project: ProjectResponse | null) {
  if (!project) return -1;
  if (project.files.replaced) return 4;
  if (project.files.green) return 2;
  if (project.state.final_mask) return 1;
  if (project.files.first_frame) return 0;
  return -1;
}

function accessibleIndex(project: ProjectResponse | null) {
  if (!project) return 0;
  if (project.files.replaced) return 4;
  if (project.files.green) return 3;
  if (project.files.first_frame || project.state.final_mask) return 1;
  return 0;
}

function maskLabels(project: ProjectResponse | null) {
  const retained = project?.state.retained_masks ?? [];
  if (retained.length > 0) {
    return retained.map((item, index) => item.name || item.id || `MASK_${index + 1}`);
  }

  const history = project?.state.history ?? [];
  const subjectHistory = history.filter((item) => item.action === "set_subject");
  const latestSubject = subjectHistory[subjectHistory.length - 1]?.payload;
  const foregroundHistory = history.filter((item) => item.action === "add_foreground");
  const labels: string[] = [];
  if (project?.state.subject_mask) labels.push(labelFromPayload(latestSubject, "MASK_1"));
  labels.push(
    ...(project?.state.foreground_masks ?? []).map((_, index) =>
      labelFromPayload(foregroundHistory[index]?.payload, `MASK_${labels.length + index + 1}`),
    ),
  );
  return labels;
}

function labelFromPayload(payload: Record<string, unknown> | undefined, fallback: string) {
  if (!payload) return fallback;
  if (payload.mode === "text" && typeof payload.text === "string" && payload.text.trim()) {
    return payload.text.trim();
  }
  return fallback;
}

function UploadPanel({
  projectId,
  setProjectId,
  onUpload,
}: {
  projectId: string;
  setProjectId: (value: string) => void;
  onUpload: (file?: File) => void;
}) {
  const [file, setFile] = useState<File | undefined>();
  return (
    <div className="control-stack">
      <label>
        <span>项目 ID</span>
        <input value={projectId} onChange={(event) => setProjectId(event.target.value)} />
      </label>
      <label className="file-drop">
        <Upload size={20} />
        <span>{file ? file.name : "选择原视频后自动开始"}</span>
        <input
          type="file"
          accept="video/*"
          onChange={(event) => {
            const nextFile = event.target.files?.[0];
            setFile(nextFile);
            onUpload(nextFile);
          }}
        />
      </label>
    </div>
  );
}

function MaskPanel(props: {
  hasMask: boolean;
  labels: string[];
  maskPrompt: string;
  setMaskPrompt: (value: string) => void;
  isBusy: boolean;
  boxMode: boolean;
  setBoxMode: (value: boolean) => void;
  onMaskText: () => void;
  onUndo: () => void;
  onNext: () => void;
  settings: MattingSettings;
  setSettings: (value: MattingSettings) => void;
  showAdvancedSettings: boolean;
  setShowAdvancedSettings: (value: boolean) => void;
  showGenSettings: boolean;
  setShowGenSettings: (value: boolean) => void;
}) {
  return (
    <div className="control-stack">
      <div
        style={{
          background: "var(--accent-bg, #eef2ff)",
          border: "1px solid var(--accent, #6366f1)",
          borderRadius: 8,
          padding: "10px 14px",
          fontSize: 15,
          fontWeight: 600,
          lineHeight: 1.5,
          color: "var(--accent, #4338ca)",
        }}
      >
        <CircleDot size={16} style={{ display: "inline", verticalAlign: "middle", marginRight: 6 }} />
        直接在右侧图片上点击要保留的对象，即点即出 mask
      </div>

      <MaskChips labels={props.labels} />
      <button className="ghost" onClick={props.onUndo} disabled={props.isBusy}>
        <RotateCcw size={17} />
        撤销上一步抠像
      </button>

      <details open={props.showAdvancedSettings} onToggle={(event) => props.setShowAdvancedSettings(event.currentTarget.open)}>
        <summary>
          高级抠像选项
          <ChevronDown size={16} />
        </summary>
        <label>
          <span>文本描述抠像</span>
          <input value={props.maskPrompt} onChange={(event) => props.setMaskPrompt(event.target.value)} />
          <small className="field-hint">仅支持英文，例如 person、chair、desk。</small>
        </label>
        <button onClick={props.onMaskText} disabled={props.isBusy}>
          <Wand2 size={18} />
          添加文本对象
        </button>

        <label className="toggle-line" style={{ marginTop: 10 }}>
          <input
            type="checkbox"
            checked={props.boxMode}
            onChange={(event) => props.setBoxMode(event.target.checked)}
          />
          <span>框选模式（在图片上拖拽绘制矩形框）</span>
        </label>
        {props.boxMode && (
          <small className="field-hint">框选模式下拖拽绘制矩形，松手后自动抠像。</small>
        )}
      </details>

      <details open={props.showGenSettings} onToggle={(event) => props.setShowGenSettings(event.currentTarget.open)}>
        <summary>
          高级生成设置
          <ChevronDown size={16} />
        </summary>
        <SettingsForm settings={props.settings} setSettings={props.setSettings} />
      </details>

      <button disabled={!props.hasMask} onClick={props.onNext}>
        进入绿幕生成
        <ArrowRight size={18} />
      </button>
    </div>
  );
}

function MaskChips({ labels }: { labels: string[] }) {
  if (labels.length === 0) {
    return <div className="mask-ledger empty">尚未添加保留对象</div>;
  }
  return (
    <div className="mask-ledger">
      <div>
        <span>保留对象</span>
        <div className="chip-row">
          {labels.map((label, index) => (
            <strong key={`${label}-${index}`}>{label}</strong>
          ))}
        </div>
      </div>
    </div>
  );
}

function SettingsForm({
  settings,
  setSettings,
}: {
  settings: MattingSettings;
  setSettings: (value: MattingSettings) => void;
}) {
  function update<K extends keyof MattingSettings>(key: K, value: MattingSettings[K]) {
    setSettings({ ...settings, [key]: value });
  }

  return (
    <div className="settings-grid">
      <label>
        <span>首帧稳定帧数</span>
        <input type="number" value={settings.warmup} onChange={(event) => update("warmup", Number(event.target.value))} />
      </label>
      <label>
        <span>处理分辨率上限</span>
        <input type="number" value={settings.max_size} onChange={(event) => update("max_size", Number(event.target.value))} />
      </label>
      <label>
        <span>边缘收缩强度</span>
        <input type="number" value={settings.erode} onChange={(event) => update("erode", Number(event.target.value))} />
      </label>
      <label>
        <span>边缘扩展强度</span>
        <input type="number" value={settings.dilate} onChange={(event) => update("dilate", Number(event.target.value))} />
      </label>
      <label className="toggle-line">
        <input type="checkbox" checked={settings.save_image} onChange={(event) => update("save_image", event.target.checked)} />
        <span>保存调试帧</span>
      </label>
    </div>
  );
}

function BackgroundPanel({ onUpload }: { onUpload: (file?: File) => void }) {
  const [file, setFile] = useState<File | undefined>();
  return (
    <div className="control-stack">
      <label className="file-drop">
        <ImagePlus size={20} />
        <span>{file ? file.name : "选择替换背景图后自动合成"}</span>
        <input
          type="file"
          accept="image/*"
          onChange={(event) => {
            const nextFile = event.target.files?.[0];
            setFile(nextFile);
            onUpload(nextFile);
          }}
        />
      </label>
    </div>
  );
}

function ReviewPanel({ onBack, onClearAndReturn, onNext }: { onBack: () => void; onClearAndReturn: () => void; onNext: () => void }) {
  return (
    <div className="control-stack">
      <div className="quiet-box">
        <CheckCircle2 size={20} />
        <span>绿幕视频已生成。先检查主舞台结果。</span>
      </div>
      <div className="button-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <button className="secondary" onClick={onClearAndReturn}>
          <RotateCcw size={17} />
          继续补对象
        </button>
        <button className="secondary" onClick={onBack}>
          <RotateCcw size={17} />
          重新抠像
        </button>
      </div>
      <p className="field-hint">
        继续补对象：保留当前绿幕结果，继续填充抠像。<br />
        重新抠像：删除当前绿幕结果，重新做抠像操作。
      </p>
      <button onClick={onNext}>
        替换背景图
        <ArrowRight size={18} />
      </button>
    </div>
  );
}

function DonePanel({ files, onRestart }: { files: { replaced?: string | null }; onRestart: () => void }) {
  return (
    <div className="control-stack">
      <div className="quiet-box">
        <CheckCircle2 size={20} />
        <span>最终视频已经生成。</span>
      </div>
      <a className="download-button" href={files.replaced || undefined} target="_blank" rel="noreferrer">
        打开最终视频
      </a>
      <button className="secondary" onClick={onRestart}>
        新建任务
      </button>
    </div>
  );
}

function AssetLink({ href, label }: { href?: string | null; label: string }) {
  if (!href) return <span className="asset-link disabled">{label}</span>;
  return (
    <a className="asset-link" href={href} target="_blank" rel="noreferrer">
      {label}
    </a>
  );
}

export default App;
