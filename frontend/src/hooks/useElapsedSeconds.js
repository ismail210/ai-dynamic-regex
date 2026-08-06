import { useEffect, useState } from "react";

/**
 * Seconds since a long-running stage started, or 0 while idle.
 *
 * Extraction and analysis take tens of seconds on a full drawing set; without
 * a running counter the page is indistinguishable from a hung request.
 */
export default function useElapsedSeconds(running) {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    if (!running) {
      setSeconds(0);
      return undefined;
    }
    const startedAt = Date.now();
    setSeconds(0);
    const timer = setInterval(
      () => setSeconds(Math.round((Date.now() - startedAt) / 1000)),
      1000,
    );
    return () => clearInterval(timer);
  }, [running]);

  return seconds;
}
