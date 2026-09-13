# GHX Geometry Audit (static, read-only)

- Path: `C:\Users\Bassam\Downloads\estima3d_web_plan.ghx` (never modified, moved, or renamed this session)
- SHA-256: `35d5bb064f30ad82c7364485f4a53ee15971581aed9d7b117e382e95c75fab0e`
- File size: 6,798,022 bytes
- Last modified (source file, on disk): 2026-09-12 11:42:41
- Top-level object count (DefinitionObjects): 315 -- matches the count given in the audit brief exactly, which is a good cross-check that the parsing method below is sound.

## Findings summary (read this first)

1. **Rhino.Compute bridge confirmed and fully recovered.** A C# script component (base64-encoded in the archive, decoded in full below) implements exactly the `i3dmBase64 -> Rhino.Geometry.GeometryBase` bridge described in the audit brief: `File3dm.FromByteArray`, iterating `archive.Objects`, wired as `x <- i3dmBase64 (base64 .3dm from Rhino.Compute REST)` / `a -> RH_OUT:i3dmContents`. **Discrepancy found:** no top-level Group literally named `RH_OUT:i3dmContents` exists anywhere in the definition (checked by direct string search on the raw file, not just the parsed object list) -- the script's own code comment describes an output name that isn't wired to a page-level RH_OUT boundary. Most likely explanation: the imported `.3dm` geometry becomes raw *input* geometry feeding `MAIN_PlanPurging`, not itself an exposed output; the comment may be stale documentation inside the script. This is not something to fix (the file is read-only) -- just a documented discrepancy.
2. **`MAIN_PlanPurging`, `MAIN_FilterBeamText`, `MAIN_BeamProcessing&Selection`, and `MAIN_BeamsMomentConnection` are genuine Cluster components** (they each carry a `ClusterDocument` bytearray payload), not merely visual Group boxes. This was not obvious from the parsed data alone -- their `Name` field holds the user's custom cluster name rather than the literal string `"Cluster"`, which is why a naive check (`type_name == "Cluster"`) misses them; only 2 of the real 6 clusters in this file (`BeamsSheetTitle`, `BeamConnections`) have `Name == "Cluster"` literally. Verified by a direct raw-item dump of the `MAIN_PlanPurging` object (its Container carries a `ClusterDocument` item alongside `Name="MAIN_PlanPurging"` and `Description="Contains a cluster of Grasshopper components"`), cross-checked against the same dump for `RH_OUT:BeamCrv` (a real Group: `Name="Group"`, `Description="A group of Grasshopper objects"`, 3 `ID` member guids).
3. **RH_OUT:* names are GH Group annotations, not components.** Each carries an explicit `ID`/`ID_Count` member list (the guids of the actual objects it boxes) -- resolved below against the full 315-object index so each output's real producing component is known, not guessed.
4. **The BeamTxt <-> BeamCrv pairing contract is UNRESOLVED at this session's depth of analysis, and is explicitly documented as such rather than assumed.** RH_OUT groups only reveal *membership* (which components sit in the box), not *data-tree structure* (whether two outputs' list/tree branches correspond 1:1). Answering this conclusively requires either (a) actually running the definition once through Rhino.Compute/Grasshopper with a real project and inspecting the resulting data trees, or (b) fully deserializing the ~1.24MB nested binary GH_IO document inside the `MAIN_BeamProcessing&Selection` cluster (found via best-effort zlib decompression below, but that inner document is itself in GH_IO's *binary* chunk format, not XML -- deserializing it is a materially bigger undertaking than parsing the outer XML file, and the audit brief explicitly says not to sink multiple days into GH_IO reverse-engineering). **Architectural consequence: the semantic pipeline implemented this session never assumes index or tree alignment between separate RH_OUT lists** -- `GrasshopperGeometryEvidenceProvider` (see `backend/services/semantic_preprocessor/geometry_evidence.py`) only trusts a text<->curve pairing when the capture payload states one explicitly (e.g. a shared `element_id`/`BeamElementID`), and falls back to the pipeline's own deterministic nearest-geometry association otherwise.
5. **Catalog contract divergence found and documented, not silently unified.** The GHX's own AISC-lookup Python script contains the literal comment `# Keep in sync with backend/integrations/steel/section_catalog.py normalize_designation()`. That path **does not exist anywhere in this repository** (checked across all 4 local worktrees) -- the actual current normalization logic lives in `backend/services/normalization.py` and `backend/services/label_reconstruction/structural_parser.py`. This is either stale documentation inside the GHX script, or a planned contract that was never implemented at that path. Per Section 25's explicit instruction, this divergence is documented here rather than "fixed" by rewriting either side.
6. **`BeamElementID`'s exact semantics are unresolved.** Its RH_OUT group has 3 members (one resolves to a `Text` param, two are unresolved raw `Param` objects this static method can't classify -- see Limitations). Whether it is a per-beam stable identifier that survives across separate runs of the same input, as the brief hopes, could not be confirmed statically; this needs the live-run experiment (Top-5 Experiment 1) to answer.

