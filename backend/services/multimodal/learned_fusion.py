"""Learned candidate fusion MLP with temperature-calibrated confidence."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from config import settings


SCORE_ORDER = (
    "text",
    "geometry",
    "graph",
    "ocr",
    "layout",
    "engineering_rules",
)
_LOCK = threading.RLock()
_RUNTIME: Optional[tuple[Any, Any, Dict[str, Any]]] = None


def _torch():
    from services.multimodal.torch_runtime import load_torch

    return load_torch()


def _create_model(input_dim: int, hidden_dim: int):
    torch = _torch()
    return torch.nn.Sequential(
        torch.nn.Linear(input_dim, hidden_dim),
        torch.nn.ReLU(),
        torch.nn.Dropout(0.1),
        torch.nn.Linear(hidden_dim, max(8, hidden_dim // 2)),
        torch.nn.ReLU(),
        torch.nn.Linear(max(8, hidden_dim // 2), 1),
    )


def _load_runtime() -> Optional[tuple[Any, Any, Dict[str, Any]]]:
    global _RUNTIME
    path = settings.fusion_model_path
    if not path.exists():
        return None
    with _LOCK:
        if _RUNTIME is None:
            torch = _torch()
            checkpoint = torch.load(path, map_location="cpu", weights_only=False)
            model = _create_model(
                int(checkpoint["input_dim"]), int(checkpoint["hidden_dim"])
            )
            model.load_state_dict(checkpoint["state_dict"])
            model.eval()
            _RUNTIME = (torch, model, checkpoint)
    return _RUNTIME


def _candidate_vector(
    fused_vector: List[float],
    modality_scores: Dict[str, float],
) -> List[float]:
    return [
        *(float(value) for value in fused_vector),
        *(float(modality_scores.get(name) or 0.0) for name in SCORE_ORDER),
    ]


def predict_learned_fusion(
    fused_vector: List[float],
    candidates: List[Dict[str, Any]],
    modality_slices: Dict[str, List[int]],
) -> Optional[Dict[str, Any]]:
    """Rank exact-section candidates with the trained MLP."""

    try:
        runtime = _load_runtime()
    except (ImportError, RuntimeError, OSError, KeyError):
        # Attention fusion stays in charge when torch or the checkpoint
        # cannot be loaded.
        return None
    if runtime is None or not candidates:
        return None
    torch, model, checkpoint = runtime
    matrix = [
        _candidate_vector(fused_vector, candidate["modality_scores"])
        for candidate in candidates
    ]
    if len(matrix[0]) != int(checkpoint["input_dim"]):
        return None
    with torch.inference_mode():
        logits = model(torch.tensor(matrix, dtype=torch.float32)).squeeze(-1)
        temperature = max(float(checkpoint.get("temperature") or 1.0), 0.05)
        probabilities = torch.softmax(logits / temperature, dim=0)
    ranked_indices = sorted(
        range(len(candidates)),
        key=lambda index: (-float(probabilities[index]), candidates[index]["shape"]),
    )
    ranked = []
    for index in ranked_indices[:5]:
        item = dict(candidates[index])
        item["score"] = round(float(probabilities[index]), 6)
        item["fusion_logit"] = round(float(logits[index]), 6)
        ranked.append(item)

    selected = ranked_indices[0]
    base_logit = float(logits[selected])
    ablations: Dict[str, float] = {}
    for modality, bounds in modality_slices.items():
        modified = list(matrix[selected])
        for position in range(bounds[0], bounds[1]):
            modified[position] = 0.0
        with torch.inference_mode():
            ablated = float(
                model(torch.tensor([modified], dtype=torch.float32)).item()
            )
        ablations[modality] = max(0.0, base_logit - ablated)
    total = sum(ablations.values())
    contributions = (
        {name: value / total for name, value in ablations.items()}
        if total > 0
        else {name: 0.0 for name in ablations}
    )
    return {
        "section": candidates[selected]["shape"],
        "confidence": float(probabilities[selected]),
        "candidate_scores": ranked,
        "contributions": contributions,
        "temperature": temperature,
        "calibration": "temperature_scaling",
    }


def train_fusion_model(
    samples: Iterable[Dict[str, Any]],
    *,
    epochs: int = 100,
    hidden_dim: int = 64,
    destination: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Train and calibrate fusion from reviewed candidate-ranking samples."""

    torch = _torch()
    groups = []
    for sample in samples:
        fused = list(sample.get("fused_vector") or [])
        candidates = sample.get("candidates") or []
        selected = str(sample.get("correct_section") or "")
        if not fused or len(candidates) < 2 or not selected:
            continue
        labels = [str(candidate.get("shape") or "") for candidate in candidates]
        if selected not in labels:
            continue
        matrix = [
            _candidate_vector(fused, candidate.get("modality_scores") or {})
            for candidate in candidates
        ]
        groups.append((matrix, labels.index(selected)))
    if not groups:
        raise ValueError("No reviewed multimodal candidate samples were provided")
    input_dim = len(groups[0][0][0])
    if any(len(row) != input_dim for matrix, _ in groups for row in matrix):
        raise ValueError("Fusion samples use inconsistent embedding dimensions")
    split = max(1, int(len(groups) * 0.8))
    training = groups[:split]
    calibration = groups[split:] or groups[-min(20, len(groups)) :]
    model = _create_model(input_dim, hidden_dim)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    for _ in range(max(1, epochs)):
        model.train()
        for matrix, target in training:
            logits = model(torch.tensor(matrix, dtype=torch.float32)).view(1, -1)
            loss = torch.nn.functional.cross_entropy(
                logits, torch.tensor([target], dtype=torch.long)
            )
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

    model.eval()
    log_temperature = torch.nn.Parameter(torch.zeros(1))
    calibrator = torch.optim.LBFGS([log_temperature], lr=0.05, max_iter=60)

    def closure():
        calibrator.zero_grad()
        losses = []
        for matrix, target in calibration:
            with torch.no_grad():
                logits = model(torch.tensor(matrix, dtype=torch.float32)).view(1, -1)
            losses.append(
                torch.nn.functional.cross_entropy(
                    logits / log_temperature.exp().clamp_min(0.05),
                    torch.tensor([target], dtype=torch.long),
                )
            )
        loss = torch.stack(losses).mean()
        loss.backward()
        return loss

    calibrator.step(closure)
    temperature = float(log_temperature.exp().clamp(0.05, 20.0).item())
    path = Path(destination or settings.fusion_model_path)
    torch.save(
        {
            "schema_version": "1.0",
            "model": "candidate_fusion_mlp",
            "input_dim": input_dim,
            "hidden_dim": hidden_dim,
            "temperature": temperature,
            "state_dict": model.state_dict(),
            "score_order": SCORE_ORDER,
        },
        path,
    )
    global _RUNTIME
    _RUNTIME = None
    return {
        "path": str(path),
        "samples": len(groups),
        "temperature": temperature,
    }
