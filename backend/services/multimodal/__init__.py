"""Modular multimodal AI services for structural steel extraction."""

__all__ = ["run_multimodal_pipeline"]


def __getattr__(name: str):
    if name == "run_multimodal_pipeline":
        from services.multimodal.pipeline import run_multimodal_pipeline

        return run_multimodal_pipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