## Method
Static XML parse of the GH_IO archive format (no Rhino/Grasshopper install available in this environment, so OPTION A/C from the audit brief were not possible; this is OPTION B). Top-level objects were read directly from the `DefinitionObjects` chunk's own `Object` children -- type name from the object's direct `<items>`, nickname/description/instance guid from its nested `Container` chunk's direct `<items>`. Nested Cluster documents are opaque (embedded as separate encoded payloads, not literal child Object chunks), so cluster internals below are from best-effort base64/deflate recovery, not full GH_IO deserialization -- treat cluster-internal findings as indicative, not authoritative.

## RH_OUT contract found
42 named Groups with a nickname starting `RH_OUT:`. Each is a GH Group annotation whose `ID`/`ID_Count` items enumerate the instance guids of the actual components it boxes -- resolved below against the full object index to identify what really produces each output:

- `RH_OUT:DeckSheetName` (2 member(s)): ?, ?
- `RH_OUT:BeamTxt` (2 member(s)): ?, Text Entity "Text Entity"
- `RH_OUT:BeamCrv` (3 member(s)): ?, ?, Data "Data"
- `RH_OUT:BeamTxtUnpaired` (2 member(s)): ?, Text Entity "Text Entity"
- `RH_OUT:BeamTypeCnt` (2 member(s)): ?, Integer "Integer"
- `RH_OUT:BeamTypeList` (2 member(s)): ?, Text "Text"
- `RH_OUT:BeamLength` (1 member(s)): Number "Number"
- `RH_OUT:BeamCamber` (1 member(s)): Text "Text"
- `RH_OUT:BeamStudCnt` (2 member(s)): ?, Data "Data"
- `RH_OUT:BeamType` (1 member(s)): Text "Text"
- `RH_OUT:BeamFinish` (1 member(s)): Text "Text"
- `RH_OUT:BeamSheetName` (2 member(s)): ?, Text "Text"
- `RH_OUT:BeamMomentBoolean` (1 member(s)): ?
- `RH_OUT:PlanLine` (1 member(s)): Curve "Curve"
- `RH_OUT:PlanCrv` (1 member(s)): Curve "Curve"
- `RH_OUT:MomentPnt` (1 member(s)): Point "Point"
- `RH_OUT:MomentCnt` (1 member(s)): Integer "Integer"
- `RH_OUT:BeamMomentCnt` (1 member(s)): Integer "Integer"
- `RH_OUT:MomentRect` (1 member(s)): Rectangle "Rectangle"
- `RH_OUT:MomentWidth` (1 member(s)): Number "Number"
- `RH_OUT:MomentLength` (1 member(s)): Number "Number"
- `RH_OUT:MomentThickness` (1 member(s)): Number "Number"
- `RH_OUT:MomentSheetName` (2 member(s)): ?, Text "Text"
- `RH_OUT:MomentArea` (1 member(s)): Number "Number"
- `RH_OUT:MomentType` (1 member(s)): Text "Text"
- `RH_OUT:MomentFinish` (2 member(s)): ?, Text "Text"
- `RH_OUT:AngleGeo` (2 member(s)): ?, Geometry "Geometry"
- `RH_OUT:AngleLength` (1 member(s)): Number "Number"
- `RH_OUT:AngleCnt` (1 member(s)): Integer "Integer"
- `RH_OUT:BeamSheetTitle` (1 member(s)): ?
- `RH_OUT:BeamElementID` (3 member(s)): ?, Text "Text", ?
- `RH_OUT:PlanDebug` (1 member(s)): Text "Text"
- `RH_OUT:PlanSheetCurve` (1 member(s)): Curve "Curve"
- `RH_OUT:PlanText` (1 member(s)): Text Entity "Text Entity"
- `RH_OUT:MiscBeamCrv` (2 member(s)): ?, Curve "Curve"
- `RH_OUT:PlanColumnClosed` (1 member(s)): Curve "Curve"
- `RH_OUT:PlanColumnOpen` (1 member(s)): Curve "Curve"
- `RH_OUT:MiscScatteredText` (1 member(s)): Geometry "Geo"
- `RH_OUT:CheckCurves` (2 member(s)): ?, Data "Data"
- `RH_OUT:BeamFabBoltCnt` (2 member(s)): ?, Integer "Integer"
- `RH_OUT:BeamFieldBoltCnt` (2 member(s)): ?, Integer "Integer"
- `RH_OUT:RemainingPlanText` (1 member(s)): Text Entity "Text Entity"

