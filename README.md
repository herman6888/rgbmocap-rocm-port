# RGBMocap on AMD RX 9070XT — ROCm 移植成果

把 [toyxyz/toyxyz_RGBMocap](https://github.com/toyxyz/toyxyz_RGBMocap)（原生 Windows RGB 动作捕捉应用，官方仅支持 NVIDIA CUDA）移植到 **AMD RX 9070XT (gfx1201) + ROCm 10.1.0** 的全部可复现成果：运行时补丁、验证配置，以及三条推理路线在 AMD 显卡上实跑产出的 FBX 文件。

- 移植目标机：Windows 11 / RX 9070XT（16GB VRAM）/ ROCm 10.1.0（torch `2.14.0+rocm10.1.0`，AMD wheel 渠道见下）
- 移植方式：**原地改装 + 双闸门兼容**（不改上游代码本体，只改 `runtime_registry.py` 的 pin 与 `.setup` 的状态哈希，两处必须同步改，见「双验证闸门」）
- 验证结果：**GVHMR / ExMR / FlowHMR 三大路线全部产出真实 FBX**（`results/` 内附实物）

## 最终验证结果（全部实机产出）

| 路线 | 产物 | 大小 | 验证 |
|---|---|---|---|
| GVHMR (SMPL-X) | `results/gvhmr/sample_mocap.fbx` | 297,516 B | `Kaydara FBX Binary` header ✓ |
| ExMR (SMPL-X, 含手指) | `results/exmr/sample_mocap_exmr.fbx` | 328,172 B | header ✓，52 关节含 30 手指通道 |
| FlowHMR (SMPL-H) | `results/flowhmr/sample_mocap_flow.fbx` | 327,548 B | header ✓，含 rig 资产与 surface |

各目录附对应 `project.json`（项目状态快照，含全部阶段 status 与资源账本）。

## 文件清单

```
patches/
  sitecustomize.py              # ROCm 补丁核心：lazy meta_path 钩子（SDPA 强制 math + 纯 torch nms）
  runtime_registry.py           # 已改装版：六个 profile 全部 pin 到 torch 2.14.0+rocm10.1.0
  runtime_registry.py.bak-cu128 # 上游原版（cu128 pin）备份
  git-runtime-state.json        # .setup 状态（registry_sha256 已同步为改装版哈希）
  git-runtime-state.json.bak-cu128  # 上游原版状态备份
results/
  gvhmr/  exmr/  flowhmr/       # 三条路线的 FBX + project.json
skill/
  port-nvidia-app-to-rocm/      # 通用移植方法论 skill（SKILL.md + templates/sitecustomize.py）
  rgbmocap-rocm-port/           # 本 app 专属操作 skill（SKILL.md + templates/sitecustomize.py）
```

## Agent 如何用本仓库的 Skill

skill 是给 AI agent 读的**过程性知识文件**（`SKILL.md`，[Agent Skills 约定](https://agentskills.io)）。任何 agent 拿到本仓库即可获得完整移植能力：

| Agent 类型 | 调用方式 |
|---|---|
| **Hermes Agent** | 把 `skill/port-nvidia-app-to-rocm/` 整个文件夹拷入 `~/.hermes/skills/`（Windows: `C:\Users\<user>\.hermes\skills\`），skill 自动进索引；对话中说 "load skill port-nvidia-app-to-rocm" 或 agent 遇到 "port CUDA app to ROCm" 类任务时自动加载。app 级细节装 `skill/rgbmocap-rocm-port/`。 |
| **Claude Code / Codex / pi 等** | 把 `skill/port-nvidia-app-to-rocm/SKILL.md` 的 URL 或文件路径贴进提示词，例：*"Read https://github.com/herman6888/rgbmocap-rocm-port/blob/main/skill/port-nvidia-app-to-rocm/SKILL.md and follow it to port <app> to ROCm"*；或挂进各自的技能体系（CLAUDE.md / AGENTS.md 中 `@` 引用该文件）。 |
| **任意 agent 取单文件** | 模板直接取：`skill/port-nvidia-app-to-rocm/templates/sitecustomize.py`（与 `patches/sitecustomize.py` 同源）。 |

**给 agent 的最小指令模板**：
> 把 `<app>` 移植到 AMD ROCm。方法论：`skill/port-nvidia-app-to-rocm/SKILL.md`（11 步流程，含全部已知坑与验证方法）。参考实现：本仓库 `patches/`（照抄的双闸门补丁对）+ `results/`（验证过的产物）。

## Model weights 下载链接（本机全部验证过）

通用规则：app 的 `mocap/models.py` manifest 给出每个权重的**精确相对路径 + sha256**（路径必须逐字符一致）。URL 模式：
- HuggingFace：`https://huggingface.co/<org>/<repo>/resolve/main/<path>`（gated 仓库无 token 返回 401；可用镜像 `https://hf-mirror.com/<org>/<repo>/resolve/main/<path>`）
- ModelScope：`https://modelscope.cn/api/v1/models/<org>/<repo>/repo?Revision=master&FilePath=<path>`（匿名、无需 token、国内快）
- GitHub release：`https://github.com/<org>/<repo>/releases/download/<tag>/<file>`
- Google Drive（manifest 给 drive_id 时）：`https://drive.usercontent.google.com/download?id=<drive_id>&confirm=t`

| 权重 | 实际下载来源 | 验证 |
|---|---|---|
| `yolo/yolov8x.pt` | <https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8x.pt> | 官方 v8.3.0 资产实际 sha `ad8f7f83…`（manifest 记 `c4d5a3f0…`，以官方资产为准） |
| `body_models/smplh/neutral/model.npz` | <https://huggingface.co/lithiumice/models_hub/resolve/main/4_SMPLhub/smplh/neutral/model.npz> | sha `a60a7e29…` 逐字节 = manifest |
| `flowhmr/sam/model.ckpt` | <https://modelscope.cn/api/v1/models/facebook/sam-3d-body-dinov3/repo?Revision=master&FilePath=model.ckpt> | sha `b5a2f9d3…` = manifest |
| `flowhmr/sam/model_config.yaml` | 同上仓库 `FilePath=model_config.yaml` | sha `1012fc3f…` = manifest |
| `flowhmr/sam/assets/mhr_model.pt` | 同上仓库 `FilePath=assets/mhr_model.pt` | sha `352e271a…` = manifest |
| `flowhmr/vggt_omega_1b_512.pt` | <https://modelscope.cn/api/v1/models/facebook/VGGT-Omega/repo?Revision=master&FilePath=vggt_omega_1b_512.pt> | sha `c02da418…` 逐字节 = manifest |
| `hmr2/epoch=10-step=25000.ckpt` | <https://huggingface.co/camenduru/GVHMR/resolve/main/hmr2/epoch%3D10-step%3D25000.ckpt> | sha `2dcf7963…` 逐字节 = manifest |
| `vitpose/vitpose-h-multi-coco.pth` | <https://huggingface.co/camenduru/GVHMR/resolve/main/vitpose/vitpose-h-multi-coco.pth> | sha `50e33f40…` 逐字节 = manifest |
| `gvhmr/gvhmr_siga24_release.ckpt` | <https://huggingface.co/camenduru/GVHMR/resolve/main/gvhmr/gvhmr_siga24_release.ckpt> | sha `4fae7da2…` |
| `exmr/exmr.safetensors` | <https://huggingface.co/twehrbein/ExMR/resolve/main/exmr.safetensors> | sha `8d394731…` |
| `exmr/sapiens2_1b_pose.safetensors` | <https://huggingface.co/facebook/sapiens2-pose-1b/resolve/main/sapiens2_1b_pose.safetensors> | sha `2dab7014…` |

其余权重（pva/footmr/handflow 系/mano/smpl/smplx/reid/flowhmr ckpt）按 manifest 的 `url` + `drive_id` 字段套用上面的 URL 模式即可。所有下载后必须 sha256 校验；`models/**.receipt.json` sidecar 制度见 skill。

## 移植要点（可复现步骤）

### 1. torch 换血
上游六个 profile 全部硬 pin `torch 2.14.0+cu128`（NVIDIA only）。移植用 ROCm wheel `torch-2.14.0+rocm10.1.0-cp310-win_amd64` 替换：
- wheel 来源：`https://stable.repo.amd.com/rocm/pytorch/whl-next/`（本机也复用了 ComfyUI portable 的 ROCm 10.1.0 栈）
- ROCm torch wheel 分 base + device kernel pack：venv 里只有 base 时必须给 `.kpack` 建 junction 指向全量 torch，否则 matmul 报 `hipErrorInvalidKernelFile`

### 2. 双验证闸门必须同步改
- 闸门①：`launch_source.py` 用 sha256 校验 `runtime_registry.py` 是否等于 `.setup/git-runtime-state.json` 记录值 → 改 PROFILES 必须同一步更新该 JSON 的 hash（本仓库两个文件就是配好的一对）
- 闸门②：`activate()` 逐一校验 pin 版本 + 模块 `__file__` 必须落在期望目录 → 版本字符串写错一个字符就 `Incompatible torch in shared`

### 3. sitecustomize 必须 lazy（本次最贵的坑）
任何**启动期 eager import torch** 的 sitecustomize 会把 base venv 的 numpy 钉进 `sys.modules`，所有 overlay profile（numpy pin 不同）随即报 `Unexpected numpy import path`——错误指向 numpy，病根在 sitecustomize。正确姿势：`sys.meta_path` finder 包住 torch 的 `exec_module`，torch 真被 import 时才装补丁（模板见 `patches/sitecustomize.py`）。

### 4. gfx1201 必需的运行时补丁（由钩子在 torch 首次导入时应用）
- **SDPA**：flash / mem-efficient kernel 在 gfx1201 上抛 `hipErrorInvalidImage` → 关掉两者、强制 math backend
- **`torchvision.ops.nms`**：aten kernel 同样 invalid → 换成纯 torch 实现
- `nvdiffrast` 无需安装（headless 用不到，应用自带纯 Python pytorch3d shim）

### 5. FlowHMR 在 16GB 卡上的策略
- 非静态相机 flow_camera 走 VGGT-1B@512，120 帧需 ~12.8GiB VRAM，且 interval=2 反而触发更高分辨率路径（78GiB 请求）→ **固定机位素材用 static camera（`flow_options.camera_interval=-1`），跳过 VGGT，仅需 5GiB RAM**
- flow 项目是嵌套结构：根 `project.json` 必须有 `pipeline.model='flowhmr'`，否则 flow 阶段被路由进 gvhmr 分支报 `KeyError: 'flow_camera'`
- flow_features 依赖标准管线的 `tracking.npz`：需先跑 `people → person → track`（需要 `models/yolo/yolov8x.pt`；上游期望 sha `c4d5a3f0…`，ultralytics v8.3.0 官方资产实际 hash `ad8f7f83…`，以 GitHub 官方资产为准）

### 6. 权重来源
`mocap/models.py` 是唯一真源（相对路径 + 期望 sha256，路径必须逐字符一致，如 `body_models/smplh/neutral/model.npz`）。全部验证过的下载链接见上文「Model weights 下载链接」章节；其余权重按 manifest 的 `url`/`drive_id` 套 URL 模式，任意下载器（curl/wget 等）均可，下载后必须 sha256 校验并以 `.receipt.json` sidecar 记档。

### 7. 升级注意事项
`update.cmd` 会重写 registry + state → **本仓库的 patches/ 需重新盖回**（这正是把这一对文件版本化的原因）。上游代码本体（含 fbx_writer 原生实现）未被修改。

## 上游与许可
上游 [toyxyz/toyxyz_RGBMocap](https://github.com/toyxyz/toyxyz_RGBMocap)（MIT）。本仓库仅包含移植补丁与产物快照，供该应用在 AMD 显卡上的复现参考。
