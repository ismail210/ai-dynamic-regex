# Frontend Documentation

The frontend is React 18, Vite, Material UI, TanStack Table, Axios, and
React Router.

## Route surfaces

- Dashboard — operational summary.
- Upload — validates and stores the PDF only.
- Extract — explicit OCR, layout, table, dimension, callout, and structural
  object extraction.
- Analyze — explicit geometry, graph, fusion, correction, and validation.
- Results — exact-section predictions and Prediction Details.
- Validation — multimodal issues, Excel metrics, and per-component evidence.
- Corrections — uncertain/conflicting predictions and engineer action.
- Takeoff — preview and Excel generation from completed predictions.
- Dataset — source and version information.
- Training — retraining and model status.
- Analytics, Model, History, Settings — operational support.

## Contract handling

`src/lib/predictionContract.js` is the sole compatibility boundary for reading
family, section, confidence, and explanations. Components should not recreate
fallback chains.

`src/components/PredictionExplainability.jsx` is the shared renderer used by:

- Review Queue details;
- Validation component details;
- Prediction Details.

It renders prediction, confidence, ranked candidates, selection rationale,
rejection rationale, and text/OCR/geometry/graph/engineering evidence.

## API boundary

All HTTP calls belong in `src/api/client.js`. Pages and components import
client functions rather than creating Axios requests. The production Nginx
configuration proxies `/api/` and `/upload/` to FastAPI.

## Build

```bash
npm ci
npm run build
```

The output is `frontend/dist/`. Production serves it through Nginx with SPA
fallback, upload size limits, proxy timeouts, and basic security headers.