## MAIN_ / cluster-like named objects
- `MAIN_PlanPurging` (type=MAIN_PlanPurging, is_cluster_component=True)
- `MAIN_FilterBeamText` (type=MAIN_FilterBeamText, is_cluster_component=True)
- `MAIN_BeamProcessing&Selection` (type=MAIN_BeamProcessing&Selection, is_cluster_component=True)
- `MAIN_BeamsMomentConnection` (type=MAIN_BeamsMomentConnection, is_cluster_component=True)

## Cluster components found: 6
- nickname=`BeamsSheetTitle` guid=`03ca8752-373d-44f2-b5b6-e65eab13bb02`
- nickname=`BeamConnections` guid=`8c1a528d-d3fe-47e2-b853-79cdf237a646`
- nickname=`MAIN_PlanPurging` guid=`63c97194-c404-456d-a93d-f4a3e5bcb84a`
- nickname=`MAIN_FilterBeamText` guid=`acf0a406-b136-44ae-9cac-0d5357f20a5e`
- nickname=`MAIN_BeamProcessing&Selection` guid=`b3f293fd-c9cd-4ec9-98e6-0c1ad6f48258`
- nickname=`MAIN_BeamsMomentConnection` guid=`c4de5144-4bf6-414e-af14-d2bf09ff5817`

