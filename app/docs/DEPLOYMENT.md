# WSL 部署说明

本文档说明如何把当前完整 `matting/` 工程恢复到 WSL 运行环境中。

这个包只包含：

- SAM3.1 服务封装。
- MatAnyone2 服务封装。
- FastAPI 服务。
- 一个测试用例 `avatar_test`。
- 中文 README / API 交接文档 / 部署文档。
- CLI 和 API 冒烟测试脚本。

这个包通常不包含：

- 模型权重。
- 历史输出视频。

## 1. 目标运行目录

WSL 中建议保持如下目录。当前交付目录本身已经按这个结构组织：

```text
~/matting/
  sam3/
  MatAnyone2/
  app/
    api_server/
    frontend/
    docs/
    scripts/
  projects/
    avatar_test/
```

其中：

```text
~/matting/sam3
  已安装好的 SAM3.1 仓库

~/matting/MatAnyone2
  已安装好的 MatAnyone2 仓库

~/matting/sam3/models
  SAM3.1 模型权重目录

~/matting/projects/avatar_test
  唯一保留的测试用例
```

## 2. 放置工程包

如果拿到的是完整 `matting/` 目录，直接放到 WSL 用户目录：

```bash
mv /path/to/matting ~/matting
```

如果拿到的是压缩包，解压后也应得到：

```text
~/matting/
  app/
  sam3/
  MatAnyone2/
```

## 3. 同步服务封装

```bash
bash ~/matting/app/scripts/sync_services.sh
```

该脚本以 `~/matting/app` 作为唯一源头，将服务封装同步到完整模型仓库：

```text
~/matting/app/sam3/services      -> ~/matting/sam3/services
~/matting/app/sam3/tools         -> ~/matting/sam3/tools
~/matting/app/MatAnyone2/services -> ~/matting/MatAnyone2/services
```

脚本会排除 `.DS_Store`、`._*`、`__pycache__`、`*.pt`、`*.pth` 等不应进入同步层的文件。

## 4. 同步唯一测试用例

```bash
mkdir -p ~/matting/projects
rsync -av --delete ~/matting/app/projects/avatar_test/ ~/matting/projects/avatar_test/
```

注意：这里使用 `--delete` 是为了保证 `avatar_test` 目录和交付包保持一致，清掉本地已有的历史输出。

## 5. 检查 API 服务文件

API 服务直接保留在：

```text
~/matting/app/api_server
```

不需要同步进 `sam3` 或 `MatAnyone2` 仓库。

## 6. 检查模型权重

```bash
ls -lh ~/matting/sam3/models/sam3.1/sam3.1_multiplex.pt
ls -lh ~/matting/MatAnyone2/pretrained_models/matanyone2.pth
```

如果文件不存在，需要先补齐模型权重。

`MatAnyone2` 推理会优先使用 `--ckpt` 指定的本地 checkpoint。只有该文件不存在时，才尝试从官方 release 自动下载。

## 7. 检查 SAM3.1 环境

```bash
conda run -n sam3 python -c "import sys, numpy, torch; print(sys.version); print(numpy.__version__); print(torch.__version__); print(torch.cuda.is_available())"
```

期望：

```text
Python 3.12.x
numpy 1.26.x
CUDA true
```

不要在 `sam3` 环境里安装最新版 `opencv-python`，否则可能把 NumPy 升到 `>=2`，导致 SAM3 依赖冲突。

## 8. 检查 MatAnyone2 环境

```bash
conda run -n matanyone2 python -c "import sys, torch, cv2; print(sys.version); print(torch.__version__); print(cv2.__version__); print(torch.cuda.is_available())"
```

期望：

```text
Python 3.10.x
CUDA true
```

## 9. 验证测试用例状态

```bash
cd ~/matting/sam3
conda activate sam3

python -m services.mask_service_cli state \
  --project ~/matting/projects/avatar_test
```

`avatar_test` 已经包含：

```text
inputs/input.mp4
inputs/background.png
inputs/first_frame.png
masks/subject.png
masks/foreground_000.png
masks/final.png
overlays/final_overlay.png
state.json
```

## 10. 查看首帧和 mask 预览

