# 前端工程规范

本文档是前端后续小修小补的默认约束。当前前端服务于 WSL 部署的 `~/matting`，由 FastAPI 挂载构建产物。

## 技术栈

- Vite + React + TypeScript。
- 图标使用 `lucide-react`。
- 不引入 UI 组件库；优先用小型本地组件保持接入成本低。
- 构建产物输出到 `app/frontend/dist`，FastAPI 优先挂载该目录到 `/app/`。

## 目录结构

```text
app/frontend/
  package.json
  vite.config.ts
  tsconfig.json
  index.html
  src/
    main.tsx
    App.tsx
    api.ts
    types.ts
    styles.css
```

约定：

- `api.ts` 只负责 HTTP 请求、上传进度和文件 URL 处理。
- `types.ts` 保存 API 响应和工作流状态类型。
- `App.tsx` 承载当前轻量状态机；后续组件超过单文件可拆到 `src/components/`。
- `styles.css` 使用全局类名，避免内联大段样式。

## 工作流状态

前端只展示当前阶段的主操作：

```text
upload -> mask -> matting -> review -> background -> done
```

- `upload`：选择原视频即自动上传，后端截取首帧，不再提供额外“上传并截帧”按钮。
- `mask`：添加保留对象；默认使用英文文字 prompt 或画面点选，所有对象统一进入保留列表。
- `matting`：自动执行 MatAnyone2，展示任务进度。
- `review`：展示绿幕视频；用户可返回补对象，或明确进入背景替换。
- `background`：选择替换背景图即自动上传并合成最终视频。
- `done`：展示最终视频和文件入口。

SAM3.1 本地仓库已确认存在 point prompt 支撑：`sam3/model/data_misc.py` 的 `FindStage` 包含 `input_points`，prompt 对象支持 `append_points`。本工程在 `services/mask_service/sam3_mask_service.py` 内置 point fallback；如果当前 WSL 的 `Sam3Processor` 没有 `add_point_prompt`，service 会直接调用底层 point prompt 能力。

当前 SAM3.1 点选质量和速度不适合最终点击交互体验。后续推荐在 WSL 增加常驻 SAM2.1 image predictor 服务：上传视频截首帧后缓存首帧 embedding，多次点击只跑 prompt decoder，生成的 mask 继续写入同一套 `retained_masks -> final_mask -> MatAnyone2` 合同。

不要把独立 `targets` 模式暴露给用户，除非产品路线重新确认。

## UI 规范

- 每阶段只保留当前必要操作；视频和背景文件选择后自动进入对应后端任务。
- 可自动执行的动作不增加额外确认按钮，但必须展示进度和失败信息。
- 高级参数默认折叠，并使用自然语言命名。
- 已完成阶段可点击回看，未完成阶段必须显示锁定/不可用状态。
- 主舞台只展示当前最重要的媒体：首帧、绿幕或最终视频。
- 不使用营销落地页式 hero；这是一个可嵌入大项目的工具界面。
- 控件必须在移动宽度下换行，不能靠视口字体缩放解决溢出。

## API 接入约定

- 创建项目：`POST /api/projects`，只要求 `video`。
- 抠像主路径：`/masks/text`、`/masks/point`。
- 兼容路径：`/subject/*`、`/foreground/*` 暂时保留给旧客户端。
- 撤销抠像：`POST /api/projects/{project_id}/mask/undo`。
- 生成绿幕：`POST /api/projects/{project_id}/matting`。
- 上传背景并合成：`POST /api/projects/{project_id}/background`。
- 后台任务统一轮询：`GET /api/jobs/{job_id}`。

## WSL 测试

```bash
cd ~/matting
bash app/scripts/sync_services.sh
bash app/scripts/smoke_test_wsl_frontend_build.sh
```

启动 API 后：

```bash
bash app/scripts/smoke_test_wsl_api_three_stage.sh
```

可选 CLI 重模型验证：

```bash
bash app/scripts/smoke_test_wsl_cli_three_stage.sh
```