## Script components found: 10
### `C# Script` (csharp)
- base64-encoded in archive: True
- decoded length: 3437 chars
- keyword hits: ['File3dm', 'FromByteArray', 'i3dmBase64', 'archive.Objects', 'GeometryBase', 'Rhino.Compute']
```
// Grasshopper Script Instance
#region Usings
using System;
using System.IO;
using System.Linq;
using System.Collections;
using System.Collections.Generic;
using System.Drawing;

using Rhino;
using Rhino.Geometry;
using Rhino.FileIO;

using Grasshopper;
using Grasshopper.Kernel;
using Grasshopper.Kernel.Data;
using Grasshopper.Kernel.Types;
#endregion

public class Script_Instance : GH_ScriptInstance
{
    #region Notes
    /* 
      Members:
        RhinoDoc RhinoDocument
        GH_Document GrasshopperDocument
        IGH_Component Component
        int Iteration

      Methods (Virtual & overridable):
        Print(string text)
        Print(string format, params object[] args)
        Reflect(object obj)
        Reflect(object obj, string method_name)

      Wiring:
        x  <- i3dmBase64 (base64 .3dm from Rhino.Compute REST)
        y  <- unused
        a  -> RH_OUT:i3dmContents (List<GeometryBase>)
    */
    #endregion

    private void RunScript(object x, ref object a)
    {
        a = null;

        try
        {
            string data = CoerceBase64String(x);
            if (string.IsNullOrWhiteSpace(data))
            {
                Print("ERR: empty i3dmBase64 on input x");
                return;
            }

            string clean = data.Trim();
            if (clean.Length >= 2 && clean[0] == '"' && clean[clean.Length - 1] == '"')
                clean = clean.Substring(1, clean.Length - 2);

            byte[] bytes = Convert.FromBase64String(clean);
            Print("decoded bytes: {0}"
```
### `ControlPointsCount` (python)
- base64-encoded in archive: True
- decoded length: 562 chars
- keyword hits: none
```
import Rhino.Geometry as rg

# Inputs:
# x : Curve (closed, planar)

a = False  # Default output

if x and x.IsClosed:
    # Try to convert curve into a polyline
    success, poly = x.TryGetPolyline()
    if success:
        # Polyline points can be accessed like a list
        pts = list(poly)  # Convert to Python list

        # Remove duplicate last point (polyline is closed)
        if pts[0].DistanceTo(pts[-1]) < 1e-6:
            pts = pts[:-1]

        # Check if exactly 3 vertices
        if len(pts) == 3:
            a = True

```
### `grasshopper\data\aisc_section_catalog.json` (python)
- base64-encoded in archive: True
- decoded length: 6381 chars
- keyword hits: ['Rhino.Compute']
```
"""
Grasshopper Python 3 — AISC section lookup (height, width, weight).

Wire this script into a GhPython component (Rhino 8+ / Python 3).

Inputs (add in component, type hints optional):
  name    Item or List — section label, e.g. W12X50, HSS14X6X1_2, Pipe6STD
  catalog Item — EITHER:
      • full path to aisc_section_catalog.json (use a File Path component), OR
      • the JSON text from a Read File component (recommended on Rhino.Compute)

Outputs:
  height   depth / overall height (in)
  width    flange width, leg width, or outer diameter (in); round sections use OD for both
  weight   weight (lb/ft)
  warning  empty when found; otherwise a short lookup message

Wiring (recommended):
  File Path → Read File → catalog
  beam types (list)     → name

Do NOT wire beam names into catalog — that produces:
  "invalid catalog JSON: Extra data: line 1 column 3 (char 2)"
"""

import json
import re

_CATALOG_CACHE = {}
_BEAM_LIKE_RE = re.compile(r"^[A-Z]{0,4}\d+X[\d_./-]+$", re.IGNORECASE)
# Keep in sync with backend/integrations/steel/section_catalog.py normalize_designation().
_MIXED_NUMBER_SLASH_RE = re.compile(r"(\d+)\s*-\s*(\d+)/(\d+)")
_MIXED_NUMBER_SPACE_RE = re.compile(r"(\d+)\s+(\d+)/(\d+)")
_MIXED_NUMBER_HYPHEN_UNDERSCORE_RE = re.compile(r"(\d+)-(\d+)_(\d+)")


def _normalize_designation(raw):
    text = (raw or "").strip().upper()
    text = _MIXED_NUMBER_SLASH_RE.sub(r"\1_\2_\3", text)
    text = _MIXED_NUMBER_SPACE_RE.sub(r"\1_\2_\3", text)
    text = re.sub(r"\s+", "", text)
    if text.startswith("PIPE"):
        text = "P
```
### `Py3` (python)
- base64-encoded in archive: True
- decoded length: 217 chars
- keyword hits: none
```
lookup = {
    8:  2,
    10: 2,
    12: 3,
    14: 4,
    16: 4,
    18: 5,
    21: 6,
    24: 7,
    27: 8,
    30: 9,
    33: 10,
    36: 11,
    40: 12,
    44: 13,
}

a = lookup.get(int(x), None)
```
### `Py3` (python)
- base64-encoded in archive: True
- decoded length: 162 chars
- keyword hits: none
```
import re

# x = input text (e.g. "W8x10")

match = re.search(r'[A-Za-z]+(\d+(?:\.\d+)?)', x)

if match:
    a = float(match.group(1))
else:
    a = None
```
### `Py3` (python)
- base64-encoded in archive: True
- decoded length: 1062 chars
- keyword hits: none
```
import math
 
def fraction_feet_inches(feet):
    total_inches = feet * 12
 
    # Round to nearest 1/16"
    sixteenths = int(round(total_inches * 16))
 
    total_inches = sixteenths / 16.0
 
    # Separate feet and inches
    whole_feet = int(total_inches // 12)
    remaining_sixteenths = sixteenths - (whole_feet * 12 * 16)
 
    whole_inches = remaining_sixteenths // 16
    remainder = remaining_sixteenths % 16
 
    # No fraction
    if remainder == 0:
        return str(whole_feet) + "'-" + str(whole_inches) + '"'
 
    # Simplify fraction
    g = math.gcd(remainder, 16)
    num = remainder // g
    den = 16 // g
 
    # Feet + fractional inches
    if whole_inches == 0:
        inch_string = str(num) + "/" + str(den)
    else:
        inch_string = str(whole_inches) + " " + str(num) + "/" + str(den)
 
    return str(whole_feet) + "'-" + inch_string + '"'
 
 
# Handle single value or list
if isinstance(D, (list, tuple)):
    A = [fraction_feet_inches(x) for x in D]
else:
    A = fraction_feet_inches(D)
```
### `Py3` (python)
- base64-encoded in archive: True
- decoded length: 663 chars
- keyword hits: none
```
import math
 
def fraction_inch(feet):
    inches = feet * 12
 
    # Round to nearest 1/16"
    sixteenths = int(round(inches * 16))
 
    whole = sixteenths // 16
    remainder = sixteenths % 16
 
    if remainder == 0:
        return str(whole) + '"'
 
    # Simplify fraction
    g = math.gcd(remainder, 16)
    num = remainder // g
    den = 16 // g
 
    if whole == 0:
        return str(num) + "/" + str(den) + '"'
    else:
        return str(whole) + " " + str(num) + "/" + str(den) + '"'
 
 
# Handle single value or list
if isinstance(D, (list, tuple)):
    A = [fraction_inch(x) for x in D]
else:
    A = fraction_inch(D)
```
### `Py3` (python)
- base64-encoded in archive: True
- decoded length: 663 chars
- keyword hits: none
```
import math
 
def fraction_inch(feet):
    inches = feet * 12
 
    # Round to nearest 1/16"
    sixteenths = int(round(inches * 16))
 
    whole = sixteenths // 16
    remainder = sixteenths % 16
 
    if remainder == 0:
        return str(whole) + '"'
 
    # Simplify fraction
    g = math.gcd(remainder, 16)
    num = remainder // g
    den = 16 // g
 
    if whole == 0:
        return str(num) + "/" + str(den) + '"'
    else:
        return str(whole) + " " + str(num) + "/" + str(den) + '"'
 
 
# Handle single value or list
if isinstance(D, (list, tuple)):
    A = [fraction_inch(x) for x in D]
else:
    A = fraction_inch(D)
```
### `grasshopper\data\aisc_section_catalog.json` (python)
- base64-encoded in archive: True
- decoded length: 13503 chars
- keyword hits: ['Rhino.Compute']
```
"""
Grasshopper Python 3 — AISC section lookup (height, width, weight, thicknesses).

Wire this script into a GhPython component (Rhino 8+ / Python 3).

Inputs (add in component, type hints optional):
  name    Item or List — section label, e.g. W12X50, HSS14X6X1_2, Pipe6STD
  catalog Item — EITHER:
      • full path to aisc_section_catalog.json (use a File Path component), OR
      • the JSON text from a Read File component (recommended on Rhino.Compute)

Outputs:
  height                  depth / overall height (in)
  width                   flange width, leg width, or outer diameter (in); round sections use OD for both
  weight                  weight (lb/ft)
  flange_thickness        tf for I-shapes; wall thickness for HSS/Pipe; leg thickness for L-shapes (in)
  web_thickness           tw for I-shapes; wall thickness for HSS/Pipe; leg thickness for L-shapes (in)
  centroid_to_web_face    tw/2 for I-shapes; B/2 for HSS rectangular; OD/2 for HSS round/Pipe; leg_t/2 for L-shapes (in)
  warning                 empty when found; otherwise a short lookup message

Wiring (recommended):
  File Path → Read File → catalog
  beam types (list)     → name

Do NOT wire beam names into catalog — that produces:
  "invalid catalog JSON: Extra data: line 1 column 3 (char 2)"
"""

import json
import re

_CATALOG_CACHE = {}
_BEAM_LIKE_RE = re.compile(r"^[A-Z]{0,4}\d+X[\d_./-]+$", re.IGNORECASE)

# Keep in sync with backend/integrations/steel/section_catalog.py normalize_designation().
_MIXED_NUMBER_SLASH_RE = re.compile(r"(\d+)\s*-\s*(\d+)/(\d+)")
_MIXED
```
### `grasshopper\data\aisc_section_catalog.json` (python)
- base64-encoded in archive: True
- decoded length: 13503 chars
- keyword hits: ['Rhino.Compute']
```
"""
Grasshopper Python 3 — AISC section lookup (height, width, weight, thicknesses).

Wire this script into a GhPython component (Rhino 8+ / Python 3).

Inputs (add in component, type hints optional):
  name    Item or List — section label, e.g. W12X50, HSS14X6X1_2, Pipe6STD
  catalog Item — EITHER:
      • full path to aisc_section_catalog.json (use a File Path component), OR
      • the JSON text from a Read File component (recommended on Rhino.Compute)

Outputs:
  height                  depth / overall height (in)
  width                   flange width, leg width, or outer diameter (in); round sections use OD for both
  weight                  weight (lb/ft)
  flange_thickness        tf for I-shapes; wall thickness for HSS/Pipe; leg thickness for L-shapes (in)
  web_thickness           tw for I-shapes; wall thickness for HSS/Pipe; leg thickness for L-shapes (in)
  centroid_to_web_face    tw/2 for I-shapes; B/2 for HSS rectangular; OD/2 for HSS round/Pipe; leg_t/2 for L-shapes (in)
  warning                 empty when found; otherwise a short lookup message

Wiring (recommended):
  File Path → Read File → catalog
  beam types (list)     → name

Do NOT wire beam names into catalog — that produces:
  "invalid catalog JSON: Extra data: line 1 column 3 (char 2)"
"""

import json
import re

_CATALOG_CACHE = {}
_BEAM_LIKE_RE = re.compile(r"^[A-Z]{0,4}\d+X[\d_./-]+$", re.IGNORECASE)

# Keep in sync with backend/integrations/steel/section_catalog.py normalize_designation().
_MIXED_NUMBER_SLASH_RE = re.compile(r"(\d+)\s*-\s*(\d+)/(\d+)")
_MIXED
```

