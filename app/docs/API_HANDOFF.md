# API 交接文档：交互式视频换背景

本文档定义前端/客户端与后端之间的 HTTP API 合同。

当前底层模型调用仍然是 CLI，API server 通过 `subprocess` 或 `conda run` 调用已有命令：

本包已提供最小 FastAPI 实现：

```text
api_server/main.py
```

```text
SAM3.1 mask worker:
  conda run -n sam3 python -m services.mask_service_cli ...

MatAnyone2 matting worker:
  conda run -n matanyone2 python -m services.matting_project_cli ...
```

第一版不建议让 API server 直接 import SAM3.1 或 MatAnyone2。两个模型环境继续保持隔离。

## 职责边界

后端负责：

- 接收上传的视频。
- 创建 project 目录。
- 用 FFmpeg 截取首帧。
- 调用 SAM3.1 生成首帧 mask。
- 管理 retained masks 和 final mask 状态；旧 subject/foreground 状态仅作为兼容字段保留。
- 生成 overlay 预览图。
- 调用 MatAnyone2 做整段视频 matting。
- 管理每一轮 matting 结果，将多轮 alpha 通过 max 累积。
- 输出第一阶段绿幕视频，并支持撤销上一轮绿幕。
- 接收第三阶段背景图。
- 合成背景图并输出最终视频。
- 管理任务状态、错误信息和结果文件。

前端负责：

- 上传 UI。
- 展示首帧图片。
- 输入文字 prompt。
- 在画布上点选要保留的对象，并把坐标换算回原始首帧像素坐标。
- 展示 mask overlay 预览。
- 发起 matting 任务。
- 展示任务进度。当前后端会解析 MatAnyone2 tqdm 输出里的 `当前帧/总帧数`，返回帧级 progress。
- 上传替换背景图并展示背景合成进度。
- 播放或下载最终视频。

## Project 数据模型

每个用户任务对应一个 project：

```text
projects/{project_id}/state.json
```

推荐的 `state.json` 结构：

```json
{
  "project_id": "avatar_test",
  "created_at": "2026-06-09T14:59:26",
  "updated_at": "2026-06-09T15:19:01",
  "video": "inputs/input.mp4",
  "background": null,
  "first_frame": "inputs/first_frame.png",
  "subject_mask": "masks/subject.png",
  "foreground_masks": [
    "masks/foreground_000.png"
  ],
  "final_mask": "masks/final.png",
  "matting_rounds": [
    {
      "id": "round_000",
      "source_mask": "masks/final.png",
      "round_alpha": "rounds/round_000/alpha.mp4",
      "foreground": "rounds/round_000/foreground.mp4"
    }
  ],
  "results": {
    "alpha": "results/alpha.mp4",
    "green": "results/green.mp4",
    "foreground": "rounds/round_000/foreground.mp4"
  },
  "history": []
}
```

说明：

- `video`：原视频。
- `background`：第三阶段上传的背景图，后端统一保存为 PNG；创建项目时可为空。
- `first_frame`：原视频第一帧。
- `retained_masks`：保留对象列表，可由多次文字或点选添加。
- `final_mask`：所有 retained masks 的合并结果，直接传入 MatAnyone2。
- `subject_mask` / `foreground_masks`：旧兼容字段，新前端不再区分。
- `matting_rounds`：每一轮绿幕 matting 的独立结果。
- `results.alpha`：多轮 alpha 通过 max 累积后的结果。
- `results.green`：第一阶段绿幕预览视频。
- `results.replaced`：第三阶段最终换背景视频。
- `history`：用于记录用户每次 mask 操作，便于调试和回溯。

API 响应里不要返回服务器绝对路径，应该返回浏览器可访问的 URL。

示例映射：

```text
projects/avatar_test/inputs/first_frame.png
  -> /files/avatar_test/inputs/first_frame.png
```

## 接口列表

### 1. 创建项目

```http
POST /api/projects
Content-Type: multipart/form-data
```

表单字段：

```text
video: file, 必填
background: file, 可选，不建议新前端使用
```

后端动作：

```bash
cd ~/matting/sam3
conda run -n sam3 python -m services.mask_service_cli init \
  --project ~/matting/projects/{project_id} \
  --video {uploaded_video_path}
```

响应示例：

```json
{
  "project_id": "avatar_test",
  "status": "ready_for_mask",
  "files": {
    "first_frame": "/files/avatar_test/inputs/first_frame.png"
  },
  "state": {
    "subject_mask": null,
    "foreground_masks": [],
    "final_mask": null
  }
}
```

