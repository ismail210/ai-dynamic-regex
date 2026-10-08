import { useEffect, useState } from "react";
import { Alert, AlertTitle, Button } from "@mui/material";
import { checkBackendIdentity, onBackendIdentity } from "../../api/devIdentity";

/**
 * States why API calls are refused (or warns) when this frontend is not paired
 * with its own backend: its worktree's in development, its image build in
 * containers. Renders nothing when paired.
 */
export default function BackendIdentityBanner() {
  const [identity, setIdentity] = useState(null);

  useEffect(() => {
    const unsubscribe = onBackendIdentity(setIdentity);
    checkBackendIdentity();
    return unsubscribe;
  }, []);

  if (!identity || (identity.ok && !identity.warning)) return null;
  return (
    <Alert
      severity={identity.ok ? "warning" : "error"}
      sx={{ mb: 2 }}
      action={
        <Button color="inherit" size="small" onClick={() => checkBackendIdentity()}>
          Check again
        </Button>
      }
    >
      <AlertTitle>
        {identity.ok ? "Backend revision differs" : "Backend check failed — upload and extraction are blocked"}
      </AlertTitle>
      {identity.problem || identity.warning}
    </Alert>
  );
}
