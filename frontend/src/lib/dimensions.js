// Presentation of printed lengths, elevations and plate dimensions.
//
// Formatting is applied by meaning, never by shape: these helpers are for
// values the backend already classified as a length / elevation / plate
// dimension. Grid identifiers (C.8, A.1', 02), catalog designations
// (W10X33), marks and source strings are never passed through here -- they
// stay exactly as printed, so they can be copied and searched.
//
// Exact fractions are kept (5/8 -> ⅝); nothing is rounded into apparent
// precision, and the printed string stays available for "As printed".

const FRACTION_GLYPH = {
  "1/2": "½", "1/4": "¼", "3/4": "¾", "1/8": "⅛", "3/8": "⅜", "5/8": "⅝", "7/8": "⅞",
  "1/3": "⅓", "2/3": "⅔", "1/16": "1⁄16",
};
const FRACTION_WORDS = {
  "1/2": "one half", "1/4": "one quarter", "3/4": "three quarters", "1/8": "one eighth",
  "3/8": "three eighths", "5/8": "five eighths", "7/8": "seven eighths",
};
const MINUS = "−";

// 69' - 4", 41'-9 5/8", -0'-5 1/4", 55'-10", 8", 3/4", 1 1/4", 12", 24"
const FEET_INCH_RE = /^\s*([-+−]?)\s*(\d+)\s*['′’]\s*-?\s*(\d+)?(?:[\s-]+(\d+)\/(\d+))?\s*["″”]?\s*$/;
const INCH_RE = /^\s*([-+−]?)\s*(?:(\d+)(?:[\s-]+(\d+)\/(\d+))?|(\d+)\/(\d+))\s*["″”]\s*$/;

function reduce(num, den) {
  const gcd = (a, b) => (b ? gcd(b, a % b) : a);
  const g = gcd(num, den);
  return [num / g, den / g];
}

function fractionText(num, den) {
  if (!num) return "";
  const [n, d] = reduce(num, den);
  const key = `${n}/${d}`;
  return FRACTION_GLYPH[key] || `${n}⁄${d}`;
}

function fractionSpoken(num, den) {
  if (!num) return "";
  const [n, d] = reduce(num, den);
  return FRACTION_WORDS[`${n}/${d}`] || `${n} over ${d}`;
}

/** Parse a printed length into parts; ``null`` when it is not one. */
function parseLength(raw) {
  const text = String(raw ?? "").trim();
  let m = text.match(FEET_INCH_RE);
  if (m) {
    return {
      negative: m[1] === "-" || m[1] === MINUS, feet: Number(m[2]), inches: Number(m[3] || 0),
      num: m[4] ? Number(m[4]) : 0, den: m[5] ? Number(m[5]) : 1, hasFeet: true,
    };
  }
  m = text.match(INCH_RE);
  if (m) {
    if (m[5]) {
      return { negative: m[1] === "-" || m[1] === MINUS, feet: 0, inches: 0, num: Number(m[5]), den: Number(m[6]), hasFeet: false };
    }
    return {
      negative: m[1] === "-" || m[1] === MINUS, feet: 0, inches: Number(m[2]),
      num: m[3] ? Number(m[3]) : 0, den: m[4] ? Number(m[4]) : 1, hasFeet: false,
    };
  }
  return null;
}

/** From a decimal inch value (backend ``inches``), exact to 1/16". */
export function lengthFromInches(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return null;
  const sixteenths = Math.round(Math.abs(Number(value)) * 16);
  const feet = Math.floor(sixteenths / 192);
  const rest = sixteenths - feet * 192;
  return { negative: Number(value) < 0 && sixteenths > 0, feet, inches: Math.floor(rest / 16), num: rest % 16, den: 16, hasFeet: feet > 0 };
}

/** ``69′-4″``, ``41′-9⅝″``, ``8″``, ``¾″``, ``−0′-5¼″``. Unparseable text is returned as printed. */
export function formatLength(raw) {
  const parts = typeof raw === "number" ? lengthFromInches(raw) : parseLength(raw);
  if (!parts) return raw ?? "";
  const sign = parts.negative ? MINUS : "";
  const frac = fractionText(parts.num, parts.den);
  if (parts.hasFeet) {
    return `${sign}${parts.feet}′-${parts.inches}${frac}″`;
  }
  const whole = parts.feet * 12 + parts.inches;
  return `${sign}${whole || !frac ? whole : ""}${frac}″`;
}

/** Words for a screen reader: "69 feet 4 inches", "three quarters of an inch". */
export function spokenLength(raw) {
  const parts = typeof raw === "number" ? lengthFromInches(raw) : parseLength(raw);
  if (!parts) return String(raw ?? "");
  const words = [];
  if (parts.negative) words.push("minus");
  if (parts.hasFeet) words.push(`${parts.feet} ${parts.feet === 1 ? "foot" : "feet"}`);
  const frac = fractionSpoken(parts.num, parts.den);
  const whole = parts.hasFeet ? parts.inches : parts.feet * 12 + parts.inches;
  if (whole && frac) words.push(`${whole} and ${frac} inches`);
  else if (whole) words.push(`${whole} ${whole === 1 ? "inch" : "inches"}`);
  else if (frac) words.push(`${frac} of an inch`);
  else words.push("0 inches");
  return words.join(" ");
}

const PLATE_ROLE_ORDER = ["width", "length", "thickness"];
const ROLE_LABEL = { width: "Width", length: "Length", thickness: "Thickness" };

/**
 * Plate dimensions in a fixed role order -- Width × Length × Thickness --
 * with each value's role. Values without a role keep their printed order.
 */
function plateParts(dimensions) {
  const dims = dimensions || [];
  const byRole = PLATE_ROLE_ORDER.map((role) => dims.find((d) => d.label === role)).filter(Boolean);
  const rest = dims.filter((d) => !PLATE_ROLE_ORDER.includes(d.label));
  return [...byRole, ...rest].map((d) => ({
    label: ROLE_LABEL[d.label] || (d.label ? d.label[0].toUpperCase() + d.label.slice(1) : "Dimension"),
    text: formatLength(d.raw),
    spoken: spokenLength(d.raw),
    raw: d.raw,
  }));
}

/** ``12″ × 18″ × ¾″`` and the role order it is written in. */
export function formatPlate(dimensions) {
  const parts = plateParts(dimensions);
  return {
    text: parts.map((p) => p.text).join(" × "),
    roles: parts.map((p) => p.label).join(" × "),
    spoken: parts.map((p) => `${p.label.toLowerCase()} ${p.spoken}`).join(", "),
    parts,
  };
}

/** ``24"x24"`` (a printed size) -> ``24″ × 24″``; as printed when a part does not read. */
export function formatPrintedSize(raw) {
  const pieces = String(raw ?? "").split(/\s*[xX×]\s*/).filter(Boolean);
  if (pieces.length < 2 || pieces.some((p) => !parseLength(p))) return raw ?? "";
  return pieces.map((p) => formatLength(p)).join(" × ");
}
