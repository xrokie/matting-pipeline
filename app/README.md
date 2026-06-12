# SAM3.1 + MatAnyone2 视频换背景工程包

这是当前数字人视频换背景流程的工程化检查点。目标不是做一个单独的实验脚本，而是沉淀成可以给前端/客户端调用的后端能力。

整体流程如下：

1. 用户上传原视频。
2. 后端用 FFmpeg 截取视频第一帧。
3. 前端展示第一帧，用户通过文字 prompt、点选等方式选择本轮唯一主体和前景遮挡物。
4. SAM3.1 根据首帧生成 mask。
5. 后端将主体 mask 和多个前景 mask 合并成一张 `final.png`。
6. MatAnyone2 使用 `final.png` 对整段视频进行 video matting，生成本轮 alpha。
7. 后端将本轮 alpha 与历史轮次 alpha 做 `max` 累积，输出绿幕预览 `green.mp4`。
8. 用户可以观看绿幕效果后上传替换背景图。
9. 后端将累计 alpha 和上传背景图合成，输出换背景后的视频 `replaced.mp4`。

## 当前架构

目前不建议强行统一 SAM3.1 和 MatAnyone2 的 Python 环境。两个模型依赖差异较大，工业落地第一阶段采用进程隔离更稳。

当前分为两个模型环境：

```text
sam3 环境，Python 3.12
  -> 负责首帧 mask 生成

matanyone2 环境，Python 3.10
  -> 负责整段视频 matting 和背景合成
```

后续 API 服务通过子进程调用两个 worker：

```text
API server
  -> conda run -n sam3 ...
  -> conda run -n matanyone2 ...
```

这样做的好处是：

- 不需要为统一环境解决复杂依赖冲突。
- SAM3.1 和 MatAnyone2 可以独立升级。
- 后续 Docker 化时可以拆成两个镜像。
- 单张 4090 上可以通过任务队列控制 GPU 占用。

## 推荐运行目录

建议 WSL 中的最终目录结构如下：

```text
~/matting/
  sam3/
    sam3/
    services/
    tools/
    models/
      sam3.1/sam3.1_multiplex.pt
  MatAnyone2/
    matanyone2/
    services/
    pretrained_models/matanyone2.pth
  app/
    api_server/
    frontend/
    docs/
    scripts/
  projects/
    {project_id}/
```

其中：

```text
~/matting/sam3
  官方 SAM3 代码 + 我们新增的 mask 服务封装

~/matting/MatAnyone2
  官方 MatAnyone2 代码 + 我们新增的 matting 服务封装

~/matting/app
  API、前端、文档、脚本，以及服务封装的源头副本

~/matting/sam3/models
  SAM3.1 模型权重

~/matting/projects
  每个用户任务一个项目目录
```

`app/sam3` 和 `app/MatAnyone2` 是服务封装的唯一源头。部署或更新后，用下面的脚本同步到完整模型仓库：

```bash
bash ~/matting/app/scripts/sync_services.sh
```

## 项目目录约定

每个任务都对应一个独立 project：

```text
projects/{project_id}/
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
  results/
    alpha.mp4
    green.mp4
    foreground.mp4
    replaced.mp4
    replaced_no_audio.mp4
    matanyone2_raw/
  rounds/
    round_000/
      alpha.mp4
      foreground.mp4
    round_001/
      alpha.mp4
      foreground.mp4
  state.json
```

说明：

- `input.mp4` 是用户上传的原视频。
- `background.png` 是第三阶段上传的背景图，会统一转成 PNG。
- `first_frame.png` 是 FFmpeg 截取的首帧。
- `subject.png` 是主体 mask，建议只允许一个主体。
- `foreground_000.png`、`foreground_001.png` 是多次添加的前景/遮挡物 mask。
- `final.png` 是最终给 MatAnyone2 使用的合并 mask。
- `overlays/` 下面是给前端预览用的可视化图。
- `rounds/round_xxx/alpha.mp4` 是每一轮 MatAnyone2 的独立 alpha。
- `results/alpha.mp4` 是所有轮次 alpha 通过 max 累积后的结果。
- `results/green.mp4` 是第一阶段绿幕预览视频。
- `results/replaced.mp4` 是第三阶段最终换背景视频。

`state.json` 里推荐使用 project 内相对路径，例如：

```text
inputs/input.mp4
masks/final.png
results/replaced.mp4
```

不要在前端直接暴露服务器绝对路径。API 服务应该把这些相对路径转换成文件访问 URL。

