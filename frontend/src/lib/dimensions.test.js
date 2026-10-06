import { describe, expect, it } from "vitest";
import { formatLength, formatPlate, formatPrintedSize, lengthFromInches, spokenLength } from "./dimensions";

describe("formatLength", () => {
  it("uses feet and inch symbols and keeps exact fractions", () => {
    expect(formatLength("69' - 4\"")).toBe("69′-4″");
    expect(formatLength("55'-10\"")).toBe("55′-10″");
    expect(formatLength("41' - 9 5/8\"")).toBe("41′-9⅝″");
    expect(formatLength("3/4\"")).toBe("¾″");
    expect(formatLength("1 1/4\"")).toBe("1¼″");
    expect(formatLength("12\"")).toBe("12″");
  });

  it("writes a clear minus sign", () => {
    expect(formatLength("-0'-5 1/4\"")).toBe("−0′-5¼″");
    expect(formatLength("-6\"")).toBe("−6″");
  });

  it("formats a backend inch value without rounding away the fraction", () => {
    expect(formatLength(376)).toBe("31′-4″");
    expect(formatLength(8)).toBe("8″");
    expect(formatLength(501.625)).toBe("41′-9⅝″");
    expect(lengthFromInches(null)).toBeNull();
  });

  it("leaves text that is not a length exactly as printed", () => {
    for (const text of ["C.8", "A.1'", "02", "W10X33", "#4@12\" O.C. E.F.", "SEE PLAN"]) {
      expect(formatLength(text)).toBe(text);
    }
  });
});

describe("spokenLength", () => {
  it("speaks units and fractions", () => {
    expect(spokenLength("69' - 4\"")).toBe("69 feet 4 inches");
    expect(spokenLength("3/4\"")).toBe("three quarters of an inch");
    expect(spokenLength("41' - 9 5/8\"")).toBe("41 feet 9 and five eighths inches");
    expect(spokenLength("-6\"")).toBe("minus 6 inches");
  });
});

describe("formatPlate", () => {
  it("orders by role: width × length × thickness", () => {
    const plate = formatPlate([
      { label: "thickness", raw: "3/4\"" },
      { label: "width", raw: "12\"" },
      { label: "length", raw: "18\"" },
    ]);
    expect(plate.text).toBe("12″ × 18″ × ¾″");
    expect(plate.roles).toBe("Width × Length × Thickness");
    expect(plate.spoken).toBe("width 12 inches, length 18 inches, thickness three quarters of an inch");
  });

  it("keeps values without a role in printed order", () => {
    expect(formatPlate([{ raw: "10\"" }, { raw: "1/2\"" }]).text).toBe("10″ × ½″");
  });
});

describe("formatPrintedSize", () => {
  it("formats a printed size and leaves anything else alone", () => {
    expect(formatPrintedSize("24\"x24\"")).toBe("24″ × 24″");
    expect(formatPrintedSize("24\" x 24\"")).toBe("24″ × 24″");
    expect(formatPrintedSize("HSS6X6X1/2")).toBe("HSS6X6X1/2");
  });
});
