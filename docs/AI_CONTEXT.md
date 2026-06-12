# AI 项目上下文

这是给 AI coding agent 和维护者使用的压缩项目地图。

## 项目做什么

把上传视频转换成绿幕视频或替换背景视频：

```text
video -> first frame -> retained object masks -> MatAnyone2 alpha -> green/replaced video
```

## 文档源头

权威文档：

```text
docs/ARCHITECTURE.md
docs/DEPLOYMENT.md
docs/API_CONTRACT.md
docs/FRONTEND_INTEGRATION.md
docs/AI_CONTEXT.md
```

不要恢复旧的 `app/docs` 内容。该目录已被有意退役，避免两套文档并存。

## 运行根目录

默认：

```text
MATTING_ROOT=~/matting
```

关键运行路径：

```text
~/matting/projects/{project_id}
~/matting/sam3/models/sam3.1/sam3.1_multiplex.pt
~/matting/MatAnyone2/pretrained_models/matanyone2.pth
~/matting/sam2/checkpoints/sam2.1_hiera_base_plus.pt
```

SAM3.1 checkpoint 下载走 ModelScope，不走 Hugging Face 授权。模型地址是 `https://modelscope.cn/models/facebook/sam3.1`，model id 是 `facebook/sam3.1`。

## 核心文件

后端：

```text
app/api_server/main.py
app/api_server/jobs.py
app/api_server/runner.py
app/api_server/project_files.py
app/api_server/mask_registry.py
app/api_server/config.py
app/api_server/schemas.py
```

前端：

```text
app/frontend/src/App.tsx
app/frontend/src/api.ts
app/frontend/src/types.ts
app/frontend/src/styles.css
```

模型 wrapper：

```text
sam3/services/mask_service_cli.py
sam3/services/mask_service/project_store.py
sam3/services/mask_service/sam3_mask_service.py
sam3/tools/mask_ops.py
MatAnyone2/services/matting_project_cli.py
MatAnyone2/services/matting_service/compose_bg.py
sam2/services/sam2_service/sam2_point_server.py
sam2/services/sam2_service/sam2_point_cli.py
```

脚本：

```text
app/scripts/run_api.sh
app/scripts/sync_services.sh
app/scripts/smoke/
```

## 不能破坏的约束

- 不合并模型环境。
- 不在 `matting_api` 里 import 模型包。
- `state.json` 不保存服务器绝对路径。
- 不把 smoke 脚本移回生产脚本目录。
- 不把 `targets` 模式作为主前端流程暴露。
- 不删除首帧 FFmpeg sRGB 参数，除非有等价的颜色一致性方案。

## 常见修改区域

API 行为：

```text
app/api_server/main.py
app/api_server/schemas.py
docs/API_CONTRACT.md
```

项目文件或 URL 行为：

```text
app/api_server/project_files.py
docs/ARCHITECTURE.md
```

点选 mask 行为：

```text
app/api_server/main.py
app/api_server/mask_registry.py
MatAnyone2/services/sam2_service/
sam2/services/sam2_service/
sam3/services/mask_service/sam3_mask_service.py
```

前端工作流：

```text
app/frontend/src/App.tsx
app/frontend/src/api.ts
app/frontend/src/types.ts
docs/FRONTEND_INTEGRATION.md
docs/API_CONTRACT.md
```

部署：

```text
app/scripts/run_api.sh
app/scripts/sync_services.sh
docs/DEPLOYMENT.md
```

## 快速验证

不跑模型的前端构建：

```bash
cd ~/matting/app/frontend
npm install
npm run build
```

部署后 API/service 冒烟：

```bash
bash ~/matting/app/scripts/smoke/smoke_test_wsl_api_three_stage.sh
```

直接模型冒烟：

```bash
bash ~/matting/app/scripts/smoke/smoke_test_wsl_cli_three_stage.sh
```
