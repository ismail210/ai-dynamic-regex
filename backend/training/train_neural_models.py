"""Manual training entry point for geometry, graph, and fusion models.

Run from the backend directory:

  ./venv/bin/python training/train_neural_models.py build
  ./venv/bin/python training/train_neural_models.py train-geometry
  ./venv/bin/python training/train_neural_models.py train-graph
  ./venv/bin/python training/train_neural_models.py train-fusion
  ./venv/bin/python training/train_neural_models.py train-all
  ./venv/bin/python training/train_neural_models.py status
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.training_pipeline.neural_dataset import (  # noqa: E402
    build_neural_training_samples,
    load_persisted_neural_samples,
    train_neural_models,
)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def cmd_build(_: argparse.Namespace) -> dict:
    result = build_neural_training_samples(persist=True)
    return {
        "geometry": len(result.get("geometry") or []),
        "graph": len(result.get("graph") or []),
        "fusion": len(result.get("fusion") or []),
        "manifest": result.get("manifest"),
    }


def cmd_status(_: argparse.Namespace) -> dict:
    from config import settings

    samples = load_persisted_neural_samples()
    return {
        "samples": {
            "geometry": len(samples["geometry"]),
            "graph_graphs": len(samples["graph"]),
            "graph_nodes": sum(
                len(item.get("node_labels") or {}) for item in samples["graph"]
            ),
            "fusion": len(samples["fusion"]),
        },
        "models": {
            "geometry_embedding_index": {
                "path": str(settings.geometry_embedding_index_path),
                "exists": settings.geometry_embedding_index_path.exists(),
            },
            "graphsage_model": {
                "path": str(settings.graphsage_model_path),
                "exists": settings.graphsage_model_path.exists(),
            },
            "multimodal_fusion": {
                "path": str(settings.fusion_model_path),
                "exists": settings.fusion_model_path.exists(),
            },
        },
    }


def cmd_train(args: argparse.Namespace) -> dict:
    modalities = None
    if args.command == "train-geometry":
        modalities = ("geometry",)
    elif args.command == "train-graph":
        modalities = ("graph",)
    elif args.command == "train-fusion":
        modalities = ("fusion",)
    # train-all skips models that already exist unless --force is set.
    # Single-modality commands always train that modality.
    skip_existing = args.command == "train-all" and not bool(args.force)
    return train_neural_models(
        rebuild_dataset=bool(args.rebuild),
        modalities=modalities,
        min_samples=args.min_samples,
        skip_existing=skip_existing,
    )


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    parser = argparse.ArgumentParser(
        description="Build neural datasets and train geometry/graph/fusion models"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("build", help="Generate geometry/graph/fusion datasets")
    sub.add_parser("status", help="Show dataset counts and model file presence")

    for name in ("train-geometry", "train-graph", "train-fusion", "train-all"):
        train_parser = sub.add_parser(name, help=f"Run {name}")
        train_parser.add_argument(
            "--rebuild",
            action="store_true",
            help="Rebuild datasets from PDF/Excel pairs before training",
        )
        train_parser.add_argument(
            "--min-samples",
            type=int,
            default=None,
            help="Override the default sample threshold (default from config)",
        )
        train_parser.add_argument(
            "--force",
            action="store_true",
            help="Retrain even when the model file already exists",
        )

    args = parser.parse_args(argv)
    if args.command == "build":
        payload = cmd_build(args)
    elif args.command == "status":
        payload = cmd_status(args)
    else:
        payload = cmd_train(args)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
