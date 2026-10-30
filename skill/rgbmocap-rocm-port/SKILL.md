---
name: rgbmocap-rocm-port
description: "Use when running RGBMocap on the AMD 9070XT via ROCm."
version: 1.0.0
author: 蛋散 (Hermes)
license: MIT
metadata:
  hermes:
    tags: [rocm, amd, mocap, windows, gpu]
    related_skills: [ab-download-manager, comfyui-rocm-windows]
---

# RGBMocap ROCm Port (toyxyz_RGBMocap on RX 9070XT)

## When to Use
Any work on toyxyz_RGBMocap on this AMD box: launching worker stages, fixing runtime_registry/activate() errors, acquiring or verifying weights, exporting FBX, or re-applying the port after `update.cmd`.

Install at `G:\research\toyxyz_RGBMocap`. Upstream pins torch to cu128 (NVIDIA-only app); the port re-pins every profile to `2.14.0+rocm10.1.0` (wheel sources: skill comfyui-rocm-windows). Known-good state: ALL THREE routes (GVHMR/ExMR/FlowHMR) produce verified FBX on the 9070XT. The port is published at `https://github.com/herman6888/rgbmocap-rocm-port` (patches/ + results/ + README) — after `update.cmd`, re-apply from that repo (generic methodology: skill port-nvidia-app-to-rocm).

## Runtime layout and the dual validation gate
- `mocap/runtime_registry.py` PROFILES define all envs: `shared` (folder `runtime`), `gui`/`flow`/`hand`/`htd` (base=shared, folders `runtime_gui`/`runtime_flow`/...), `exmr` (standalone venv, py3.12.10). Overlay folders are flat package dirs (numpy/scipy/timm dist-infos sit at the top level).
- Gate 1: the launcher sha256-checks `runtime_registry.py` against `.setup/git-runtime-state.json`. **Any edit to PROFILES must update that JSON's hash in the same step** (upstream backup kept as `.bak-cu128`), else every launch fails with a registry mismatch.
- Gate 2: `activate()` validates each pinned package's exact version AND that `module.origin` resolves under the expected dir (the overlay folder when the overlay owns the package, else the base venv's `Lib/site-packages`).
- `profile_for(stage)` routes workers: `exmr*`→exmr, `flow*`→flow, `pva`/`refine`→htd, `rig`/`mesh`/`export` read `project.json`'s `pipeline.model`, everything else→shared. Run as: `<base venv>/python.exe -I -X utf8 -B worker_boot.py <stage> --project <dir>`.

## sitecustomize must be lazy (this bug cost two debug sessions)
A `sitecustomize.py` that eagerly imports torch caches the base venv's numpy into `sys.modules` at interpreter startup; every overlay profile pinning a different numpy then fails activate() with `Unexpected numpy import path` — the error names numpy, but the bug is in sitecustomize, not the overlay.
Rule: sitecustomize imports NOTHING at startup. Install a `sys.meta_path` finder that wraps the target module's `loader.exec_module` and applies patches on the module's first real import. Full template (copy + adapt): `templates/sitecustomize_lazy.py`.

## Required ROCm patches (applied by the hook when torch.version.hip)
- **SDPA backends:** flash and mem-efficient raise `hipErrorInvalidImage` on gfx1201 → `torch.backends.cuda.enable_flash_sdp(False); enable_mem_efficient_sdp(False); enable_math_sdp(True)`.
- **`torchvision.ops.nms`:** aten kernel likewise invalid → replace with the pure-torch implementation in the template.
- **torch `.kpack`:** the ROCm torch wheel splits into base wheel + device kernel pack. A venv with only the base needs a junction to a full torch's `.kpack` (e.g. from `runtime_exmr`), else matmul raises `hipErrorInvalidKernelFile`.
- `nvdiffrast` is NOT required for headless runs (the app ships a pure-Python pytorch3d shim; nvdiffrast only backs the on-screen renderer).

## Weights inventory
- `mocap/models.py` is the single source of truth: each `Model(...)` gives the exact relative path + expected sha256; the path must match exactly (e.g. smplh lives at `body_models/smplh/neutral/model.npz`, not `body_models/smplh/model.npz`).
- Mark verified files with a sidecar `{file}.receipt.json` = `{"stat": [size, mtime_ns], "sha256": "..."}`; then `models.missing(stage, tool=...)` reports the stage READY. Copy the schema from an existing receipt before writing new ones.
- Acquisition order (user rule): ModelScope mirror first, then HF direct, then ABDM — details in skill ab-download-manager.

## Stage-run notes
- Flow route order: `flow_camera → flow_features → flowhmr → flow_export`; `rig` must run before `save_fbx` (rig writes `{kind}_mixamo.json`; without it `selected_export()` returns None → "Selected target motion changed").
- Flow projects are nested: `<name>_project/project.json` (workspace v2 root, MUST contain `pipeline.model='flowhmr'` — without it worker.py routes flow stages into the gvhmr branch and raises `KeyError: 'flow_camera'`) + `<name>_project/flowhmr/` (the actual project dir passed as `--project`, holds its own project.json with flow_options). Mirror any option change (e.g. camera_interval) in BOTH jsons.
- flow_features needs `tracking.npz` from the STANDARD pipeline: run `people → person → track` first (needs yolo weight `yolo/yolov8x.pt`; upstream's expected sha c4d5a3f0… matches an ultralytics v8.3.0 build, the real v8.3.0 asset hashes ad8f7f83… — trust the actual GitHub asset). Verified End-to-end on 9070XT: FlowHMR FBX produced 2026-10-30 (`sample_mocap_flow.fbx` in `G:\research\toyxyz_RGBMocap\projects\flow_input_0532c6df758b6d_project\flowhmr`).
- 16GB-VRAM VGGT strategy: non-static flow_camera at interval=1 needs ~12.8GiB VRAM for 120 frames and OOMs under the app's (free-3GiB) fraction cap; interval=2 makes VGGT switch to a higher-res token budget (78GiB request). Use static camera (`flow_options.camera_interval=-1`, needs only 5GiB RAM, skips VGGT) for fixed-camera footage.
- `save_fbx` `--output` is an export-request JSON `[{project, kind, source, target}]`, not an output path; build `source` with `mocap.motion_tools.selected_export(project, kind)` (needs a Path, not str).
- Hard-coded RAM gates in `flow_backend.py`: non-static flow_camera needs 30 GiB available RAM (static-camera project — `camera_interval=-1` set via `RGB_MOCAP_FLOW_INTERVAL` at prepare — needs only 9 and skips VGGT), flow_features 19, flowhmr 16+, flow_export 7. Check `psutil.virtual_memory().available` against the table before launching; freeing RAM may mean closing the user's running apps — always ask before closing user apps, and never kill a system-service process without approval (needs UAC).