## Embedded base64 blob scan (candidate cluster/nested-doc payloads)
- total blob candidates (>=600 base64 chars) found in raw file: 17
- inspected in detail: 17
- offset 165708: raw_len=864, base64_ok=True, zlib_ok=False, decompressed_len=0, sample_strings=[]
- offset 224757: raw_len=864, base64_ok=True, zlib_ok=False, decompressed_len=0, sample_strings=[]
- offset 368689: raw_len=4588, base64_ok=True, zlib_ok=False, decompressed_len=0, sample_strings=[]
- offset 434403: raw_len=22308, base64_ok=True, zlib_ok=True, decompressed_len=55330, sample_strings=['Match Text', 'Match a text against a pattern', 'Match Text', 'Text to match', '1True if the text adheres to all supplied patterns', 'Point In Curve', '*Test a point for closed curve containment.', 'Point In Curve']
- offset 510367: raw_len=752, base64_ok=True, zlib_ok=False, decompressed_len=0, sample_strings=[]
- offset 735399: raw_len=126356, base64_ok=True, zlib_ok=True, decompressed_len=144077, sample_strings=['S-BeamCrv', 'S-BeamCrv', 'S-BeamCrv', 'S-BeamCrv', 'S-BeamCrv', 'S-Beam', 'S-Beam', 'S-Beam']
- offset 918968: raw_len=8556, base64_ok=True, zlib_ok=False, decompressed_len=0, sample_strings=[]
- offset 1143035: raw_len=265104, base64_ok=True, zlib_ok=True, decompressed_len=249065, sample_strings=['Sorted Text to Bake', 'Cluster', 'ClusterDocument', ',Contains a cluster of Grasshopper components', 'Cluster', 'WColumnCurvesExraction', 'Curves to join', 'Curves']
- offset 1446364: raw_len=36844, base64_ok=True, zlib_ok=True, decompressed_len=112337, sample_strings=['Match Text', 'Match a text against a pattern', 'Match Text', 'Text to match', '1True if the text adheres to all supplied patterns', '(A panel for custom notes and text values', 'UserText', 'Text Split']
- offset 1500852: raw_len=375488, base64_ok=True, zlib_ok=True, decompressed_len=1248625, sample_strings=['$IFS_UI_Beam_v34.0_CurvesExtension.gh', 'Main (straight + curved)', '*find intersections with non parallel beams', 'CurvedBeams', 'NonSpecifiedBeams', '"Concatenate some fragments of text', 'First text fragment', 'Second text fragment']
- offset 2090843: raw_len=83872, base64_ok=True, zlib_ok=True, decompressed_len=272945, sample_strings=['Moments Without Columns', "'Find appropriate intersection with beam", 'Moments with column', '=sub tree structure {A;B} per moment {B} under parent beam {A}', ',ChecksIfBeamEndpoints&MomentAreSameDirection', '"ChangeDimensionsOFMomentConnection', 'moment curves', 'Length of rectangle curve']
- offset 2223284: raw_len=1416, base64_ok=True, zlib_ok=False, decompressed_len=0, sample_strings=[]
- offset 2236886: raw_len=884, base64_ok=True, zlib_ok=False, decompressed_len=0, sample_strings=[]
- offset 2337653: raw_len=884, base64_ok=True, zlib_ok=False, decompressed_len=0, sample_strings=[]
- offset 6657023: raw_len=18052, base64_ok=True, zlib_ok=False, decompressed_len=0, sample_strings=[]

