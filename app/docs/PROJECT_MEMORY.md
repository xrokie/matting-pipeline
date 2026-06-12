# 项目工程记忆：SAM3.1 + MatAnyone2 视频背景替换

本文档用于在新的 Codex 对话中快速恢复上下文。当前本地项目目录为完整 `matting/` 快照：

```text
/Users/macmini005/ICC/bgreplace/matting
```

WSL 中对应的推荐部署目录为：

```text
~/matting/app
~/matting/sam3
~/matting/MatAnyone2
~/matting/projects
```

## 一句话目标

构建一个工业化的数字人/人物视频背景替换工具：用户选择原视频后自动上传并截取首帧，在首帧上通过文字 prompt 或点选选择主体和前景，生成绿幕视频后先检查结果，再上传背景图并合成最终视频。

当前选定技术路线：

```text
SAM3.1 -> 首帧主体/前景 mask
MatAnyone2 -> 整段视频 matting / alpha 传播
OpenCV + FFmpeg -> 绿幕预览、背景合成、音频封装
FastAPI -> 后端接口
Vite + React + TypeScript -> 三阶段前端界面
```

## 当前产品流程

项目已从“独立 target 模式”改为更容易理解的三阶段统一流程。

### 第一阶段：上传视频

用户选择原视频后，前端立即上传，后端截取首帧。前端展示上传和截帧进度，截帧完成后进入抠像阶段。

### 第二阶段：确认抠像并生成绿幕

前端展示首帧，用户可以：

- 设置唯一主体 mask：文字 prompt 或画面点选。
- 添加多个前景 mask：文字 prompt 或画面点选。
- 查看 overlay 预览。
- 确认抠像后进入 MatAnyone2 绿幕生成。

这一轮会将当前：

```text
subject_mask + foreground_masks -> final_mask
```

交给 MatAnyone2，得到本轮 alpha：

```text
rounds/round_000/alpha.mp4
rounds/round_000/foreground.mp4
```

如果用户继续下一轮，系统会得到：

```text
rounds/round_001/alpha.mp4
rounds/round_001/foreground.mp4
```

所有轮次 alpha 会做逐帧 max 合并：

```text
results/alpha.mp4 = max(round_000_alpha, round_001_alpha, ...)
```

再生成绿幕预览：

```text
results/green.mp4
```

绿幕生成完成后，前端停留在检查阶段展示 `green.mp4`，用户可以返回抠像阶段补主体，或继续进入背景替换阶段。

### 第三阶段：替换背景

用户上传背景图后，系统基于已有 alpha 单独合成最终背景替换视频：

```text
results/replaced.mp4
```

换背景不会重跑 MatAnyone2。

## 主体与前景的定义

主体：

- 本轮 MatAnyone2 要重点跟踪的唯一主要对象。
- 通常是数字人、人物、可动物体、手持物体。
- 再次设置主体会替换当前主体 mask。
- 如果水杯、手机等手持道具在视频后半段丢失，不建议只把它当固定前景；更推荐把它作为下一轮主体重新选择，再跑一轮绿幕。

前景：

- 需要和主体一起保留的遮挡物或场景物体。
- 适合桌子、椅子、麦克风、电脑屏幕、桌面遮挡物。
- 前景是追加式的，多次添加会合并到 `final_mask`。
- 前景适合相对固定或与主体关系稳定的物体。

## 当前代码结构

```text
app/
  README.md
  api_server/
    main.py
    config.py
    jobs.py
    project_files.py
    runner.py
    schemas.py
    requirements.txt
  frontend/
    package.json
    vite.config.ts
    src/
      App.tsx
      api.ts
      types.ts
      styles.css
  docs/
    API_HANDOFF.md
    DEPLOYMENT.md
    FRONTEND_ENGINEERING.md
    PROJECT_MEMORY.md
  scripts/
    run_api.sh
    smoke_test_api.sh
    smoke_test_cli.sh
  sam3/
    services/
      mask_service_cli.py
      mask_service/
        project_store.py
        sam3_mask_service.py
    tools/
      mask_ops.py
  MatAnyone2/
    services/
      matting_project_cli.py
      matting_service/
        compose_bg.py
  projects/
    avatar_test/
```

注意：`app/sam3` 和 `app/MatAnyone2` 只保存我们新增的 service 封装。当前 `matting/sam3` 和 `matting/MatAnyone2` 是补完整后的上游模型仓库。部署到 WSL 时，应以 `app/` 作为唯一源头，把服务封装同步到完整模型仓库：

```text
~/matting/sam3/services
~/matting/sam3/tools
~/matting/MatAnyone2/services
```

推荐使用：

```bash
bash ~/matting/app/scripts/sync_services.sh
```

## WSL 运行环境

推荐继续保持两个模型环境隔离，不要强行统一 Python 版本。

