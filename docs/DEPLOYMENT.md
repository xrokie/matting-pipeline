# 部署指南

这是新机器部署的权威指南，覆盖后端环境、模型 checkpoint、前端构建、服务启动和冒烟测试。

## 目标机器

建议环境：

- Linux 或 WSL2，并能访问 NVIDIA GPU。
- CUDA driver 与所选 PyTorch CUDA wheel 兼容。
- Conda 或 Miniconda。
- Node.js 和 npm，用于构建前端。
- `ffmpeg` 可在 `PATH` 中访问。
- 足够内存。测试先用 `max_size=720`，全分辨率推理可能需要大量 RAM。

默认部署根目录：

```text
~/matting
```

如需修改：

```bash
export MATTING_ROOT=/path/to/matting
```

## 1. 放置仓库

生产路径应直接包含仓库内容：

```text
~/matting/
  app/
  docs/
  sam3/
  MatAnyone2/
```

如果仓库克隆在其他路径：

```bash
mv /path/to/matting-pipeline ~/matting
```

## 2. 系统依赖

Ubuntu/WSL 示例：

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg git curl build-essential
```

检查：

```bash
ffmpeg -version
nvidia-smi
```

## 3. Conda 环境

三个环境必须隔离。

### SAM3.1 环境

```bash
conda create -n sam3 python=3.12 -y
conda activate sam3
pip install torch==2.10.0 torchvision --index-url https://download.pytorch.org/whl/cu128
cd ~/matting/sam3
pip install -e .
```

上游 SAM3.1 的可选加速依赖可能需要额外 CUDA 编译条件。先确保基础环境可运行，再考虑安装。

### MatAnyone2 与 SAM2 点选服务环境

```bash
conda create -n matanyone2 python=3.10 -y
conda activate matanyone2
pip install torch==2.10.0 torchvision --index-url https://download.pytorch.org/whl/cu128
cd ~/matting/MatAnyone2
pip install -e .
```

SAM2 点选服务会 import `sam2`。请在同一个 `matanyone2` 环境中，按你的部署来源安装 SAM2.1 包。服务期望存在配置：

```text
configs/sam2.1/sam2.1_hiera_b+.yaml
```

### API 环境

```bash
conda create -n matting_api python=3.11 -y
conda activate matting_api
pip install -r ~/matting/app/api_server/requirements.txt
pip install numpy Pillow
```

`app/api_server/mask_registry.py` 需要 `numpy` 和 `Pillow` 来注册 SAM2 点选结果并合并 mask。

## 4. 模型 Checkpoint

创建目录：

```bash
mkdir -p ~/matting/sam3/models/sam3.1
mkdir -p ~/matting/MatAnyone2/pretrained_models
mkdir -p ~/matting/sam2/checkpoints
```

必需文件：

```text
~/matting/sam3/models/sam3.1/sam3.1_multiplex.pt
~/matting/MatAnyone2/pretrained_models/matanyone2.pth
~/matting/sam2/checkpoints/sam2.1_hiera_base_plus.pt
```

### SAM3.1

SAM3.1 checkpoint 统一走 ModelScope，不走 Hugging Face 授权流程。

模型页面：

```text
https://modelscope.cn/models/facebook/sam3.1
```

下载命令：

```bash
pip install modelscope

modelscope download \
  --model facebook/sam3.1 \
  sam3.1_multiplex.pt \
  --local_dir ~/matting/sam3/models/sam3.1
```

如果生产环境使用内部镜像或离线包，请保证最终文件名和路径一致：

```text
~/matting/sam3/models/sam3.1/sam3.1_multiplex.pt
```

### MatAnyone2

```bash
curl -L \
  https://github.com/pq-yang/MatAnyone2/releases/download/v1.0.0/matanyone2.pth \
  -o ~/matting/MatAnyone2/pretrained_models/matanyone2.pth
```

MatAnyone2 也能在首次推理时自动下载，但生产部署建议提前放好，避免首次请求才触发外网下载。

### SAM2.1

从你的 SAM2.1 官方来源下载 `hiera_base_plus` checkpoint，并放到：

```text
~/matting/sam2/checkpoints/sam2.1_hiera_base_plus.pt
```

如果该文件缺失，SAM2 点选服务启动会失败。

### 校验 Checkpoint

```bash
ls -lh ~/matting/sam3/models/sam3.1/sam3.1_multiplex.pt
ls -lh ~/matting/MatAnyone2/pretrained_models/matanyone2.pth
ls -lh ~/matting/sam2/checkpoints/sam2.1_hiera_base_plus.pt
```

## 5. 构建前端

```bash
cd ~/matting/app/frontend
npm install
npm run build
```

FastAPI 会把 `app/frontend/dist` 挂载到 `/app`。生产环境应始终构建 `dist`。

## 6. 校验 Service Wrapper 布局

```bash
bash ~/matting/app/scripts/sync_services.sh
```

当前仓库的 wrapper 已经放在生产目录内。这个脚本只校验文件是否存在，不再复制文件。

## 7. 启动服务

```bash
conda activate matting_api
bash ~/matting/app/scripts/run_api.sh
```

`run_api.sh` 会：

1. 如果未设置 `MATTING_ROOT`，默认使用 `~/matting`。
2. 检查 `8765` 端口的 SAM2.1 服务；不可用则启动。
3. 启动 FastAPI/Uvicorn。

默认地址：

```text
API:  http://127.0.0.1:8000
UI:   http://127.0.0.1:8000/app
Docs: http://127.0.0.1:8000/docs
SAM2: http://127.0.0.1:8765
```

常用覆盖：

```bash
HOST=0.0.0.0 PORT=8000 SAM2_PORT=8765 bash ~/matting/app/scripts/run_api.sh
```

## 8. 健康检查

```bash
curl http://127.0.0.1:8000/health
```

重点字段：

```json
{
  "status": "ok",
  "sam3_dir_exists": true,
  "matanyone2_dir_exists": true,
  "sam3_checkpoint_exists": true,
  "matanyone2_checkpoint_exists": true
}
```

SAM2：

```bash
curl http://127.0.0.1:8765/health
```

## 9. 冒烟测试

冒烟测试是非生产脚本，统一放在 `app/scripts/smoke/`。

前端构建检查：

```bash
bash ~/matting/app/scripts/smoke/smoke_test_wsl_frontend_build.sh
```

API 三阶段测试，需先启动 API：

```bash
bash ~/matting/app/scripts/smoke/smoke_test_wsl_api_three_stage.sh
```

直接 CLI 重模型测试：

```bash
bash ~/matting/app/scripts/smoke/smoke_test_wsl_cli_three_stage.sh
```

常用覆盖：

```bash
ROOT=~/matting \
VIDEO=~/matting/MatAnyone2/inputs/video/avatar.mp4 \
BACKGROUND=~/matting/MatAnyone2/inputs/bg.png \
MAX_SIZE=720 \
bash ~/matting/app/scripts/smoke/smoke_test_wsl_api_three_stage.sh
```

## 10. 生产注意事项

- checkpoint 不进 git。
- `projects/` 运行时输出不进 git。
- 不要从 `sam3` 或 `MatAnyone2` 目录启动 API server。
- 不要把 MatAnyone2 依赖装进 `sam3` 环境。
- 不要把 SAM3.1 依赖装进 `matting_api` 环境。
- 验收测试优先使用 `max_size=720`，确认内存后再提高。
