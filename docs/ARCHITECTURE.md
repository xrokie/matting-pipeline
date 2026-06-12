# 架构说明

本项目是一个面向生产接入的交互式视频背景替换管线。核心原则是模型环境隔离、HTTP 接口稳定、运行时数据可追踪。

## 组件划分

```text
app/api_server/
  main.py             FastAPI 路由和流程编排
  jobs.py             GPU 重任务单 worker 异步队列
  runner.py           子进程执行工具
  project_files.py    state.json 读取、URL 映射、路径安全检查
  mask_registry.py    SAM2 点选结果的 mask 注册和合并
  config.py           基于环境变量的配置

app/frontend/
  src/App.tsx         内置工作台 UI 和状态机
  src/api.ts          HTTP client、上传进度、轮询工具
  src/types.ts        TypeScript 接口类型

sam3/
  sam3/               SAM3.1 上游模型代码
  services/           API 调用的 SAM3.1 CLI/service wrapper
  tools/              mask 读写、overlay、合并工具

sam2/
  services/           SAM2.1 常驻点选服务 wrapper
  checkpoints/         SAM2.1 checkpoint 目录，部署时放置

MatAnyone2/
  matanyone2/         MatAnyone2 上游代码
  services/           matting CLI、背景合成；保留 SAM2 旧兼容入口
```

## 进程与环境边界

三个 Python 环境必须分开：

```text
sam3         Python 3.12，numpy<2，负责 SAM3.1 首帧 mask
matanyone2   Python 3.10，负责 MatAnyone2 视频 matting 和 SAM2.1 点选服务
matting_api  Python 3.11，负责 FastAPI、上传、状态文件、任务队列
```

API 进程不直接 import SAM3.1 或 MatAnyone2。模型工作统一通过子进程调用：

```text
conda run --no-capture-output -n sam3 python -m services.mask_service_cli ...
conda run --no-capture-output -n matanyone2 python -m services.matting_project_cli ...
```

这样可以避免依赖冲突，也便于定位模型环境内的错误。

## 运行流程

```text
POST /api/projects
  -> 保存上传视频
  -> 调用 sam3/services/mask_service_cli init
  -> 复制 input.mp4
  -> 用 FFmpeg 截取 inputs/first_frame.png
  -> 创建 state.json
  -> 如 SAM2 服务可用，预缓存首帧 embedding

POST /api/projects/{id}/masks/point
  -> 优先调用 127.0.0.1:8765 上的常驻 SAM2.1 服务
  -> 保存 retained mask 和 overlay
  -> 写入 state.json
  -> 合并 masks/final.png
  -> SAM2 不可用时回退到 SAM3.1 点选

POST /api/projects/{id}/masks/text 或 /masks/box
  -> SAM3.1 CLI 生成 retained mask
  -> 合并 masks/final.png

POST /api/projects/{id}/matting
  -> 提交单 GPU job
  -> MatAnyone2 读取 input.mp4 和 masks/final.png
  -> 将单轮 alpha 写入 rounds/
  -> 对所有 round alpha 做逐帧 max 合并，生成 results/alpha.mp4
  -> 合成 results/green.mp4

POST /api/projects/{id}/background
  -> 提交背景合成 job
  -> 保存上传背景为 inputs/background.png
  -> 使用已有 alpha 合成 results/replaced.mp4
```

## Project 目录

运行时数据位于 `${MATTING_ROOT}/projects/{project_id}`：

```text
projects/{project_id}/
  inputs/
    input.mp4
    first_frame.png
    background.png
  masks/
    retained_000.png
    final.png
  overlays/
    retained_000_overlay.png
    final_overlay.png
  rounds/
    round_000/
      alpha.mp4
      foreground.mp4
  results/
    alpha.mp4
    green.mp4
    replaced.mp4
  state.json
```

`state.json` 只保存 project-relative path。HTTP 响应会将这些路径转换成 `/files/{project_id}/...` URL。

## 状态机

项目状态由 `state.json` 中的文件字段推导：

```text
created
  -> ready_for_mask          first_frame 存在
  -> ready_for_matting       final_mask 存在
  -> ready_for_background    results.green 存在
  -> background_succeeded    results.replaced 存在
```

前端可以用 `status` 做导航，但渲染媒体时仍应检查对应 `files.*` URL 是否存在。

## 多轮 Matting

每次 matting 都追加一个 `matting_rounds` 条目。最终 `results.alpha` 是所有轮次 alpha 的逐帧 max 合并结果。

这个设计支持：

1. 先生成绿幕预览。
2. 回到 mask 阶段。
3. 清空当前 mask，但保留之前的 matting round。
4. 继续选择新对象。
5. 再跑一轮 matting，并合并结果。

`POST /api/projects/{id}/matting/undo` 会移除最后一个 matting round，并用剩余 round 重建累计 alpha/green。

## Service Wrapper 归属

当前仓库中 service wrapper 就地放在模型目录：

```text
sam3/services/
sam3/tools/
sam2/services/
MatAnyone2/services/
```

SAM2.1 服务的真实实现位于 `sam2/services/sam2_service/`。`MatAnyone2/services/sam2_service/` 只保留兼容 shim，旧命令仍可转发到新实现。

本仓库不存在 `app/sam3` 或 `app/MatAnyone2` 这类权威源目录。`app/scripts/sync_services.sh` 仅做兼容性校验，不再复制文件。
