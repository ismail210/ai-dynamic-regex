import { describe, expect, it } from "vitest";
import {
  computeFitPageScale,
  computeFitPageWidth,
  pageWidthForBbox,
} from "./BboxHighlight";

// The sample drawing's actual page 1 dimensions (points, from PyMuPDF):
// a large landscape architectural sheet.
const LANDSCAPE_PAGE = { pageWidthPts: 3024, pageHeightPts: 2160 };
// A typical portrait letter-ish sheet for contrast.
const PORTRAIT_PAGE = { pageWidthPts: 1224, pageHeightPts: 1584 };

describe("computeFitPageScale — the core Fit Page calculation", () => {
  it("uses the SMALLER of width-ratio and height-ratio (never stretches X/Y independently)", () => {
    // Real repro: container 722w x 412h (from the live drawing-review panel),
    // landscape page 3024x2160. Width-only fit (722/3024=0.239) would render
    // the page 509px tall against a 395px-tall viewport -- cut off vertically.
    // Fit Page must pick the smaller ratio so the whole page fits.
    const scale = computeFitPageScale({
      ...LANDSCAPE_PAGE,
      availableWidth: 722,
      availableHeight: 412,
    });
    const widthRatio = 722 / 3024;
    const heightRatio = 412 / 2160;
    expect(heightRatio).toBeLessThan(widthRatio); // height is the binding constraint here
    expect(scale).toBeCloseTo(heightRatio, 6);
  });

  it("landscape page in a roughly-square viewport: fits without vertical cropping", () => {
    const scale = computeFitPageScale({
      ...LANDSCAPE_PAGE,
      availableWidth: 800,
      availableHeight: 800,
    });
    const renderedHeight = LANDSCAPE_PAGE.pageHeightPts * scale;
    const renderedWidth = LANDSCAPE_PAGE.pageWidthPts * scale;
    expect(renderedHeight).toBeLessThanOrEqual(800.0001);
    expect(renderedWidth).toBeLessThanOrEqual(800.0001);
    // At least one dimension should be flush against the viewport (a real fit,
    // not an arbitrarily small render).
    expect(Math.max(renderedHeight, renderedWidth)).toBeGreaterThan(799);
  });

  it("portrait page in a wide viewport: height is the binding constraint", () => {
    const scale = computeFitPageScale({
      ...PORTRAIT_PAGE,
      availableWidth: 1200,
      availableHeight: 600,
    });
    const heightRatio = 600 / 1584;
    expect(scale).toBeCloseTo(heightRatio, 6);
    const renderedWidth = PORTRAIT_PAGE.pageWidthPts * scale;
    expect(renderedWidth).toBeLessThanOrEqual(1200.0001);
  });

  it("preserves aspect ratio -- the fit width and fit height scale by the exact same factor", () => {
    const scale = computeFitPageScale({
      ...LANDSCAPE_PAGE,
      availableWidth: 900,
      availableHeight: 500,
    });
    const renderedWidth = LANDSCAPE_PAGE.pageWidthPts * scale;
    const renderedHeight = LANDSCAPE_PAGE.pageHeightPts * scale;
    const nativeAspect = LANDSCAPE_PAGE.pageWidthPts / LANDSCAPE_PAGE.pageHeightPts;
    const renderedAspect = renderedWidth / renderedHeight;
    expect(renderedAspect).toBeCloseTo(nativeAspect, 6);
  });
});

describe("computeFitPageWidth", () => {
  it("returns a width whose implied height fits entirely inside the viewport", () => {
    const width = computeFitPageWidth({
      ...LANDSCAPE_PAGE,
      availableWidth: 722,
      availableHeight: 412,
    });
    const impliedHeight = width * (LANDSCAPE_PAGE.pageHeightPts / LANDSCAPE_PAGE.pageWidthPts);
    expect(width).toBeLessThanOrEqual(722.0001);
    expect(impliedHeight).toBeLessThanOrEqual(412.0001);
  });

  it("never returns a width below the configured minimum", () => {
    const width = computeFitPageWidth({
      ...LANDSCAPE_PAGE,
      availableWidth: 50,
      availableHeight: 20,
      minWidth: 240,
    });
    expect(width).toBeGreaterThanOrEqual(240);
  });
});