前端拿到 `first_frame` 后，应展示给用户做主体/前景选择。

### 2. 获取项目状态

```http
GET /api/projects/{project_id}
```

响应示例：

```json
{
  "project_id": "avatar_test",
  "status": "ready_for_background",
  "files": {
    "first_frame": "/files/avatar_test/inputs/first_frame.png",
    "subject_overlay": "/files/avatar_test/overlays/subject_overlay.png",
    "final_overlay": "/files/avatar_test/overlays/final_overlay.png",
    "green": "/files/avatar_test/results/green.mp4"
  },
  "state": {
    "subject_mask": "masks/subject.png",
    "foreground_masks": [
      "masks/foreground_000.png"
    ],
    "final_mask": "masks/final.png"
  }
}
```

### 3. 通过文字添加保留对象

```http
POST /api/projects/{project_id}/masks/text
Content-Type: application/json
```

请求：

```json
{
  "text": "person"
}
```

后端动作：

```bash
cd ~/matting/sam3
conda run -n sam3 python -m services.mask_service_cli add-mask-text \
  --project ~/matting/projects/{project_id} \
  --checkpoint ~/matting/sam3/models/sam3.1/sam3.1_multiplex.pt \
  --text "person"
```

响应：

```json
{
  "status": "ready_for_matting",
  "files": {
    "retained_masks": [
      {
        "id": "MASK_1",
        "name": "person",
        "mask": "/files/avatar_test/masks/retained_000.png",
        "overlay": "/files/avatar_test/overlays/retained_000_overlay.png"
      }
    ],
    "final_mask": "/files/avatar_test/masks/final.png",
    "final_overlay": "/files/avatar_test/overlays/final_overlay.png"
  }
}
```

### 4. 通过点选添加保留对象

```http
POST /api/projects/{project_id}/masks/point
Content-Type: application/json
```

请求：

```json
{
  "point": [520, 360]
}
```

坐标格式：

```text
[x, y]
```

坐标必须基于 `first_frame.png` 的原始像素尺寸。SAM3.1 本地仓库已确认存在 point prompt 支撑；服务封装会优先调用 `Sam3Processor.add_point_prompt`，如果当前仓库没有该方法，则 fallback 到底层 `append_points`。

### 5. 兼容接口

旧客户端仍可使用下列接口，但新前端不再区分主体和前景：

```http
POST /api/projects/{project_id}/subject/text
POST /api/projects/{project_id}/subject/point
POST /api/projects/{project_id}/subject/box
POST /api/projects/{project_id}/foreground/text
POST /api/projects/{project_id}/foreground/point
POST /api/projects/{project_id}/foreground/box
```

### 7. 撤销上一版抠像

该接口会回退任意一次保留对象添加或旧主体/前景抠像操作。前端主流程应优先使用该接口。

```http
POST /api/projects/{project_id}/mask/undo
```

后端动作：

```bash
cd ~/matting/sam3
conda run -n sam3 python -m services.mask_service_cli undo-mask \
  --project ~/matting/projects/{project_id}
```

响应：

```json
{
  "status": "ready_for_mask",
  "files": {
    "first_frame": "/files/avatar_test/inputs/first_frame.png"
  }
}
```

### 8. 撤销最后一次前景添加

```http
POST /api/projects/{project_id}/foreground/undo
```

后端动作：

```bash
cd ~/matting/sam3
conda run -n sam3 python -m services.mask_service_cli undo-foreground \
  --project ~/matting/projects/{project_id}
```

响应：

```json
{
  "status": "ready_for_matting",
  "files": {
    "final_overlay": "/files/avatar_test/overlays/final_overlay.png"
  }
}
```

### 9. 生成/叠加一轮绿幕 Matting

MatAnyone2 是长时间 GPU 任务。API 不应阻塞等待完成，应该立即返回 `job_id`。

这个接口代表绿幕生成操作：使用当前 `final_mask` 跑 MatAnyone2，产出本轮 alpha，并与历史轮次 alpha 做 max 累积。完成后会生成：

```text
results/alpha.mp4
results/green.mp4
```

前端应展示 `results/green.mp4`，并在第三阶段上传背景后再生成 `results/replaced.mp4`。

```http
POST /api/projects/{project_id}/matting
Content-Type: application/json
```

请求：

```json
{
  "warmup": 10,
  "erode": 10,
  "dilate": 10,
  "max_size": -1
}
```

字段说明：

- `warmup`：MatAnyone2 warmup 参数。
- `erode`：mask erode 半径。
- `dilate`：mask dilate 半径。
- `max_size`：推理最大尺寸，`-1` 表示不限制。

