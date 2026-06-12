# Matting Pipeline

这是一个交互式视频背景替换管线，组合了 SAM3.1、SAM2.1、MatAnyone2、FastAPI 和 Vite/React 前端。

生产流程：

```text
上传视频
  -> 截取首帧
  -> 用文本 / 点选 / 框选选择要保留的对象
  -> SAM3.1 或 SAM2.1 生成首帧 mask
  -> MatAnyone2 将首帧 alpha 传播到整段视频
  -> 合成绿幕预览或上传背景
```

## 从这里开始

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)：系统架构、进程边界、项目状态和运行时数据流。
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)：新机器环境配置、checkpoint 放置、前端构建、服务启动和冒烟测试。
- [docs/API_CONTRACT.md](docs/API_CONTRACT.md)：后端/前端 HTTP 接口合同。
- [docs/FRONTEND_INTEGRATION.md](docs/FRONTEND_INTEGRATION.md)：前端工作流、坐标换算、任务轮询和接入注意事项。
- [docs/AI_CONTEXT.md](docs/AI_CONTEXT.md)：给 AI coding agent 和维护者使用的项目速览。

## 仓库结构

```text
app/
  api_server/       FastAPI 服务、任务队列、项目文件工具
  frontend/         Vite + React + TypeScript 前端
  scripts/
    run_api.sh      生产服务启动入口
    smoke/          非生产冒烟测试和构建检查

sam3/               SAM3.1 上游代码和服务封装
sam2/               SAM2.1 点选服务封装和 checkpoint 目录
MatAnyone2/         MatAnyone2 上游代码和 matting 封装
docs/               项目权威文档
projects/           运行时数据目录，部署时生成，不进 git
```

## 生产默认约定

默认部署根目录是 `~/matting`，可通过 `MATTING_ROOT` 覆盖。

必需 checkpoint：

```text
~/matting/sam3/models/sam3.1/sam3.1_multiplex.pt
~/matting/MatAnyone2/pretrained_models/matanyone2.pth
~/matting/sam2/checkpoints/sam2.1_hiera_base_plus.pt
```

其中 SAM3.1 checkpoint 下载走 ModelScope：`https://modelscope.cn/models/facebook/sam3.1`，具体命令见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

运行环境必须隔离：

```text
sam3         Python 3.12，负责 SAM3.1 首帧 mask
matanyone2   Python 3.10，负责 MatAnyone2 视频抠像和 SAM2.1 点选服务
matting_api  Python 3.11，负责 FastAPI 和项目状态管理
```

启动服务：

```bash
conda activate matting_api
bash ~/matting/app/scripts/run_api.sh
```

打开：

```text
http://127.0.0.1:8000/app
http://127.0.0.1:8000/docs
```

## 开发注意事项

API server 不允许直接 import SAM3.1 或 MatAnyone2 模型包。模型调用必须通过 `conda run` 子进程执行，以保持依赖隔离。生产脚本放在 `app/scripts/`；测试和冒烟脚本统一放在 `app/scripts/smoke/`。
