# Folder Documentation

```text
ai-dynamic-regex/
├── backend/
│   ├── app.py                 FastAPI composition and health probes
│   ├── config.py              Environment and artifact paths
│   ├── routers/               HTTP transport only
│   ├── services/              Domain and application services
│   │   ├── prediction/        Canonical token prediction contract
│   │   ├── multimodal/        Document fusion, correction, validation
│   │   ├── engineering/       Geometry, graph, rules, corrections
│   │   ├── takeoff/           Excel GT, evaluation, paired datasets, exports
│   │   └── training_pipeline/ Versioned continuous-learning workflow
│   ├── database/              Immutable AISC reference workbook
│   ├── training/              Runtime datasets, models, registries, reports
│   ├── uploads/               Ephemeral uploaded source files
│   └── tests/                 Backend contract and integration tests
├── frontend/
│   ├── src/api/               HTTP client functions
│   ├── src/components/        Reusable UI, including explainability
│   ├── src/context/           Shared application state
│   ├── src/layout/            Navigation and page shell
│   ├── src/lib/               Contract normalization and utilities
│   └── src/pages/             Route-level UI
├── docs/                      Maintained system documentation
├── docker-compose.yml         Production-like two-service deployment
└── .env.example               Deployment configuration template
```

## Data directory policy

- `database/` is reference data and read-only at runtime.
- `training/datasets/` and `training/models/` are version registries.
- `training/pdf/` + `training/excel/` contain paired learning sources.
- `training/engineering_artifacts/` and `uploads/` are operational data and
  should use persistent storage with retention policies in production.
- `frontend/dist/`, virtual environments, caches, and `node_modules/` are build
  outputs, not source.