## 模型权重路径

当前约定的模型文件：

```bash
~/matting/sam3/models/sam3.1/sam3.1_multiplex.pt
~/matting/MatAnyone2/pretrained_models/matanyone2.pth
```

SAM3.1 checkpoint 当前来自 ModelScope。运行时可能出现少量 `missing_keys` 提示，只要生成的 mask 质量正常，就可以继续使用。

## 命令行流程

下面是当前已经跑通的 CLI 流程。`api_server` 已经基于这些命令封装了 HTTP 接口。

### 1. 初始化项目

在 SAM3 仓库中执行：

```bash
cd ~/matting/sam3
conda activate sam3

python -m services.mask_service_cli init \
  --project ~/matting/projects/avatar_test \
  --video ~/matting/MatAnyone2/inputs/video/avatar.mp4
```

输出：

```text
inputs/input.mp4
inputs/background.png
inputs/first_frame.png
state.json
```

### 2. 设置主体 mask

主体建议保持唯一。重复执行该命令会替换 `masks/subject.png`。

```bash
python -m services.mask_service_cli set-subject-text \
  --project ~/matting/projects/avatar_test \
  --checkpoint ~/matting/sam3/models/sam3.1/sam3.1_multiplex.pt \
  --text "person"
```

打开主体预览：

```bash
explorer.exe "$(wslpath -w ~/matting/projects/avatar_test/overlays/subject_overlay.png)"
```

### 3. 添加前景 mask

前景是可叠加的，适合桌子、麦克风、电脑、桌面遮挡物等需要保留在新背景里的对象。

文字 prompt：

```bash
python -m services.mask_service_cli add-foreground-text \
  --project ~/matting/projects/avatar_test \
  --checkpoint ~/matting/sam3/models/sam3.1/sam3.1_multiplex.pt \
  --text "desk"
```

点选 prompt：

```bash
python -m services.mask_service_cli add-foreground-point \
  --project ~/matting/projects/avatar_test \
  --checkpoint ~/matting/sam3/models/sam3.1/sam3.1_multiplex.pt \
  --point 640 780
```

point 坐标格式：

```text
x y
```

坐标基于 `inputs/first_frame.png` 的原始像素尺寸。前端如果缩放展示了首帧，需要先把画布坐标换算回原图坐标再传给后端。

### 4. 撤销最后一个前景

```bash
python -m services.mask_service_cli undo-foreground \
  --project ~/matting/projects/avatar_test
```

### 5. 查看当前项目状态

```bash
python -m services.mask_service_cli state \
  --project ~/matting/projects/avatar_test
```

### 6. 运行一轮 MatAnyone2 并生成绿幕

在 MatAnyone2 仓库中执行：

```bash
cd ~/matting/MatAnyone2
conda activate matanyone2

python -m services.matting_project_cli \
  --project ~/matting/projects/avatar_test
```

### 7. 上传或指定背景并合成最终视频

```bash
python -m services.matting_project_cli \
  --project ~/matting/projects/avatar_test \
  --compose-background \
  --background ~/matting/MatAnyone2/inputs/bg.png
```

Matting 输出：

```text
rounds/round_000/alpha.mp4
results/alpha.mp4
results/green.mp4
```

背景合成后会额外输出：

```text
results/replaced.mp4
```

再次设置主体/前景后重复执行 MatAnyone2，会生成 `round_001`，并把新 alpha 与历史 alpha 做 max 合并。

### 8. 撤销上一轮绿幕

```bash
python -m services.matting_project_cli \
  --project ~/matting/projects/avatar_test \
  --undo-round
```

撤销后会回到上一轮累计 alpha 和绿幕视频。旧的换背景结果会失效，需要重新上传背景合成。

打开结果目录：

```bash
explorer.exe "$(wslpath -w ~/matting/projects/avatar_test/results)"
```

## 运行环境要求

这份包对应的已验证环境如下，仅用于说明当前可运行组合：

```text
sam3:
  Python 3.12.13
  numpy 1.26.4
  torch 2.10.0+cu128
  CUDA available: true

matanyone2:
  Python 3.10.20
  numpy 2.2.6
  torch 2.5.1+cu121
  opencv-python 4.13.0
  CUDA available: true
```

注意：不要在 `sam3` 环境里安装最新版 `opencv-python`。它可能会把 NumPy 升级到 `>=2`，而 SAM3 当前要求 `numpy<2`。

## 前端接入说明