## Component type histogram (top-level)
- Group: 100
- Panel: 31
- Text: 15
- Number: 13
- Curve: 11
- Geometry: 10
- Data: 9
- Python 3 Script: 9
- List Item: 7
- Text Entity: 6
- Integer: 6
- Stream Filter: 6
- Number Slider: 5
- Scribble: 5
- Cull Pattern: 4
- Member Index: 4
- Clean Tree: 4
- Null Item: 3
- Colour Swatch: 3
- Get String: 3
- Merge: 3
- Multiplication: 3
- Replace Nulls: 3
- Filter Content: 2
- Equality Filter: 2
- Value List Object Type: 2
- Line: 2
- File Path: 2
- Custom Preview Lineweights: 2
- Cluster: 2
- Point: 2
- List Length: 2
- Concatenate: 2
- Relay: 2
- Area: 2
- Bounding Box: 2
- Get Geometry: 2
- Content Information: 1
- Smaller Than: 1
- Custom Preview: 1

## Limitations of this static audit (be precise about what this does and doesn't prove)

- **No Rhino/Grasshopper install exists in this environment.** This audit could not run the definition (Options A/C from the brief). Everything above is Option B: static XML parsing plus best-effort base64/zlib recovery. Nothing here should be treated as proof of *runtime* behavior (actual data-tree shapes, actual counts on a real project, actual coordinate values) -- only of what the definition's static structure and embedded source code say.
- **Nested Cluster documents are not fully deserialized.** The zlib-decompressed cluster payloads (e.g. the 1.24MB blob containing `IFS_UI_Beam_v34.0_CurvesExtension.gh`-derived content, and the 273KB blob containing the moment-connection logic) are still in GH_IO's *binary* chunk format internally -- this audit only extracted printable ASCII string runs from them, not their component graph or wiring. The strings found (`CurvedBeams`, `NonSpecifiedBeams`, `find intersections with non parallel beams`, `Moments Without Columns`, `ChecksIfBeamEndpoints&MomentAreSameDirection`, etc.) are strong corroborating evidence for the operations the audit brief described, but the *exact* algorithm, parameter thresholds, and output wiring inside each cluster remain unknown.
- **Some RH_OUT group members could not be classified** (shown as `?` in the RH_OUT contract list above) -- these are almost certainly bare `Param_*` objects (a generic Grasshopper parameter, not a component), which store their fields under a different chunk shape than the `Container`-based one this parser targets. A full audit would extend the parser to also handle `IGH_Param`-shaped objects; not done this session as it doesn't change any decision below.
- **Script Text field decoding covers all 10 top-level scripts found**, including the full C# Rhino.Compute bridge and two variants of the AISC catalog lookup script (an older 3-field version returning height/width/weight, and a newer 6-field version adding flange_thickness/web_thickness/centroid_to_web_face) -- both fully recovered and readable in the Scripts section above.

