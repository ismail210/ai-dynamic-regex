import { act, render } from "@testing-library/react";
import { useEffect, useRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PdfDocumentViewer from "./PdfDocumentViewer";

// react-pdf needs a real canvas/worker; stub it so this test can control
// exactly when a page's canvas "finishes rendering" instead of relying on
// PDF.js actually rasterizing anything. Real react-pdf only calls these
// callbacks once per actual load/render, never on every re-render -- doing
// the same here matters, since PdfDocumentViewer's own onLoadSuccess handler
// calls setState with a fresh object each time, and firing unconditionally
// on every render would starve React into an infinite render loop.
const renderCallbacks = {};
const PAGE_WIDTH_PTS = 3024;
const PAGE_HEIGHT_PTS = 2160;

vi.mock("react-pdf", () => ({
  pdfjs: { GlobalWorkerOptions: {} },
  Document: ({ children, onLoadSuccess }) => {
    const fired = useRef(false);
    useEffect(() => {
      if (fired.current) return;
      fired.current = true;
      onLoadSuccess?.({ numPages: 1 });
    }, [onLoadSuccess]);
    return <div>{children}</div>;
  },
  Page: ({ pageNumber, width, onLoadSuccess, onRenderSuccess }) => {
    const loaded = useRef(false);
    useEffect(() => {
      if (loaded.current) return;
      loaded.current = true;
      onLoadSuccess?.({
        getViewport: () => ({ width: PAGE_WIDTH_PTS, height: PAGE_HEIGHT_PTS }),
      });
    }, [onLoadSuccess]);
    // Deliberately NOT calling onRenderSuccess here -- the test decides when
    // "rendering" completes by invoking the stashed callback itself. This is
    // exactly the race the fix targets: onLoadSuccess (intrinsic page size)
    // fires immediately, but the canvas repaint at a NEW zoomed width is
    // genuinely asynchronous and must not be assumed to have finished yet.
    renderCallbacks[pageNumber] = onRenderSuccess;
    return <canvas data-testid={`page-${pageNumber}`} data-width={width} />;
  },
}));

function finishRender(pageNumber) {
  act(() => {
    renderCallbacks[pageNumber]?.();
  });
}

describe("PdfDocumentViewer zoom-to-selection scroll timing", () => {
  let scrollSpy;
  let rafSpy;

  beforeEach(() => {
    scrollSpy = vi.fn();
    Element.prototype.scrollIntoView = scrollSpy;
    // jsdom's requestAnimationFrame is timer-based and not reliably fast in
    // a test environment; fire synchronously so the "already at target
    // width" fallback path is deterministic instead of timing-dependent.
    rafSpy = vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      cb();
      return 1;
    });
  });

  afterEach(() => {
    delete renderCallbacks[1];
    rafSpy.mockRestore();
    vi.restoreAllMocks();
  });

  it("does not scroll until the page finishes (re)rendering at the new zoomed width", async () => {
    const { rerender } = render(
      <PdfDocumentViewer fileUrl="test.pdf" selection={null} />,
    );

    // Selecting a small bbox forces a zoom (new pageWidth != default), which
    // is the case that requires waiting for onRenderSuccess.
    rerender(
      <PdfDocumentViewer
        fileUrl="test.pdf"
        selection={{ key: "a", pageNumber: 1, boundingBox: [100, 100, 140, 120] }}
      />,
    );

    // Canvas repaint has not "finished" yet (test hasn't called finishRender) --
    // scrolling now would compute against the page's OLD extents.
    expect(scrollSpy).not.toHaveBeenCalled();

    finishRender(1);

    expect(scrollSpy).toHaveBeenCalled();
  });

  it("scrolls without waiting for a render event when re-selecting at the same zoom width", async () => {
    const { rerender } = render(
      <PdfDocumentViewer fileUrl="test.pdf" selection={null} />,
    );
    rerender(
      <PdfDocumentViewer
        fileUrl="test.pdf"
        selection={{ key: "a", pageNumber: 1, boundingBox: [100, 100, 140, 120] }}
      />,
    );
    finishRender(1);
    scrollSpy.mockClear();

    // Same page, same effective zoom width, different bbox -- no new
    // onRenderSuccess will fire since react-pdf skips re-rendering when the
    // width prop is unchanged, so this must not hang waiting for one.
    act(() => {
      rerender(
        <PdfDocumentViewer
          fileUrl="test.pdf"
          selection={{ key: "b", pageNumber: 1, boundingBox: [100, 300, 140, 320] }}
        />,
      );
    });

    expect(scrollSpy).toHaveBeenCalled();
  });
});