本包已包含最小 FastAPI 服务：

```text
api_server/
  main.py
  config.py
  schemas.py
  runner.py
  project_files.py
  jobs.py
```

推荐的 HTTP API 合同见：

```text
docs/API_HANDOFF.md
```

当前 React 前端支持：

- 选择原视频后自动上传并截取首帧。
- 展示后端截取的首帧。
- 通过英文文字 prompt 添加保留对象。
- 通过点选添加保留对象。
- 多个保留对象会自动合并为 `final_mask`。
- 每次操作后展示 overlay 预览图。
- 确认抠像后自动发起绿幕 matting 任务。
- 展示任务状态和 MatAnyone2 帧级进度条。
- 绿幕生成后停留在检查阶段，可返回补对象或继续替换背景。
- 选择背景图后自动合成 `results/replaced.mp4`。

SAM3.1 本地仓库已确认支持 point prompt。服务封装在 `services/mask_service/sam3_mask_service.py` 内置了 point fallback：如果当前 SAM3.1 的 `Sam3Processor` 没有 `add_point_prompt` 方法，会直接调用底层 `append_points` 和 `_forward_grounding`。因此 WSL 只需要同步 `services/`，不必手工 patch SAM3.1 源码。框选接口仍可作为后端兼容路径保留，但前端主流程不再使用框选。

### 启动 API

建议单独创建 API 环境：

```bash
conda create -n matting_api python=3.11 -y
conda activate matting_api
pip install -r ~/matting/app/api_server/requirements.txt
```

启动服务：

```bash
bash ~/matting/app/scripts/run_api.sh
```

默认地址：

```text
http://127.0.0.1:8000
```

图形界面：

```text
http://127.0.0.1:8000/app
```

浏览器接口文档：

```text
http://127.0.0.1:8000/docs
```

API 冒烟测试：

```bash
bash ~/matting/app/scripts/smoke_test_wsl_api_three_stage.sh
```

GUI 演示流程：

1. 打开 `http://127.0.0.1:8000/app`。
2. 上传原视频并等待首帧出现。
3. 用 `person`、`chair` 等英文 prompt 或画面点选添加保留对象。
4. 需要桌子、麦克风等遮挡物时，继续添加为新的保留对象。
5. 点击“进入绿幕生成”，等待 `green.mp4`。
6. 检查绿幕，必要时返回补对象；确认后进入背景替换。
7. 选择背景图并等待自动合成完成。
8. 播放最终 `replaced.mp4`。

说明：

- 保留对象是追加式：每次文字或点选都会新增一个 `retained_mask`。
- 每一轮绿幕都会保存为独立 round，系统会将所有 round 的 alpha 做 max 累积。
- 如果水杯、手机等手持道具在后半段消失，推荐返回继续添加对象并再跑一轮绿幕。
- 撤销抠像会回退上一条保留对象；撤销绿幕只撤销上一轮 MatAnyone2 结果。

## 三阶段说明

第一阶段是上传视频：

```text
input.mp4 -> ffmpeg -> first_frame.png
```

第二阶段是抠像和 Matting 绿幕：

```text
本轮 subject_mask + foreground_masks -> final_mask
final_mask -> MatAnyone2 -> rounds/round_xxx/alpha.mp4
所有 round alpha -> max -> results/alpha.mp4
results/alpha.mp4 + 绿色背景 -> results/green.mp4
```

第三阶段是替换背景：

```text
results/alpha.mp4 + 上传背景图 -> results/replaced.mp4
```


## 生产化注意事项

- 视频 matting 是长任务，必须按异步 job 设计。
- 单张 RTX 4090 上建议一次只跑一个 MatAnyone2 任务。
- SAM3.1 的 prompt 生成可以先同步执行，后面再统一进队列。
- 当前通过轮询读取 job 状态，后端会解析 MatAnyone2 tqdm 输出里的 `当前帧/总帧数` 更新进度。
- 后续可以改成 WebSocket 或 SSE 推送进度。
- 所有上传文件和生成结果都放在 `projects/{project_id}` 下。
- 生产环境不要直接暴露本机路径，需要转换成受控文件 URL。
- API server 不直接 import SAM3 或 MatAnyone2，而是通过子进程调用：

```bash
conda run -n sam3 python -m services.mask_service_cli ...
conda run -n matanyone2 python -m services.matting_project_cli ...
```

这样前后端交接时，前端只需要关心 HTTP 接口，不需要关心模型环境、conda、GPU、文件路径等内部细节。