```bash
explorer.exe "$(wslpath -w ~/matting/projects/avatar_test/inputs/first_frame.png)"
explorer.exe "$(wslpath -w ~/matting/projects/avatar_test/overlays/final_overlay.png)"
```

## 11. 运行 MatAnyone2

```bash
cd ~/matting/MatAnyone2
conda activate matanyone2

python -m services.matting_project_cli \
  --project ~/matting/projects/avatar_test
```

运行完成后会生成：

```text
~/matting/projects/avatar_test/results/alpha.mp4
~/matting/projects/avatar_test/results/foreground.mp4
~/matting/projects/avatar_test/results/replaced.mp4
```

打开结果：

```bash
explorer.exe "$(wslpath -w ~/matting/projects/avatar_test/results)"
```

## 12. CLI 冒烟测试

如果希望从初始化到出片完整跑一遍，优先使用三阶段脚本：

```bash
bash ~/matting/app/scripts/smoke_test_wsl_cli_three_stage.sh
```

默认使用：

```text
ROOT=$HOME/matting
PROJECT=$HOME/matting/projects/avatar_test
VIDEO=$HOME/matting/MatAnyone2/inputs/video/avatar.mp4
BACKGROUND=$HOME/matting/MatAnyone2/inputs/bg.png
SAM_CKPT=$HOME/matting/sam3/models/sam3.1/sam3.1_multiplex.pt
```

如需覆盖：

```bash
PROJECT=~/matting/projects/avatar_test \
VIDEO=~/matting/MatAnyone2/inputs/video/avatar.mp4 \
BACKGROUND=~/matting/MatAnyone2/inputs/bg.png \
SAM_CKPT=~/matting/sam3/models/sam3.1/sam3.1_multiplex.pt \
bash ~/matting/app/scripts/smoke_test_wsl_cli_three_stage.sh
```

## 13. 安装 API 环境

建议 API 使用独立 conda 环境：

```bash
conda create -n matting_api python=3.11 -y
conda activate matting_api
pip install -r ~/matting/app/api_server/requirements.txt
```

API server 不直接 import SAM3.1 或 MatAnyone2，而是通过子进程调用：

```bash
conda run -n sam3 python -m services.mask_service_cli ...
conda run -n matanyone2 python -m services.matting_project_cli ...
```

## 14. 构建 React 前端

FastAPI 启动时会优先挂载 `~/matting/app/frontend/dist`。因此第一次部署或前端改动后，需要先构建前端，再启动或重启 API。

```bash
cd ~/matting
bash app/scripts/smoke_test_wsl_frontend_build.sh
```

## 15. 启动 API 服务

```bash
conda activate matting_api
bash ~/matting/app/scripts/run_api.sh
```

默认监听：

```text
http://127.0.0.1:8000
```

查看健康检查：

```bash
curl http://127.0.0.1:8000/health
```

浏览器打开接口文档：

```text
http://127.0.0.1:8000/docs
```

## 16. 三阶段 API 测试

启动 API 后，另开一个 WSL 终端跑三阶段 API 冒烟测试：

```bash
cd ~/matting
bash app/scripts/smoke_test_wsl_api_three_stage.sh
```

默认测试素材：

```text
VIDEO=$HOME/matting/MatAnyone2/inputs/video/avatar.mp4
BACKGROUND=$HOME/matting/MatAnyone2/inputs/bg.png
MAX_SIZE=720
```

浏览器打开图形界面：

```text
http://127.0.0.1:8000/app
```

GUI 演示流程：

```text
上传视频和背景图
  -> 上传并截首帧
  -> 通过 prompt 或点选设置主体
  -> 通过 prompt 或点选添加前景
  -> 开始生成视频
  -> 检查 green.mp4，必要时返回补主体
  -> 选择背景图并自动合成最终视频
  -> 播放 replaced.mp4
```

## 16. API 冒烟测试

另开一个终端执行：

```bash
bash ~/matting/app/scripts/smoke_test_api.sh
```

该脚本会依次调用：

```text
GET  /health
POST /api/projects
POST /api/projects/{project_id}/subject/text
POST /api/projects/{project_id}/foreground/text
POST /api/projects/{project_id}/matting
```

Matting 是后台任务。脚本会输出 `job_id`，之后用：

```bash
curl http://127.0.0.1:8000/api/jobs/{job_id}
```

查询任务状态。