```text
sam3 环境：
  Python 3.12
  负责 SAM3.1 首帧 mask

matanyone2 环境：
  Python 3.10
  负责 MatAnyone2 video matting

matting_api 环境：
  Python 3.11
  负责 FastAPI 服务和前端静态页面
```

模型权重约定：

```text
~/matting/sam3/models/sam3.1/sam3.1_multiplex.pt
~/matting/MatAnyone2/pretrained_models/matanyone2.pth
```

SAM3.1 checkpoint 使用 ModelScope 版本可以运行。加载时出现少量 `missing_keys` 曾经出现过，只要 mask 输出正常，当前判断可继续使用。

## 关键 API

创建项目：

```http
POST /api/projects
```

当前只要求上传原视频，背景图在第三阶段上传。

设置主体：

```http
POST /api/projects/{project_id}/subject/text
POST /api/projects/{project_id}/subject/box
```

添加前景：

```http
POST /api/projects/{project_id}/foreground/text
POST /api/projects/{project_id}/foreground/box
```

撤销最后一个前景：

```http
POST /api/projects/{project_id}/foreground/undo
```

撤销上一版抠像：

```http
POST /api/projects/{project_id}/mask/undo
```

生成/叠加一轮绿幕：

```http
POST /api/projects/{project_id}/matting
```

上传背景并合成：

```http
POST /api/projects/{project_id}/background
```

撤销上一轮绿幕：

```http
POST /api/projects/{project_id}/matting/undo
```

查询任务：

```http
GET /api/jobs/{job_id}
```

文件访问：

```http
GET /files/{project_id}/{path}
```

图形界面：

```text
http://127.0.0.1:8000/app/
```

局域网访问时使用 Windows 主机 IP，例如：

```text
http://192.168.101.24:8000/app/
```

API 启动时需要监听：

```text
0.0.0.0:8000
```

## 关键 CLI

启动 API：

```bash
cd ~/matting
conda activate matting_api
bash ~/matting/app/scripts/run_api.sh
```

初始化项目：

```bash
cd ~/matting/sam3
conda activate sam3

python -m services.mask_service_cli init \
  --project ~/matting/projects/avatar_demo \
  --video /path/to/input.mp4 \
  --background /path/to/background.png
```

设置主体文字：

```bash
python -m services.mask_service_cli set-subject-text \
  --project ~/matting/projects/avatar_demo \
  --checkpoint ~/matting/sam3/models/sam3.1/sam3.1_multiplex.pt \
  --text "person"
```

添加前景文字：

```bash
python -m services.mask_service_cli add-foreground-text \
  --project ~/matting/projects/avatar_demo \
  --checkpoint ~/matting/sam3/models/sam3.1/sam3.1_multiplex.pt \
  --text "desk"
```

生成/叠加一轮绿幕：

```bash
cd ~/matting/MatAnyone2
conda activate matanyone2

python -m services.matting_project_cli \
  --project ~/matting/projects/avatar_demo \
  --warmup 10 \
  --erode 10 \
  --dilate 10 \
  --max-size 720
```

撤销上一轮绿幕：

```bash
python -m services.matting_project_cli \
  --project ~/matting/projects/avatar_demo \
  --undo-round
```

## Project 数据结构

每个任务一个 project：

```text
~/matting/projects/{project_id}/
  inputs/
    input.mp4
    background.png
    first_frame.png
  masks/
    subject.png
    foreground_000.png
    foreground_001.png
    final.png
  overlays/
    subject_overlay.png
    foreground_000_overlay.png
    final_overlay.png
  rounds/
    round_000/
      alpha.mp4
      foreground.mp4
    round_001/
      alpha.mp4
      foreground.mp4
  results/
    alpha.mp4
    green.mp4
    green_no_audio.mp4
    foreground.mp4
    replaced.mp4
    replaced_no_audio.mp4
    matanyone2_raw/
  state.json
```

`state.json` 中保存相对路径，不要保存前端可见的服务器绝对路径。API 会转换为 `/files/...` URL。

## 前端当前状态

前端是一个可嵌入大项目的三阶段 React GUI，用于把视频背景替换流程做成清晰状态机。

已实现：

- 可编辑 Project ID，默认 `avatar_demo`。
- 选择视频后自动上传并截取首帧。
- 选择背景图后自动合成最终视频。
- 展示首帧。
- 主体文字 prompt。
- 主体点选。
- 前景文字 prompt。
- 前景点选。
- 完整抠像撤销。
- mask 标签提示，例如 `person`、`desk`、`MASK_1`。
- MatAnyone2 任务进度条。
- 解析 MatAnyone2 tqdm 帧级进度。
- 展示绿幕视频 `green.mp4`。
- 绿幕检查阶段：可返回继续补主体，或进入背景替换。
- 展示换背景视频 `replaced.mp4`。
- 已完成阶段可点击回看，未完成阶段锁定。