## Grasshopper reuse decision

| Cluster / capability | Reuse decision | Why |
|---|---|---|
| `MAIN_PlanPurging` (curve/text classification: beams vs. columns vs. grid lines vs. moment curves vs. unidentified) | **Reuse as evidence, once runnable.** This is exactly the "distinguish structural member geometry from unrelated lines" capability Section 8 of the original research brief flagged as hard to build well from scratch. Do not reimplement grid-line/dimension-line filtering independently before this cluster has been tried. | Confirmed as a real, non-trivial cluster (not a stub); internal strings corroborate genuine grid/reference-line filtering and HSS/W column discrimination logic. |
| `MAIN_FilterBeamText` (text<->geometry candidate prep: bounding box, centroid, member index) | **Reuse as evidence.** | Same reasoning -- this is groundwork for exactly the association problem `association.py` solves; better to feed it as an additional evidence channel later than duplicate it. |
| `MAIN_BeamProcessing&Selection` (the actual text<->curve matching engine) | **Reuse as evidence via the `GrasshopperGeometryEvidenceProvider` fixture contract built this session -- do NOT treat its output as authoritative,** and do not attempt to reimplement `MatchingTexttoCurve`/`ClassifyTextOrientation` independently. | This is the single most sophisticated piece of existing text<->geometry logic found anywhere in this project (across both this repo and the shadow `ml_association`/`label_reconstruction` work). Rebuilding it would be pure duplication. But its pairing contract is unproven (see Finding 4) -- hence "evidence," never "ground truth." |
| `MAIN_BeamsMomentConnection` | **Not reused this session** -- out of scope (downstream of the label<->geometry problem this brief is solving; Section 2.4 already flagged it as such). Available as a future evidence channel if moment-connection geometry ever becomes relevant upstream. | Avoids scope creep into the takeoff/connection-design problem, which is explicitly the other team's responsibility. |
| AISC catalog lookup scripts | **Not reused as code** (they duplicate, in Python-for-Grasshopper form, logic that already exists in `backend/services/normalization.py` / `label_reconstruction/structural_parser.py`). **Reused as a cross-check**: the newer 6-field script's field semantics (flange_thickness/web_thickness/centroid_to_web_face defined per-family) is useful corroborating evidence for how thickness fields should be typed in `structural_parser.py`. | Two independent catalog-normalization implementations already diverge (Finding 5) -- adding a third would make it worse, not better. |
| C# Rhino.Compute bridge (`i3dmBase64 -> GeometryBase`) | **Not reused as code this session** (no live Rhino.Compute endpoint exists to call it against -- see below), but its exact input/output contract is now fully documented and should be the template when a real Compute client is eventually built. | Nothing to wrap yet; building a client without a live endpoint to test against would be speculative. |