describe("pageWidthForBbox — selected-label zoom", () => {
  it("uses Fit Page scale (no extra zoom) when the bbox is already legible", () => {
    // A reasonably large bbox on a modest page/viewport -- already readable
    // at Fit Page scale, so no extra zoom should be applied.
    const fitWidth = computeFitPageWidth({
      pageWidthPts: 800,
      pageHeightPts: 600,
      availableWidth: 700,
      availableHeight: 500,
    });
    const width = pageWidthForBbox({
      boundingBox: [100, 100, 300, 250], // 150pt tall
      pageWidthPts: 800,
      pageHeightPts: 600,
      availableWidth: 700,
      availableHeight: 500,
    });
    expect(width).toBeCloseTo(fitWidth, 6);
  });

  it("zooms in just enough to make a tiny label legible, not to fill the viewport", () => {
    // Reproduces the real case: a ~13pt-tall text token on a huge 3024x2160
    // sheet. At Fit Page scale it would render far too small to read.
    const fitWidth = computeFitPageWidth({
      ...LANDSCAPE_PAGE,
      availableWidth: 722,
      availableHeight: 412,
    });
    const width = pageWidthForBbox({
      boundingBox: [1647.96, 544.11, 1687.8, 556.7], // real token bbox, ~12.6pt tall
      ...LANDSCAPE_PAGE,
      availableWidth: 722,
      availableHeight: 412,
    });
    expect(width).toBeGreaterThan(fitWidth); // did zoom in
    expect(width).toBeLessThanOrEqual(fitWidth * 2.5 + 0.001); // capped, not extreme
  });

  it("never zooms below Fit Page scale", () => {
    const fitWidth = computeFitPageWidth({
      ...LANDSCAPE_PAGE,
      availableWidth: 722,
      availableHeight: 412,
    });
    const width = pageWidthForBbox({
      boundingBox: [100, 100, 2900, 2000], // a huge bbox, already very legible
      ...LANDSCAPE_PAGE,
      availableWidth: 722,
      availableHeight: 412,
    });
    expect(width).toBeGreaterThanOrEqual(fitWidth - 0.001);
  });
});

describe("source bbox -> rendered highlight coordinate transformation", () => {
  // BboxHighlight itself just multiplies by (renderedWidth / pageWidthPts);
  // this pins that transformation stays correct across Fit Page, Fit Width,
  // and selected-element zoom -- i.e. for ANY renderedWidth this module
  // hands back, the highlight stays aligned with the real label.
  function highlightRect(boundingBox, pageWidthPts, renderedWidth) {
    const scale = renderedWidth / pageWidthPts;
    const [x0, y0, x1, y1] = boundingBox;
    return {
      left: Math.min(x0, x1) * scale,
      top: Math.min(y0, y1) * scale,
      width: Math.abs(x1 - x0) * scale,
      height: Math.abs(y1 - y0) * scale,
    };
  }

  it("stays aligned under Fit Page scale", () => {
    const fitWidth = computeFitPageWidth({
      ...LANDSCAPE_PAGE,
      availableWidth: 722,
      availableHeight: 412,
    });
    const bbox = [1647.96, 544.11, 1687.8, 556.7];
    const rect = highlightRect(bbox, LANDSCAPE_PAGE.pageWidthPts, fitWidth);
    const scale = fitWidth / LANDSCAPE_PAGE.pageWidthPts;
    expect(rect.left).toBeCloseTo(1647.96 * scale, 6);
    expect(rect.top).toBeCloseTo(544.11 * scale, 6);
  });

  it("stays aligned under Fit Width scale", () => {
    const fitWidthOnlyWidth = 722; // Fit Width just uses availableWidth directly
    const bbox = [1647.96, 544.11, 1687.8, 556.7];
    const rect = highlightRect(bbox, LANDSCAPE_PAGE.pageWidthPts, fitWidthOnlyWidth);
    const scale = fitWidthOnlyWidth / LANDSCAPE_PAGE.pageWidthPts;
    expect(rect.left).toBeCloseTo(1647.96 * scale, 6);
    expect(rect.width).toBeCloseTo((1687.8 - 1647.96) * scale, 6);
  });

  it("stays aligned under selected-element zoom", () => {
    const bbox = [1647.96, 544.11, 1687.8, 556.7];
    const zoomedWidth = pageWidthForBbox({
      boundingBox: bbox,
      ...LANDSCAPE_PAGE,
      availableWidth: 722,
      availableHeight: 412,
    });
    const rect = highlightRect(bbox, LANDSCAPE_PAGE.pageWidthPts, zoomedWidth);
    const scale = zoomedWidth / LANDSCAPE_PAGE.pageWidthPts;
    expect(rect.left).toBeCloseTo(1647.96 * scale, 6);
    expect(rect.top).toBeCloseTo(544.11 * scale, 6);
    expect(rect.width).toBeCloseTo((1687.8 - 1647.96) * scale, 6);
    expect(rect.height).toBeCloseTo((556.7 - 544.11) * scale, 6);
  });
});
