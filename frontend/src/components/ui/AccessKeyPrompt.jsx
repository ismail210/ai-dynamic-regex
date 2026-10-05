import { useEffect, useState } from "react";
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  TextField,
} from "@mui/material";
import { getAccessKey, onAccessDenied, setAccessKey } from "../../api/accessKey";

/**
 * Asks for the hosted backend's access key after it answers 401. Reloading
 * re-runs the workflow restore with the key in place.
 */
export default function AccessKeyPrompt() {
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState("");
  const rejected = Boolean(getAccessKey());

  useEffect(() => onAccessDenied(() => setOpen(true)), []);

  const submit = (event) => {
    event.preventDefault();
    setAccessKey(key.trim());
    window.location.reload();
  };

  return (
    <Dialog open={open} component="form" onSubmit={submit}>
      <DialogTitle>Access key required</DialogTitle>
      <DialogContent>
        <DialogContentText sx={{ mb: 2 }}>
          {rejected
            ? "The backend rejected the saved access key. Enter the current one."
            : "This Estima3D backend is private. Enter the access key you were given."}
        </DialogContentText>
        <TextField
          autoFocus
          fullWidth
          type="password"
          label="Access key"
          autoComplete="off"
          value={key}
          onChange={(event) => setKey(event.target.value)}
        />
      </DialogContent>
      <DialogActions>
        <Button type="submit" variant="contained" disabled={!key.trim()}>
          Continue
        </Button>
      </DialogActions>
    </Dialog>
  );
}