不再在前端展示：

- 独立 target 模式。

底层历史上曾经保留过 target 相关 API 和 CLI 分支，但当前产品路线不建议暴露给用户。

## 已解决的重要问题

1. MatAnyone2 必须传首帧 mask。没有 mask 会出现尺寸不匹配或推理失败。
2. SAM3 官方 checkpoint 需要 Hugging Face 权限，后来改用 ModelScope 的 SAM3.1 checkpoint。
3. BiRefNet 可用于自动首帧抠像，但当前主线已切到 SAM3.1。
4. `open` 命令在 WSL 不存在，看图片可用：

```bash
explorer.exe "$(wslpath -w path/to/image.png)"
```

5. `save_image` 会保存逐帧图片，长视频会造成巨大存储压力，前端默认不勾选。
6. `max_size=-1` 表示不限制推理尺寸，高分辨率/长视频容易吃显存和内存。建议测试时先用 `720` 或 `1080`。
7. `replaced.mp4` 曾出现只有声音没有画面，已改为 FFmpeg 用 H.264 `libx264`、`yuv420p`、`+faststart` 重新封装。
8. MatAnyone2 tqdm 进度默认在子进程输出里，API 用 `conda run --no-capture-output` 并解析 `当前帧/总帧` 更新 job progress。
9. WSL 可能因为内存压力导致新终端 `wsl` 超时。建议 `.wslconfig` 限制内存，例如 64GB 机器给 WSL 48GB。

## WSL 内存建议

Windows 用户目录创建或编辑：

```powershell
notepad $env:USERPROFILE\.wslconfig
```

建议内容：

```ini
[wsl2]
memory=48GB
processors=12
swap=16GB
```

然后：

```powershell
wsl --shutdown
```

不要把 64GB 全部分给 WSL，Windows 自身和浏览器也需要内存。

## 当前风险和下一步

### 风险 1：多轮 alpha max 的边界质量

当前多轮逻辑是工程上最直接的：

```text
final_alpha = max(alpha_round_0, alpha_round_1, ...)
```

优点是简单、可撤销、容易解释。

风险是如果某一轮误选区域较大，错误 alpha 会被永久并入累计结果，除非撤销该轮。因此前端需要鼓励用户先看 `green.mp4` 再确认。

### 风险 2：长视频性能

MatAnyone2 对长视频和高分辨率视频压力较大。建议演示时：

```text
视频长度：5-15 秒
max_size：720 或 1080
save_image：关闭
一次只跑一个任务
```

### 风险 3：主体和前景语义仍需产品打磨

当前解释：

- 主体：可动对象，本轮唯一。
- 前景：固定遮挡物，可追加。

但真实用户会困惑“手持水杯算什么”。当前推荐是：如果水杯后期消失，就在下一轮把水杯作为主体重新选择并跑一轮，让 alpha max 合并回来。

### 风险 4：API 仍是本地 demo 级

当前 API 适合本地/局域网 demo，不是生产服务。

生产化还需要：

- 用户鉴权。
- project 权限隔离。
- 上传文件大小限制。
- 文件清理策略。
- GPU 队列。
- 任务取消。
- 错误码规范。
- WebSocket 或 SSE 推送进度。
- 日志落盘。
- Docker 化或服务化部署。

## 给下一段 Codex 对话的建议

如果继续开发，请优先做这些事：

1. 先打开并阅读：

```text
README.md
docs/API_HANDOFF.md
api_server/main.py
frontend/src/App.tsx
frontend/src/api.ts
MatAnyone2/services/matting_project_cli.py
MatAnyone2/services/matting_service/compose_bg.py
```

2. 不要重新引入“独立 target”作为前端模式，除非用户明确要求。
3. 当前产品主线是“三阶段 + 主体优先 + 高级前景 + 可撤销”。
4. 如果要调试 WSL 环境，要注意本地 macOS 项目只是工程包，真实模型仓库和 conda 环境在 WSL。
5. 如果要改部署脚本，请保持目标目录：

```text
~/matting/app
~/matting/sam3
~/matting/MatAnyone2
~/matting/projects
```

6. 如果前端要和正式客户端对接，优先把 `docs/API_HANDOFF.md` 更新成接口合同。

7. 不要把 `.DS_Store`、`._*`、`__pycache__`、模型 checkpoint 或历史输出视频打进交付包。

## 最近一次打包状态

最近一次生成的包名：

```text
matting_pipeline_app_two_stage.tar.gz
```

用户后来已把 `app/` 移动到：

```text
/Users/macmini005/ICC/bgreplace/app
```

这份文档应放在：

```text
/Users/macmini005/ICC/bgreplace/app/docs/PROJECT_MEMORY.md
```
