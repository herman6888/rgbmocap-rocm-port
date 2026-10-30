"""ROCm patch template, lazily applied via meta_path hook.

Eagerly importing torch here caches the base venv's numpy in sys.modules at
interpreter startup, which breaks venvs/overlays whose pinned numpy differs.
Rule: import NOTHING at startup; apply patches the first time torch is really
imported. Drop this file into <venv>/Lib/site-packages/sitecustomize.py
(or <venv>/lib/pythonX.Y/site-packages/ on POSIX).

On HIP it: (1) forces SDPA to the math backend (flash/mem-efficient raise
hipErrorInvalidImage on gfx1201), (2) replaces torchvision.ops.nms with a
pure-torch version (aten nms kernel likewise invalid).
"""
import importlib.abc
import importlib.util
import os
import sys


def nms(boxes, scores, iou_threshold):
    """Pure-torch NMS (boxes (N,4) float, scores (N,) float)."""
    import torch
    b = boxes.float().cpu()
    s = scores.float().cpu()
    x1, y1, x2, y2 = b.unbind(-1)
    area = (x2 - x1).clamp(min=0) * (y2 - y1).clamp(min=0)
    order = s.argsort(descending=True)
    x1, y1, x2, y2, area = x1[order], y1[order], x2[order], y2[order], area[order]
    n = order.numel()
    keep_idx = []
    suppressed = torch.zeros(n, dtype=torch.bool)
    for i in range(n):
        if bool(suppressed[i]):
            continue
        keep_idx.append(i)
        xx1 = torch.max(x1[i], x1); yy1 = torch.max(y1[i], y1)
        xx2 = torch.min(x2[i], x2); yy2 = torch.min(y2[i], y2)
        inter = (xx2 - xx1).clamp(min=0) * (yy2 - yy1).clamp(min=0)
        iou = inter / (area[i] + area - inter + 1e-9)
        suppressed |= iou > iou_threshold
    k = torch.tensor(keep_idx, dtype=order.dtype)
    return k if boxes.is_cuda else k.to(boxes.device)


def _apply():
    torch = sys.modules['torch']
    if 'torchvision' not in sys.modules and not (
        getattr(torch.version, 'hip', None) or os.environ.get('RGB_MOCAP_ROCM_NMS') == '1'):
        return
    hip = getattr(torch.version, 'hip', None)
    if hip:
        try:
            torch.backends.cuda.enable_flash_sdp(False)
            torch.backends.cuda.enable_mem_efficient_sdp(False)
            torch.backends.cuda.enable_math_sdp(True)
        except Exception:
            pass
    if hip or os.environ.get('RGB_MOCAP_ROCM_NMS') == '1':
        import torchvision
        torchvision.ops.nms = nms


class _Hook(importlib.abc.MetaPathFinder):
    _busy = False

    def find_spec(self, fullname, path=None, target=None):
        if fullname != 'torch' or _Hook._busy:
            return None
        _Hook._busy = True
        try:
            spec = importlib.util.find_spec('torch')
        finally:
            _Hook._busy = False
        if spec is None or spec.loader is None:
            return None
        loader = spec.loader
        orig = getattr(loader, 'exec_module', None)
        if orig is None:
            return spec

        def exec_module(module):
            orig(module)
            try:
                _apply()
            except Exception:
                pass
        try:
            loader.exec_module = exec_module
        except (AttributeError, TypeError):
            return spec
        return spec


if not sys.platform.startswith('java'):
    sys.meta_path.insert(0, _Hook())
    if 'torch' in sys.modules:
        try:
            _apply()
        except Exception:
            pass