## Rhino.Compute integration: confirmed absent elsewhere in the codebase

A repository-wide search (this session, via the `Grep` tool, across `backend/`, `frontend/src/`, and `docs/` in both the main repo and every sibling worktree) for `rhino`, `grasshopper`, `.ghx`, `compute.rhino3d`, `i3dmBase64`, `RH_OUT`, `File3dm`, `EvaluateDefinition`, and `estima3d_web_plan` found exactly three files, and none of them are an integration:

- `backend/services/engineering/geometry_adapters.py` -- a `DeferredCadAdapter("3dm", (".3dm",), "rhino3dm")` capability *stub* (raises/reports "not yet available"; contains no Rhino.Compute call, no GHX execution, no base64 handling).
- `backend/app.py` -- a feature-flag string literally named `"geometry_adapters_pdf_rhino_dwg_dxf"` (just a label).
- One training artifact JSON containing the word "rhino" incidentally in unrelated text.

**Conclusion: there is nothing to reuse for actually executing this GHX.** `GrasshopperGeometryEvidenceProvider` (Section K below / `geometry_evidence.py`) was therefore built as a pure adapter over an already-captured result payload, with no live-call implementation -- exactly per Section 32/33's fallback instruction ("if unavailable, do NOT block; implement the adapter interface and document runtime validation as pending").
