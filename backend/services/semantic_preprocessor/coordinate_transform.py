"""PDF-page <-> Rhino-model coordinate calibration (Section 13-14).

PDF and Rhino coordinates are never assumed interchangeable. A transform
must be FIT from real correspondences and its residual error measured
before any code is allowed to compare a PDF anchor against Rhino geometry.
A transform that fails calibration comes back with ``valid=False`` -- the
caller's job is to refuse to associate across frames when that's the case,
never to paper over it with a larger distance threshold.

Model: 2D similarity transform (uniform scale + rotation + translation),
with an explicit optional Y-flip applied before the fit (PDF's Y axis points
down from the top-left in this codebase's convention; Rhino's typically
points up). This is deliberately not a general affine (independent x/y
scale + shear) -- start with the simpler, more diagnosable model and only
add degrees of freedom if residuals prove it's needed (Research-to-code
decision, see docs/upstream_semantic_preprocessor.md).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple

from services.semantic_preprocessor.models import CoordinateTransform

_MAX_ACCEPTABLE_RESIDUAL_P95 = 5.0  # PDF points; tune once real correspondences exist


@dataclass
class PointCorrespondence:
    source: Tuple[float, float]
    target: Tuple[float, float]


def fit_similarity_transform(
    correspondences: List[PointCorrespondence],
    *,
    transform_id: str,
    source_frame: str,
    target_frame: str,
    flip_y: bool = False,
) -> CoordinateTransform:
    if len(correspondences) < 3:
        return CoordinateTransform(
            id=transform_id,
            source_frame=source_frame,
            target_frame=target_frame,
            scale_x=1.0,
            scale_y=1.0,
            rotation_deg=0.0,
            translation=[0.0, 0.0],
            flip_y=flip_y,
            sample_count=len(correspondences),
            valid=False,
            invalid_reason="fewer_than_3_correspondences",
        )

    src = [(x, -y if flip_y else y) for (x, y) in (c.source for c in correspondences)]
    tgt = [c.target for c in correspondences]

    n = len(src)
    src_cx = sum(p[0] for p in src) / n
    src_cy = sum(p[1] for p in src) / n
    tgt_cx = sum(p[0] for p in tgt) / n
    tgt_cy = sum(p[1] for p in tgt) / n

    src_centered = [(x - src_cx, y - src_cy) for x, y in src]
    tgt_centered = [(x - tgt_cx, y - tgt_cy) for x, y in tgt]

    # Umeyama-style closed-form similarity fit (rotation + uniform scale).
    sxx = sum(sx * tx for (sx, _), (tx, _) in zip(src_centered, tgt_centered))
    sxy = sum(sx * ty for (sx, _), (_, ty) in zip(src_centered, tgt_centered))
    syx = sum(sy * tx for (_, sy), (tx, _) in zip(src_centered, tgt_centered))
    syy = sum(sy * ty for (_, sy), (_, ty) in zip(src_centered, tgt_centered))

    theta = math.atan2(sxy - syx, sxx + syy)
    cos_t, sin_t = math.cos(theta), math.sin(theta)

    src_norm_sq = sum(x * x + y * y for x, y in src_centered)
    if src_norm_sq <= 1e-9:
        return CoordinateTransform(
            id=transform_id, source_frame=source_frame, target_frame=target_frame,
            scale_x=1.0, scale_y=1.0, rotation_deg=0.0, translation=[0.0, 0.0],
            flip_y=flip_y, sample_count=n, valid=False,
            invalid_reason="degenerate_source_points",
        )
    numerator = sum(
        (sx * cos_t - sy * sin_t) * tx + (sx * sin_t + sy * cos_t) * ty
        for (sx, sy), (tx, ty) in zip(src_centered, tgt_centered)
    )
    scale = numerator / src_norm_sq

    tx_translation = tgt_cx - scale * (src_cx * cos_t - src_cy * sin_t)
    ty_translation = tgt_cy - scale * (src_cx * sin_t + src_cy * cos_t)

    def apply(pt: Tuple[float, float]) -> Tuple[float, float]:
        x, y = pt
        return (
            scale * (x * cos_t - y * sin_t) + tx_translation,
            scale * (x * sin_t + y * cos_t) + ty_translation,
        )

    residuals = []
    for (sx, sy), (tx, ty) in zip(src, tgt):
        px, py = apply((sx, sy))
        residuals.append(math.hypot(px - tx, py - ty))

    residuals_sorted = sorted(residuals)
    mean_res = sum(residuals) / n
    median_res = residuals_sorted[n // 2] if n % 2 else (
        residuals_sorted[n // 2 - 1] + residuals_sorted[n // 2]
    ) / 2
    p95_index = min(n - 1, int(math.ceil(0.95 * n)) - 1)
    p95_res = residuals_sorted[p95_index]
    max_res = residuals_sorted[-1]

    valid = p95_res <= _MAX_ACCEPTABLE_RESIDUAL_P95
    return CoordinateTransform(
        id=transform_id,
        source_frame=source_frame,
        target_frame=target_frame,
        scale_x=scale,
        scale_y=scale,
        rotation_deg=math.degrees(theta),
        translation=[tx_translation, ty_translation],
        flip_y=flip_y,
        residual_mean=mean_res,
        residual_median=median_res,
        residual_p95=p95_res,
        residual_max=max_res,
        sample_count=n,
        valid=valid,
        invalid_reason=None if valid else "residual_p95_exceeds_threshold",
    )


def apply_transform(transform: CoordinateTransform, point: Tuple[float, float]) -> Tuple[float, float]:
    if not transform.valid:
        raise ValueError(
            f"Refusing to apply invalid coordinate transform {transform.id!r} "
            f"({transform.invalid_reason})"
        )
    x, y = point
    if transform.flip_y:
        y = -y
    theta = math.radians(transform.rotation_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    tx, ty = transform.translation
    return (
        transform.scale_x * (x * cos_t - y * sin_t) + tx,
        transform.scale_x * (x * sin_t + y * cos_t) + ty,
    )


def invert_transform(transform: CoordinateTransform, point: Tuple[float, float]) -> Tuple[float, float]:
    if not transform.valid:
        raise ValueError(
            f"Refusing to invert invalid coordinate transform {transform.id!r} "
            f"({transform.invalid_reason})"
        )
    x, y = point
    tx, ty = transform.translation
    theta = math.radians(-transform.rotation_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    dx, dy = x - tx, y - ty
    scale = transform.scale_x or 1.0
    sx = (dx * cos_t - dy * sin_t) / scale
    sy = (dx * sin_t + dy * cos_t) / scale
    if transform.flip_y:
        sy = -sy
    return (sx, sy)