后端动作：

```bash
cd ~/matting/MatAnyone2
conda run -n matanyone2 python -m services.matting_project_cli \
  --project ~/matting/projects/{project_id} \
  --warmup 10 \
  --erode 10 \
  --dilate 10 \
  --max-size -1
```

响应：

```json
{
  "job_id": "job_01H...",
  "project_id": "avatar_test",
  "status": "queued"
}
```

### 10. 上传背景并合成

背景合成是后台任务。该接口不会重跑 MatAnyone2，只基于已有 `results/alpha.mp4` 合成 `results/replaced.mp4`。

```http
POST /api/projects/{project_id}/background
Content-Type: multipart/form-data
```

表单字段：

```text
background: file, 必填
```

后端动作：

```bash
cd ~/matting/MatAnyone2
conda run -n matanyone2 python -m services.matting_project_cli \
  --project ~/matting/projects/{project_id} \
  --compose-background \
  --background {uploaded_background_path}
```

响应：

```json
{
  "job_id": "job_01H...",
  "project_id": "avatar_test",
  "status": "queued"
}
```

### 11. 撤销上一轮绿幕

```http
POST /api/projects/{project_id}/matting/undo
```

后端动作：

```bash
cd ~/matting/MatAnyone2
conda run -n matanyone2 python -m services.matting_project_cli \
  --project ~/matting/projects/{project_id} \
  --undo-round
```

说明：

- 如果已有多轮绿幕，撤销后会回到上一轮累计 alpha 和绿幕结果。
- 如果只有一轮，撤销后会清空 `results`。
- 该接口用于用户发现本轮主体/前景选择效果不好时回退。

### 12. 查询任务状态

```http
GET /api/jobs/{job_id}
```

运行中响应：

```json
{
  "job_id": "job_01H...",
  "project_id": "avatar_test",
  "status": "running",
  "stage": "matanyone2",
  "progress": 0.42,
  "message": "Processing video matting"
}
```

完成响应：

```json
{
  "job_id": "job_01H...",
  "project_id": "avatar_test",
  "status": "succeeded",
  "files": {
    "alpha": "/files/avatar_test/results/alpha.mp4",
    "green": "/files/avatar_test/results/green.mp4",
    "foreground": "/files/avatar_test/results/foreground.mp4"
  }
}
```

失败响应：

```json
{
  "job_id": "job_01H...",
  "project_id": "avatar_test",
  "status": "failed",
  "error": {
    "code": "MATANYONE2_FAILED",
    "message": "No file matched *_pha.mp4 in results/matanyone2_raw"
  }
}
```

## 文件访问接口

本地开发可以提供一个静态文件接口：

```http
GET /files/{project_id}/{path}
```

示例：

```text
/files/avatar_test/inputs/first_frame.png
/files/avatar_test/overlays/final_overlay.png
/files/avatar_test/results/green.mp4
/files/avatar_test/results/replaced.mp4
```

生产环境必须增加：

- 用户鉴权。
- project 权限校验。
- 防路径穿越。
- 文件访问过期或签名机制。

## 前端画布坐标换算

后端期望收到的是原始首帧图片上的像素坐标。

如果 `first_frame.png` 原始尺寸是：

```text
704 x 1280
```

前端展示尺寸是：

```text
352 x 640
```

那么前端需要做坐标换算：

```text
scale_x = natural_width / displayed_width
scale_y = natural_height / displayed_height
```

示例：

```js
const backendPoint = [
  Math.round(displayPoint.x * scaleX),
  Math.round(displayPoint.y * scaleY),
];
```

传给后端前，建议保证：

```text
0 <= x <= natural_width
0 <= y <= natural_height
```

## 状态模型

推荐 project 状态：

```text
created
ready_for_mask
ready_for_matting
matting_queued
matting_running
matting_succeeded
matting_failed
```

推荐 job 状态：

```text
queued
running
succeeded
failed
canceled
```

## GPU 调度建议

单张 RTX 4090 上，建议设置一个 GPU 锁。

```text
SAM3.1 text/point prompt:
  短任务，第一版可以同步执行

MatAnyone2 video matting:
  长任务，必须进入 job queue
```

第一版不要并发跑多个 MatAnyone2 任务。

## 暂不暴露到前端

独立 target 模式暂不暴露到前端。

当前稳定封装的能力是：

```text
subject text
subject point
foreground text
foreground point
undo mask
```

后端仍保留 text/box target 兼容接口，并补充了 target point CLI/API，供后续专项功能接入。
