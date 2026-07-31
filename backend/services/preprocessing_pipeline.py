"""Factory for the single shared token preprocessing pipeline."""

from __future__ import annotations

from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from services.feature_extractor import (
    CATEGORICAL_FEATURE_COLUMNS,
    NUMERIC_FEATURE_COLUMNS,
    TEXT_FEATURE_COLUMN,
    StructuralFeatureTransformer,
)


def build_preprocessing_pipeline() -> Pipeline:
    """
    Combine character TF-IDF with numerical and categorical structural data.

    The first step accepts raw tokens. No caller needs to normalize tokens or
    construct feature dictionaries before calling ``fit`` or ``transform``.
    """

    columns = ColumnTransformer(
        transformers=[
            (
                "char_tfidf",
                TfidfVectorizer(
                    analyzer="char",
                    ngram_range=(2, 5),
                    min_df=2,
                    max_features=24000,
                    sublinear_tf=True,
                ),
                TEXT_FEATURE_COLUMN,
            ),
            (
                "numeric",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="constant", fill_value=0)),
                        ("scale", StandardScaler(with_mean=False)),
                    ]
                ),
                NUMERIC_FEATURE_COLUMNS,
            ),
            (
                "categorical",
                Pipeline(
                    steps=[
                        (
                            "imputer",
                            SimpleImputer(strategy="constant", fill_value="NONE"),
                        ),
                        (
                            "one_hot",
                            OneHotEncoder(
                                handle_unknown="ignore",
                                sparse_output=True,
                            ),
                        ),
                    ]
                ),
                CATEGORICAL_FEATURE_COLUMNS,
            ),
        ],
        remainder="drop",
        sparse_threshold=0.1,
        verbose_feature_names_out=True,
    )

    return Pipeline(
        steps=[
            ("feature_extraction", StructuralFeatureTransformer()),
            ("column_transformer", columns),
        ]
    )


def transformed_feature_names(fitted_pipeline: Pipeline) -> list[str]:
    """Return stable transformed names from a fitted preprocessing pipeline."""

    names = fitted_pipeline.named_steps[
        "column_transformer"
    ].get_feature_names_out()
    return [str(name) for name in names]
