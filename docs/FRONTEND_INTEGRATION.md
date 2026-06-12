# 前端接入指南

本文档面向需要把该能力接入其他工程、或替换内置 UI 的前端工程师。

## 产品流程

使用一条线性流程：

```text
upload
  -> mask
  -> matting
  -> review
  -> background
  -> done
```

推荐交互：

- 选择视频后立即上传。
- 上传成功后展示 `files.first_frame`。
- 默认交互使用图片点选。
- 文本 prompt 和框选作为高级工具保留。
- 只有 `state.final_mask` 存在后才允许开始 matting。
- job 每 1-2 秒轮询一次。
- 背景替换前必须先展示绿幕预览。
- 绿幕成功后再上传背景。
- 最终展示 `files.replaced` 视频，并提供下载/打开入口。

## 坐标换算

发送给后端的 point 和 box 坐标必须基于首帧原图尺寸，而不是 DOM 显示尺寸。

对于 `object-fit: contain` 的图片：

```text
scale = min(container_width / natural_width, container_height / natural_height)
display_width = natural_width * scale
display_height = natural_height * scale
offset_x = (container_width - display_width) / 2
offset_y = (container_height - display_height) / 2

image_x = round((pointer_x - offset_x) / scale)
image_y = round((pointer_y - offset_y) / scale)
```

然后限制范围：

```text
0 <= image_x <= natural_width
0 <= image_y <= natural_height
```

内置实现位于 `app/frontend/src/App.tsx` 的 `eventToImagePoint()`。

## API Client 职责

HTTP client 保持薄封装：

- `POST /api/projects`，使用 `FormData`。
- `POST /api/projects/{id}/masks/point`，传原图像素坐标。
- `POST /api/projects/{id}/masks/text`，作为英文 prompt 兜底。
- `POST /api/projects/{id}/masks/box`，作为矩形框兜底。
- `POST /api/projects/{id}/mask/undo`，撤销 mask。
- `POST /api/projects/{id}/matting`，并轮询 job。
- `POST /api/projects/{id}/background`，并轮询 job。
- project response 更新后，对媒体 URL 做 cache bust。

当前轻量 client 在 `app/frontend/src/api.ts`。

## 状态与导航

建议同时使用后端 `status` 和文件是否存在：

```text
ready_for_mask          files.first_frame
ready_for_matting       state.final_mask 或 files.final_mask
ready_for_background    files.green
background_succeeded    files.replaced
```

不要在主产品流程中暴露独立 `targets` 模式。当前支持路径是 retained-mask 工作流。

## 进度处理

`/matting` 和 `/background` 会返回 Job Response。轮询：

```http
GET /api/jobs/{job_id}
```

使用字段：

- `progress`：进度条。
- `message`：用户可读状态。
- `stage`：可选的细分阶段。
- `error.message`：失败详情。
- `result`：成功后的最终 Project Response。

MatAnyone2 进度来自子进程输出解析，因此初始化和封装阶段的进度可能不是匀速变化。

## UI 要求

- 这是工作台能力，不要做成营销落地页。
- 主舞台只展示当前最重要的媒体：首帧、绿幕视频或最终视频。
- 高级设置默认折叠。
- `max_size` 默认 `720`。
- `save_image` 默认 `false`；打开后可能产生大量逐帧文件。
- 错误展示应保留后端 JSON detail，方便排查。
- 长任务运行时，相关按钮必须 disabled。

## 内置前端

内置前端技术栈：

```text
Vite + React + TypeScript
lucide-react icons
plain CSS
```

构建：

```bash
cd ~/matting/app/frontend
npm install
npm run build
```

FastAPI 挂载地址：

```text
/app
```

## 接入检查清单

接入大型前端工程前确认：

- API base URL 和宿主工程 CORS 策略。
- 上传大小限制和反向代理 timeout。
- 横屏/竖屏视频上的坐标换算。
- job 轮询是否需要跨页面刷新恢复。
- `project_id` 由后端生成还是宿主业务生成。
- 客户端只保存 project ID 和返回 URL，不推断服务器路径。
