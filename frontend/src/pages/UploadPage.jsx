import { Link } from "react-router-dom";
import { Alert, Stack } from "@mui/material";
import { ArrowForwardRounded } from "@mui/icons-material";
import FileUpload from "../components/FileUpload";
import { useAnalysis } from "../context/AnalysisContext";
import PageHeader from "../components/ui/PageHeader";
import { TipButton } from "../components/ui/ActionButtons";

export default function UploadPage() {
  const { document } = useAnalysis();

  return (
    <Stack spacing={2.5}>
      <PageHeader
        title="Upload drawing"
        subtitle="Store and validate the PDF. Extraction and AI analysis start only when you request them."
      />
      <FileUpload />
      {document && (
        <Alert
          severity="success"
          action={
            <TipButton
              title="Continue to extraction"
              variant="contained"
              component={Link}
              to="/extract"
              endIcon={<ArrowForwardRounded />}
            >
              Extract
            </TipButton>
          }
        >
          <strong>{document.source_file || document.filename}</strong> is stored
          as {document.document_id}. No OCR, geometry, or prediction has run.
        </Alert>
      )}
    </Stack>
  );
}
