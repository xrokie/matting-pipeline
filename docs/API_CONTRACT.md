# API 合同

本文档定义后端与前端之间的 HTTP 接口合同。所有返回给浏览器的文件路径都是 URL path，不是服务器绝对路径。

## 基础地址

默认开发/生产地址：

```text
API base: http://127.0.0.1:8000
UI:       http://127.0.0.1:8000/app
Swagger:  http://127.0.0.1:8000/docs
```

## Project Response

大多数项目接口返回：

```json
{
  "project_id": "avatar_demo",
  "status": "ready_for_matting",
  "files": {
    "video": "/files/avatar_demo/inputs/input.mp4",
    "first_frame": "/files/avatar_demo/inputs/first_frame.png",
    "final_mask": "/files/avatar_demo/masks/final.png",
    "final_overlay": "/files/avatar_demo/overlays/final_overlay.png",
    "green": null,
    "replaced": null,
    "retained_masks": [
      {
        "id": "MASK_1",
        "name": "person",
        "mask": "/files/avatar_demo/masks/retained_000.png",
        "overlay": "/files/avatar_demo/overlays/retained_000_overlay.png",
        "source": {"mode": "point", "point": [520, 360]}
      }
    ]
  },
  "state": {}
}
```

`status` 取值：

```text
created
ready_for_mask
ready_for_matting
ready_for_background
background_succeeded
```

## Job Response

耗时任务会立即返回 job：

```json
{
  "job_id": "job_abc123",
  "project_id": "avatar_demo",
  "status": "queued",
  "stage": "queued",
  "progress": 0.0,
  "message": "任务已进入队列",
  "result": null,
  "error": null
}
```

轮询：

```http
GET /api/jobs/{job_id}
```

终态：

```text
succeeded
failed
```

成功时 `result` 是完整 Project Response。失败时 `error.message` 包含可展示/可调试的错误信息。

## 接口列表

### 健康检查

```http
GET /health
```

前端打开前、部署验收时，都应先用它检查目录和 checkpoint 状态。

### 创建项目

```http
POST /api/projects
Content-Type: multipart/form-data
```

字段：

```text
video       必填文件
background  可选文件，旧兼容路径
project_id  可选字符串，2-64 位，仅允许字母/数字/_/-
```

前端建议：

- 新流程只上传 `video`。
- 使用返回的 `files.first_frame` 做 mask 选择。
- 不传 `project_id` 时由后端生成。

### 获取项目

```http
GET /api/projects/{project_id}
```

返回当前 Project Response。

### 文本添加保留对象

```http
POST /api/projects/{project_id}/masks/text
Content-Type: application/json
```

请求：

```json
{"text": "person"}
```

使用 SAM3.1。prompt 建议使用英文名词或短语。

### 点选添加保留对象

```http
POST /api/projects/{project_id}/masks/point
Content-Type: application/json
```

请求：

```json
{"point": [520, 360]}
```

坐标必须是 `files.first_frame` 原始像素坐标中的整数 `[x, y]`。前端需要把显示坐标换算回原图坐标。

后端行为：

1. 优先调用常驻 SAM2.1 服务。
2. 保存 mask 和 overlay。
3. 写入 `state.json` 的 retained mask 列表。
4. SAM2 失败时回退到 SAM3.1 point prompt。

### 框选添加保留对象

```http
POST /api/projects/{project_id}/masks/box
Content-Type: application/json
```

请求：

```json
{"box": [100, 200, 500, 800]}
```

格式为 `[x1, y1, x2, y2]`，同样基于首帧原始像素。使用 SAM3.1。

### 撤销上一步 Mask

```http
POST /api/projects/{project_id}/mask/undo
```

恢复最近一次 mask snapshot，并更新 `final_mask`。

### 清空当前 Mask

```http
POST /api/projects/{project_id}/masks/clear
```

清空当前 retained masks，但保留已有 matting rounds 和绿幕结果。用于多轮补对象流程。

### 开始 Matting

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
  "max_size": 720,
  "save_image": false
}
```

要求 `state.final_mask` 存在。返回 Job Response。成功后项目文件包含：

```text
files.alpha
files.foreground
files.green
files.round_count
```

### 撤销上一轮 Matting

```http
POST /api/projects/{project_id}/matting/undo
```

移除最后一轮 matting，并用剩余 rounds 重建累计 `alpha`/`green`。

### 上传背景并合成

```http
POST /api/projects/{project_id}/background
Content-Type: multipart/form-data
```

字段：

```text
background  必填文件
```

要求 `results.alpha` 存在。返回 Job Response。成功后项目文件包含 `files.replaced`。

### 文件访问

```http
GET /files/{project_id}/{project_relative_path}
```

只允许访问 `${MATTING_ROOT}/projects/{project_id}` 内部的 project-relative path。

## 旧兼容接口

以下接口为旧客户端保留，新前端不要使用：

```text
/subject/text
/subject/point
/subject/box
/foreground/text
/foreground/point
/foreground/box
/foreground/undo
/targets/*
```

新客户端只使用 `/masks/*` 的 retained-mask 主流程。
