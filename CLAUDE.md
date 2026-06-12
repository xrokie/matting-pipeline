# CLAUDE.md

这是给 coding agent 的简短操作指南。面向人的正式文档在 [docs/](docs/)。

## 优先阅读

1. [docs/AI_CONTEXT.md](docs/AI_CONTEXT.md)
2. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
3. 修改 API 或前端边界时读 [docs/API_CONTRACT.md](docs/API_CONTRACT.md)
4. 修改部署、脚本、checkpoint 或启动流程时读 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

## 硬性约束

- 不要合并三个 conda 环境。
- `app/api_server` 不要直接 import SAM3.1 或 MatAnyone2 的模型模块。
- 模型调用必须通过 `conda run --no-capture-output -n ... python -m services...`。
- GPU 重任务继续通过 `app/api_server/jobs.py` 单 worker 串行执行。
- 运行时项目文件必须放在 `${MATTING_ROOT}/projects`，不要写进源码目录。
- smoke/test bash 脚本必须放在 `app/scripts/smoke/`；生产启动入口保留为 `app/scripts/run_api.sh`。
- 当前仓库的 service wrapper 就地放在：
  - `sam3/services/`
  - `sam3/tools/`
  - `sam2/services/`
  - `MatAnyone2/services/`
  本仓库不存在权威的 `app/sam3` 或 `app/MatAnyone2` 源目录。

## 重要运行细节

- 默认 `MATTING_ROOT` 是 `~/matting`。
- SAM3.1 checkpoint 默认路径：`~/matting/sam3/models/sam3.1/sam3.1_multiplex.pt`。
- MatAnyone2 checkpoint 默认路径：`~/matting/MatAnyone2/pretrained_models/matanyone2.pth`。
- SAM2.1 checkpoint 默认路径：`~/matting/sam2/checkpoints/sam2.1_hiera_base_plus.pt`。
- `/masks/point` 优先使用 `8765` 端口上的常驻 SAM2.1 服务；不可用时回退到 SAM3.1。
- `.mov` / iPhone 视频依赖 `sam3/services/mask_service/project_store.py` 中显式 sRGB 的 FFmpeg 首帧抽取参数；不要随意删除这些颜色参数。
- `max_size=-1` 会消耗大量内存。UI/API 默认使用 `720`。

## 验证

相关改动后优先跑：

```bash
cd ~/matting/app/frontend
npm run build

bash ~/matting/app/scripts/smoke/smoke_test_wsl_api_three_stage.sh
bash ~/matting/app/scripts/smoke/smoke_test_wsl_cli_three_stage.sh
```
