"""Guarded torch import shared by the optional neural modules."""

from __future__ import annotations

import os
import threading
from typing import Any, Optional


_LOCK = threading.RLock()
_TORCH: Optional[Any] = None


def load_torch() -> Any:
    """Import torch with single-threaded, duplicate-OpenMP-safe settings.

    Prediction already runs XGBoost and NumPy inside the same worker. A second
    OpenMP runtime aborts the process instead of raising, so the environment is
    pinned before the first import.
    """

    global _TORCH
    with _LOCK:
        if _TORCH is None:
            os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
            os.environ.setdefault("OMP_NUM_THREADS", "1")
            os.environ.setdefault("MKL_NUM_THREADS", "1")
            try:
                import torch
            except ModuleNotFoundError as exc:
                raise ModuleNotFoundError(
                    "PyTorch is required for geometry/graph/fusion training. "
                    "From the backend directory run: "
                    './venv/bin/pip install "torch==2.2.2" "torchvision==0.17.2" '
                    '"numpy==1.26.4" "scipy==1.13.1"'
                ) from exc

            torch.set_num_threads(1)
            _TORCH = torch
    return _TORCH
