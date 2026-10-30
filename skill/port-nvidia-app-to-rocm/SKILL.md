---
name: port-nvidia-app-to-rocm
description: "Use when porting a CUDA-pinned app to AMD ROCm (Windows)."
version: 1.0.0
author: 蛋散 (Hermes)
license: MIT
metadata:
  hermes:
    tags: [rocm, amd, windows, pytorch, porting]
    related_skills: [rgbmocap-rocm-port, comfyui-rocm-windows, github-auth]
---

# Port an NVIDIA-pinned app to AMD ROCm (Windows)

## When to use
An app (usually Windows-native, uv/venv based) hard-pins `torch X+cuXXX` and refuses to run on an AMD GPU. Goal: make it run on ROCm, keep it updatable, and preserve the work so any agent/machine can reproduce it. Distilled from porting toyxyz_RGBMocap to an RX 9070XT (all 3 inference routes producing verified FBX).

## Reference implementation (pull this before reinventing)
`https://github.com/herman6888/rgbmocap-rocm-port` — worked example with README methodology, the exact patched `sitecustomize.py` + pinned-registry pair, and verified FBX outputs. App-specific details live in skill rgbmocap-rocm-port.

## Procedure
1. **Inventory the pins.** Find every place torch/python versions are declared: `pyproject.toml`, `uv.lock`, and any *in-code* profile tables (e.g. a `PROFILES` dict in a runtime registry). Note the app Python version (ROCm wheels exist for cp310–cp314 win_amd64; a 3.12-only app on a 3.10 wheel set needs the venv python matched to an available wheel).
2. **Source ROCm wheels.** AMD index `https://stable.repo.amd.com/rocm/pytorch/whl-next/` (torch/torchvision/torchaudio for the target cpXXX, win_amd64). On this LAN also reuse the ComfyUI portable ROCm stack (`I:\AI_Work\ROCm_Downloads`, see skill comfyui-rocm-windows / rocm_toolkit.py).
3. **Test in a throwaway venv FIRST.** Create a test venv with the ROCm wheel, run `python -c "import torch; print(torch.cuda.is_available(), (torch.randn(2048,2048,device='cuda')@torch.randn(2048,2048,device='cuda')).sum())"` before touching the app. Matmul failure `hipErrorInvalidKernelFile` = missing `.kpack`: the ROCm torch wheel splits into base wheel + device kernel pack; junction `Lib/site-packages/torch` to a FULL torch install (e.g. from a working venv).
4. **In-place migrate with rollback.** Back up everything you replace (`*.bak-cu128`, old site-packages → `_cu128_backup*`). Never delete outright.
5. **Patch ALL validation gates in one step.** If the app validates its own environment (it will), the pins usually exist in TWO coupled places: a code/manifest file AND a hash/state file (e.g. `.setup/*.json` holding `sha256(registry)`). Edit the registry without updating its recorded hash → every launch fails with a mismatch. Grep for `sha256`/`state`/`manifest` before editing. Also expect `activate()` to verify exact version strings AND that `module.__file__` sits under the expected directory — the version string you write must match the wheel exactly (`2.14.0+rocm10.1.0`, not `2.14.0`).
6. **Apply GPU patches via a LAZY sitecustomize** (template: `templates/sitecustomize.py`). Rules:
   - Sitecustomize imports NOTHING at startup. Eager `import torch` caches the base venv's numpy in `sys.modules` and breaks every overlay venv pinning a different numpy — the error names numpy but the bug is sitecustomize. Use a `sys.meta_path` finder wrapping the target module's `loader.exec_module`, applying patches on first real import.
   - On any `torch.version.hip` (esp. gfx1201): disable flash + mem-efficient SDPA, enable math (`enable_flash_sdp(False)` etc) — flash kernels raise `hipErrorInvalidImage`.
   - Replace `torchvision.ops.nms` with the pure-torch implementation (aten nms kernel also invalid on gfx1201).
7. **Verify all profiles/venvs.** Run the app's own activation path (or import each package from each venv) to prove every environment passes validation before launching real work.
8. **Model weights: all you need are download links.** The app's model manifest lists exact relative paths + sha256 per weight. Canonical URL patterns (any downloader — curl/wget/browser — works):
   - HuggingFace: `https://huggingface.co/<org>/<repo>/resolve/main/<path>` (mirror: `https://hf-mirror.com/<org>/<repo>/resolve/main/<path>`; with huggingface_hub set `HF_HUB_DISABLE_XET=1`)
   - ModelScope: `https://modelscope.cn/api/v1/models/<org>/<repo>/repo?Revision=master&FilePath=<path>` — many facebook/OpenAI-style HF repos are mirrored there anonymously (no token needed)
   - GitHub release assets: `https://github.com/<org>/<repo>/releases/download/<tag>/<file>`
   Tips: prefer ungated mirrors (gated HF repos return 401 without a token); verify sha256 after every download and re-download on mismatch (downloaders corrupt files surprisingly often); the destination path must match the manifest character-for-character (`body_models/smplh/neutral/model.npz` ≠ `body_models/smplh/model.npz`); if the manifest hash and the official upstream asset hash disagree, trust the official asset; record verified files with a `.receipt.json` sidecar `{"stat": [size, mtime_ns], "sha256": "..."}` if the app honors receipts.
9. **Memory gating.** Apps often hard-gate on `psutil.virtual_memory().available` and VRAM fractions. Tactics: set `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` (fragmentation OOM under fraction caps), use the app's static/low-memory modes (e.g. skip expensive multi-frame modules for fixed-camera footage), trim clips, batch halving. Check `psutil` available vs the app's required table BEFORE launching; closing user apps requires asking, killing services needs UAC.
10. **Upstream updates wipe your port.** Installers/updaters rewrite the pinned registry + state → keep the port files in git (see step 11) so re-applying is one copy after every update.
11. **Publish the work.** Repo layout that works (see reference): `README.md` (methodology + results table) + `patches/` (every modified file, upstream `.bak` alongside each) + `results/` (outputs + project-state snapshots). Create via `gh repo create --private --source=. --push`; on a proxy-broken Windows box use `git -c http.proxy= -c https.proxy= push` plus the per-host `!gh auth git-credential` helper (skill github-auth).
