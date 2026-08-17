import { act, fireEvent, render, screen } from "@testing-library/react";
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
const loadCallbacks = {};
const PAGE_WIDTH_PTS = 3024;
const PAGE_HEIGHT_PTS = 2160;

// @mui/icons-material's barrel is ~11k modules, more than macOS's 10240
// per-process file descriptor cap allows Vite to transform at once (EMFILE
// during collection). The zoom buttons are found by their aria-labels, so the
// glyphs themselves are irrelevant here.
vi.mock("@mui/icons-material", () => ({
  ZoomIn: () => <span />,
  ZoomOut: () => <span />,
}));

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
    loadCallbacks[pageNumber] = () =>
      onLoadSuccess?.({
        getViewport: () => ({ width: PAGE_WIDTH_PTS, height: PAGE_HEIGHT_PTS }),
      });
    useEffect(() => {
      if (loaded.current) return;
      loaded.current = true;
      loadCallbacks[pageNumber]();
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

// Stands in for an UNRELATED page finishing its own load in a real,
// multi-page document (all ~30 pages of a real drawing set load
// concurrently): it changes the pageSizes state's object identity via a
// redundant setState, without changing the current selection or its target
// page's own dimensions -- reproducing the actual trigger for the bug this
// guards against, without needing a second mocked page in the suite.
function simulateUnrelatedPageSizesUpdate(pageNumber = 1) {
  act(() => {
    loadCallbacks[pageNumber]?.();
  });
}

// jsdom has no real layout engine, so clientWidth/clientHeight on any
// element default to 0 and ResizeObserver is not implemented. Stub both so
// the Fit Page / resize behavior can be exercised deterministically: the
// component re-measures via `node.clientWidth`/`clientHeight` every time
// the observer callback fires (see its `measure` function), regardless of
// what the ResizeObserver API's own `entries` argument says -- so driving
// the fake observer's stored callback after changing the stubbed
// dimensions is enough to simulate a real resize.
let roCallback = null;
class FakeResizeObserver {
  constructor(cb) {
    roCallback = cb;
  }
  observe() {}
  disconnect() {}
}

function setContainerClientSize(container, width, height) {
  const node = container.querySelector('[data-testid="pdf-scroll-container"]');
  Object.defineProperty(node, "clientWidth", { value: width, configurable: true });
  Object.defineProperty(node, "clientHeight", { value: height, configurable: true });
  return node;
}

function triggerResize() {
  act(() => {
    roCallback?.();
  });
}

describe("PdfDocumentViewer zoom-to-selection scroll timing", () => {
  let scrollSpy;
  let rafSpy;

  beforeEach(() => {
    scrollSpy = vi.fn();
    // The viewer scrolls its own container rather than delegating to
    // scrollIntoView, so that a label near a page edge clamps to the nearest
    // visible offset instead of asking for an impossible centered one.
    Element.prototype.scrollTo = scrollSpy;
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

// jsdom has no layout engine, so the scroll geometry the viewer reads
// (getBoundingClientRect / clientWidth / scrollWidth) has to be supplied
// explicitly. These stand in for a sheet zoomed well past the panel width,
// which is the only situation where an edge label can fall outside the
// viewport in the first place.
function stubScrollGeometry(container, { targetLeft, targetTop, scrollLeft = 0, scrollTop = 0 }) {
  const scroller = container.querySelector('[data-testid="pdf-scroll-container"]');
  Object.defineProperty(scroller, "clientWidth", { value: 731, configurable: true });
  Object.defineProperty(scroller, "clientHeight", { value: 403, configurable: true });
  Object.defineProperty(scroller, "scrollWidth", { value: 3000, configurable: true });
  Object.defineProperty(scroller, "scrollHeight", { value: 2000, configurable: true });
  scroller.scrollLeft = scrollLeft;
  scroller.scrollTop = scrollTop;
  scroller.getBoundingClientRect = () => ({
    left: 0, top: 0, right: 731, bottom: 403, width: 731, height: 403,
  });
  const highlight = container.querySelector('[data-bbox-highlight="active"]');
  highlight.getBoundingClientRect = () => ({
    left: targetLeft,
    top: targetTop,
    right: targetLeft + 40,
    bottom: targetTop + 12,
    width: 40,
    height: 12,
  });
  return scroller;
}

describe("PdfDocumentViewer locating labels at a page edge", () => {
  let scrollSpy;

  beforeEach(() => {
    scrollSpy = vi.fn();
    Element.prototype.scrollTo = scrollSpy;
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      cb();
      return 1;
    });
  });

  afterEach(() => {
    delete renderCallbacks[1];
    vi.restoreAllMocks();
  });

  function selectAndScroll(geometry) {
    const { container, rerender } = render(
      <PdfDocumentViewer fileUrl="test.pdf" selection={null} />,
    );
    finishRender(1);
    rerender(
      <PdfDocumentViewer
        fileUrl="test.pdf"
        selection={{ key: "edge", pageNumber: 1, boundingBox: [4, 8, 44, 20] }}
      />,
    );
    stubScrollGeometry(container, geometry);
    finishRender(1);
    return scrollSpy.mock.calls.at(-1)?.[0];
  }

  it("scrolls to a label at the left edge instead of requesting an unreachable centered offset", () => {
    // Centering a label 4pt from the left border would need a negative
    // scroll offset, which is why these members previously never came into
    // view. Clamping to 0 shows the sheet's left edge, label included.
    const scroll = selectAndScroll({ targetLeft: -1200, targetTop: 150, scrollLeft: 1200 });

    expect(scroll).toBeTruthy();
    expect(scroll.left).toBe(0);
    expect(scroll.left).toBeGreaterThanOrEqual(0);
  });

  it("clamps to the maximum scroll offset for a label at the right edge", () => {
    const scroll = selectAndScroll({ targetLeft: 4000, targetTop: 150 });

    // scrollWidth - clientWidth, i.e. as far right as the panel can go.
    expect(scroll.left).toBe(3000 - 731);
  });

  it("never emits a negative vertical offset for a label at the top edge", () => {
    const scroll = selectAndScroll({ targetLeft: 300, targetTop: -900, scrollTop: 900 });

    expect(scroll.top).toBe(0);
  });
});

describe("PdfDocumentViewer Fit Page / manual zoom / resize", () => {
  let originalResizeObserver;

  beforeEach(() => {
    Element.prototype.scrollTo = vi.fn();
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      cb();
      return 1;
    });
    roCallback = null;
    originalResizeObserver = window.ResizeObserver;
    window.ResizeObserver = FakeResizeObserver;
  });

  afterEach(() => {
    delete renderCallbacks[1];
    window.ResizeObserver = originalResizeObserver;
    vi.restoreAllMocks();
  });

  function canvasWidth() {
    return Number(screen.getByTestId("page-1").dataset.width);
  }

  it("defaults to Fit Page: a landscape page taller-than-wide-viewport is scaled by the HEIGHT ratio, not just width", () => {
    const { container } = render(
      <PdfDocumentViewer fileUrl="test.pdf" selection={null} />,
    );
    // Real repro dimensions from the live app: a scrollable panel roughly as
    // tall as it is wide, containing a wide landscape sheet. Fit-width-only
    // would render this page at ~713x509 against a ~395px-tall viewport.
    setContainerClientSize(container, 731, 403);
    triggerResize();
    finishRender(1);

    const width = canvasWidth();
    const impliedHeight = width * (PAGE_HEIGHT_PTS / PAGE_WIDTH_PTS);
    // The whole page must fit -- both dimensions inside the (padding-adjusted)
    // viewport -- not just the width.
    expect(width).toBeLessThanOrEqual(731 - 8 + 0.5);
    expect(impliedHeight).toBeLessThanOrEqual(403 - 8 + 0.5);
  });

  it("resizing the panel recalculates Fit Page instead of leaving an obsolete scale", () => {
    const { container } = render(
      <PdfDocumentViewer fileUrl="test.pdf" selection={null} />,
    );
    setContainerClientSize(container, 731, 403);
    triggerResize();
    finishRender(1);
    const widthBefore = canvasWidth();

    setContainerClientSize(container, 1400, 900);
    triggerResize();
    finishRender(1);
    const widthAfter = canvasWidth();

    expect(widthAfter).toBeGreaterThan(widthBefore);
    const impliedHeightAfter = widthAfter * (PAGE_HEIGHT_PTS / PAGE_WIDTH_PTS);
    expect(widthAfter).toBeLessThanOrEqual(1400 - 8 + 0.5);
    expect(impliedHeightAfter).toBeLessThanOrEqual(900 - 8 + 0.5);
  });

  it("Fit Page restores the full sheet after a selected-element zoom", () => {
    const { container, rerender } = render(
      <PdfDocumentViewer fileUrl="test.pdf" selection={null} />,
    );
    setContainerClientSize(container, 731, 403);
    triggerResize();
    finishRender(1);
    const fitPageWidth = canvasWidth();

    // Select a small label -- zooms in past Fit Page.
    rerender(
      <PdfDocumentViewer
        fileUrl="test.pdf"
        selection={{ key: "a", pageNumber: 1, boundingBox: [1647.96, 544.11, 1687.8, 556.7] }}
      />,
    );
    finishRender(1);
    expect(canvasWidth()).toBeGreaterThan(fitPageWidth);

    // The reviewer clicks "Fit page" to see the whole sheet again.
    fireEvent.click(screen.getByText("Fit page"));
    finishRender(1);
    expect(canvasWidth()).toBeCloseTo(fitPageWidth, 0);
  });

  it("Fit page click is not undone by an unrelated page finishing its own load afterward", () => {
    // Regression test for a real bug caught during live verification: the
    // selection auto-zoom effect depends on `pageSizes`, which is shared
    // across every page in the document. In a real ~30-page drawing set,
    // pages keep finishing their own loads well after this selection's zoom
    // was first applied, which kept re-running that effect and silently
    // reasserting "selection" zoom over whatever the reviewer had just
    // clicked (Fit page/Fit width) a moment later.
    const { container, rerender } = render(
      <PdfDocumentViewer fileUrl="test.pdf" selection={null} />,
    );
    setContainerClientSize(container, 731, 403);
    triggerResize();
    finishRender(1);
    const fitPageWidth = canvasWidth();

    rerender(
      <PdfDocumentViewer
        fileUrl="test.pdf"
        selection={{ key: "a", pageNumber: 1, boundingBox: [1647.96, 544.11, 1687.8, 556.7] }}
      />,
    );
    finishRender(1);
    expect(canvasWidth()).toBeGreaterThan(fitPageWidth); // auto-zoomed in

    fireEvent.click(screen.getByText("Fit page"));
    finishRender(1);
    expect(canvasWidth()).toBeCloseTo(fitPageWidth, 0);

    // An unrelated page elsewhere in the document finishes loading --
    // pageSizes changes identity, but neither the selection nor the
    // relevant page's own dimensions changed.
    simulateUnrelatedPageSizesUpdate(1);
    finishRender(1);

    // Fit Page must still be in effect -- not silently reverted to the
    // selection zoom.
    expect(canvasWidth()).toBeCloseTo(fitPageWidth, 0);
  });

  it("manual zoom in/out changes scale but never changes the current page", () => {
    const { container, rerender } = render(
      <PdfDocumentViewer fileUrl="test.pdf" selection={null} />,
    );
    setContainerClientSize(container, 731, 403);
    triggerResize();
    finishRender(1);

    // Select a label -- navigates to and zooms into its page.
    rerender(
      <PdfDocumentViewer
        fileUrl="test.pdf"
        selection={{ key: "a", pageNumber: 1, boundingBox: [1647.96, 544.11, 1687.8, 556.7] }}
      />,
    );
    finishRender(1);
    expect(screen.getByTestId("pdf-viewer-root").dataset.currentPage).toBe("1");
    const zoomedWidth = canvasWidth();

    const zoomInBtn = screen.getByLabelText("Zoom in");
    fireEvent.click(zoomInBtn);
    expect(canvasWidth()).toBeGreaterThan(zoomedWidth);
    expect(screen.getByTestId("pdf-viewer-root").dataset.currentPage).toBe("1");

    fireEvent.click(screen.getByLabelText("Zoom out"));
    fireEvent.click(screen.getByLabelText("Zoom out"));
    expect(screen.getByTestId("pdf-viewer-root").dataset.currentPage).toBe("1");
  });
});
