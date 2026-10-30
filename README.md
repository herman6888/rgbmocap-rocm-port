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
```

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
`mocap/models.py` 是唯一真源（相对路径 + 期望 sha256，路径必须逐字符一致，如 `body_models/smplh/neutral/model.npz`）。经验：**ModelScope 优先**（facebook/HF 系大多有镜像，匿名直连），HF 直连次之（gated 仓库 401），ABDM 下载器 hash 损坏率高。全部权重以 `.receipt.json` sidecar 记档。

### 7. 升级注意事项
`update.cmd` 会重写 registry + state → **本仓库的 patches/ 需重新盖回**（这正是把这一对文件版本化的原因）。上游代码本体（含 fbx_writer 原生实现）未被修改。

## 上游与许可
上游 [toyxyz/toyxyz_RGBMocap](https://github.com/toyxyz/toyxyz_RGBMocap)（MIT）。本仓库仅包含移植补丁与产物快照，供该应用在 AMD 显卡上的复现参考。
