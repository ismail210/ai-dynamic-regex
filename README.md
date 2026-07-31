# AI Structural Steel Takeoff Platform

AI-first multimodal extraction, prediction, validation, review, continuous
learning, and takeoff generation for structural drawings.

## Core guarantees

- Predictions come from the AI pipeline; the AISC database verifies only.
- Excel uploads are ground truth only and never prediction inputs.
- Every v2 prediction includes confidence, ranked candidates, selection and
  rejection reasons, and text/geometry/graph/engineering evidence.
- Review Queue, Validation, and Prediction Details render the same canonical
  explainability contract.
- Production prediction enters through
  `backend/services/prediction/orchestrator.py`.

## Local development

```bash
cd backend
python -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/uvicorn app:app --reload
```

```bash
cd frontend
# Keep VITE_API_BASE empty so the browser talks to the Vite proxy
# (same-origin). Absolute hosts like http://127.0.0.1:8000 cause
# cross-origin upload failures from http://localhost:5173.
npm ci
npm run dev
```

Backend: `http://localhost:8000` · frontend: `http://localhost:5173` · OpenAPI:
`http://localhost:8000/docs`.

The staged workflow uses same-origin AJAX:
`POST /api/documents` → `POST /api/documents/{id}/extract` →
`POST /api/documents/{id}/analyze`. Upload only validates and stores bytes;
extraction and analysis never start implicitly. Requests are proxied by Vite
to the backend. Never put an absolute API host in a React
component — configure `VITE_API_BASE` (browser) and `VITE_PROXY_TARGET`
(dev proxy only) in `frontend/.env`.

## Production

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
```

Before deployment, set the public CORS origin and ensure
`backend/training/` contains the promoted model artifacts. See
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## Documentation

- [Architecture and diagrams](docs/ARCHITECTURE.md)
- [Folder map](docs/FOLDERS.md)
- [Services](docs/SERVICES.md)
- [Training and continuous learning](docs/TRAINING.md)
- [API](docs/API.md)
- [Frontend](docs/FRONTEND.md)
- [Production deployment](docs/DEPLOYMENT.md)
