import { useState } from "react";
import { Alert, Button, Paper, Stack, Typography } from "@mui/material";
import { CancelOutlined, CheckCircleOutlined, ScienceOutlined } from "@mui/icons-material";
import { getAnnotationOracle } from "../../api/client";

/**
 * Dev/demo-only oracle reveal (Section 20/26 of the repair-trace brief).
 * Only rendered by the caller when this document is a recognized PDF-attack
 * benchmark case (services.semantic_document_service.get_benchmark_context)
 * -- an ordinary customer document never shows this at all (Section 35).
 * The truth is fetched lazily, on click, AFTER the reviewer has already
 * seen/acted on the candidates -- never fetched up front, so it cannot bias
 * the review decision itself.
 */
export default function BenchmarkTruthPanel({ documentId, annotationId }) {
  const [oracle, setOracle] = useState(undefined); // undefined = not fetched, null = no oracle match
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const reveal = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getAnnotationOracle(documentId, annotationId);
      setOracle(result.oracle);
    } catch (err) {
      setError(err.friendlyMessage || "Could not load the benchmark truth.");
    } finally {
      setLoading(false);
    }
  };

  if (oracle === undefined) {
    return (
      <Button
        size="small"
        variant="text"
        startIcon={<ScienceOutlined fontSize="small" />}
        onClick={reveal}
        disabled={loading}
        data-testid="reveal-benchmark-truth"
      >
        {loading ? "Checking…" : "Reveal benchmark truth"}
      </Button>
    );
  }

  if (error) return <Alert severity="warning">{error}</Alert>;
  if (oracle === null) {
    return <Typography variant="caption" color="text.secondary">No benchmark answer key for this annotation.</Typography>;
  }

  const correct = oracle.human_decision_matches_truth;
  return (
    <Paper variant="outlined" sx={{ p: 1.25, borderColor: correct ? "success.main" : "error.main" }} data-testid="benchmark-truth-result">
      <Stack direction="row" spacing={1} alignItems="center">
        <Typography variant="overline" sx={{ fontWeight: 700 }}>Benchmark truth</Typography>
        <Typography sx={{ fontFamily: "monospace", fontWeight: 700 }}>{oracle.clean_text}</Typography>
      </Stack>
      {oracle.kind === "mutation" && (
        <Typography variant="caption" color="text.secondary" display="block">
          Attacked as {oracle.corrupted_text} ({(oracle.corruption_types || []).join(", ")})
        </Typography>
      )}
      <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.5 }}>
        {correct ? (
          <CheckCircleOutlined fontSize="small" color="success" />
        ) : (
          <CancelOutlined fontSize="small" color="error" />
        )}
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {correct ? "Correct repair" : "Incorrect repair"}
        </Typography>
      </Stack>
    </Paper>
  );
}
