import { useRef, useState } from "react";
import {
  Alert,
  Box,
  LinearProgress,
  Stack,
  Typography,
} from "@mui/material";
import { CheckCircle, CloudUpload } from "@mui/icons-material";
import { uploadPdf } from "../api/client";
import { useAnalysis } from "../context/AnalysisContext";
import { TipButton } from "./ui/ActionButtons";

export default function FileUpload() {
  const input = useRef(null);
  const { setData, setDocument, setExtraction, setRestoreNotice } = useAnalysis();
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [dragging, setDragging] = useState(false);

  const submit = async (file) => {
    if (!file) return;
    if (file.type !== "application/pdf") {
      setError("Select a PDF file.");
      return;
    }
    setError("");
    setSuccess(false);
    setLoading(true);
    setProgress(0);
    try {
      const data = await uploadPdf(file, (event) => {
        if (event.total) {
          const percent = Math.round((event.loaded * 100) / event.total);
          setProgress(percent);
        }
      });
      setDocument(data);
      setExtraction(null);
      setData(null);
      setRestoreNotice(null);
      setProgress(100);
      setSuccess(true);
    } catch (err) {
      setError(
        err.friendlyMessage ||
          err.response?.data?.detail ||
          "The PDF could not be processed.",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        submit(e.dataTransfer.files[0]);
      }}
      sx={{
        p: { xs: 3, md: 5 },
        textAlign: "center",
        borderRadius: 3,
        border: "1.5px dashed",
        borderColor: dragging ? "primary.main" : "divider",
        bgcolor: dragging ? "action.hover" : "background.paper",
        transition: "border-color .15s, background-color .15s",
        minHeight: 240,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {success ? (
        <CheckCircle color="success" sx={{ fontSize: 48, mb: 1.5 }} />
      ) : (
        <CloudUpload color="primary" sx={{ fontSize: 48, mb: 1.5, opacity: 0.9 }} />
      )}
      <Typography variant="h5" fontWeight={750} mb={0.75}>
        {success ? "Upload complete" : "Drop a PDF here"}
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 2.5, maxWidth: 420 }}>
        {success
          ? "The drawing is stored. Continue to extraction when you are ready."
          : "Upload stores and validates the PDF only. No analysis starts here."}
      </Typography>
      <input
        hidden
        ref={input}
        type="file"
        accept="application/pdf"
        onChange={(e) => submit(e.target.files?.[0])}
      />
      <Stack direction="row" spacing={1}>
        <TipButton
          title="Choose a PDF file"
          variant="contained"
          startIcon={<CloudUpload />}
          onClick={() => input.current?.click()}
          loading={loading}
          disabled={loading}
        >
          {loading ? "Uploading…" : "Choose PDF"}
        </TipButton>
      </Stack>
      {loading && (
        <Box sx={{ mt: 3, width: "100%", maxWidth: 360 }}>
          <LinearProgress variant="determinate" value={progress} />
          <Typography variant="caption" color="text.secondary" mt={0.75} display="block">
            {`${progress}% uploaded`}
          </Typography>
        </Box>
      )}
      {error && (
        <Alert severity="error" sx={{ mt: 2.5, textAlign: "left", width: "100%", maxWidth: 480 }}>
          {error}
        </Alert>
      )}
    </Box>
  );
}
