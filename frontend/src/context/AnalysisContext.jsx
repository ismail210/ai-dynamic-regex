import { createContext, useContext, useMemo, useState } from "react";

const AnalysisContext = createContext(null);

export function AnalysisProvider({ children }) {
  const [document, setDocument] = useState(null);
  const [extraction, setExtraction] = useState(null);
  const [data, setData] = useState(null);
  const clearData = () => {
    setDocument(null);
    setExtraction(null);
    setData(null);
  };
  const value = useMemo(
    () => ({
      document,
      setDocument,
      extraction,
      setExtraction,
      data,
      setData,
      clearData,
      stage: data
        ? "analyzed"
        : extraction
          ? "extracted"
          : document
            ? "uploaded"
            : "empty",
    }),
    [data, document, extraction],
  );
  return <AnalysisContext.Provider value={value}>{children}</AnalysisContext.Provider>;
}

export function useAnalysis() {
  const context = useContext(AnalysisContext);
  if (!context) throw new Error("useAnalysis must be used within AnalysisProvider");
  return context;
}
