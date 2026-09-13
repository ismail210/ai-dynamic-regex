"""Read-only static forensic audit of a Grasshopper .ghx definition.

This is a research/audit tool, not a Rhino.Compute client. It never opens the
GHX in Rhino/Grasshopper and never writes to the source file. It parses the
GH_IO XML export format directly to recover:

- the top-level object inventory (component type name + nickname + instance
  guid for every object under DefinitionObjects)
- the RH_OUT:* contract (which objects are named as Rhino.Compute outputs)
- script components (Python/C#) and their embedded source, decoded from
  base64 where the archive stores it that way
- large embedded base64 blobs (e.g. nested Cluster documents), with a
  best-effort zlib/deflate decompression + printable-string extraction pass
  when full GH_IO deserialization isn't available (no Rhino/Grasshopper
  install in this environment)

Usage:
    python backend/scripts/ghx_static_audit.py <path-to-.ghx> \
        --out-manifest docs/ghx_semantic_manifest.json \
        --out-report docs/ghx_geometry_audit.md
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import re
import zlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


RH_OUT_RE = re.compile(r"RH_OUT:[A-Za-z0-9_]+")
BASE64_BLOB_RE = re.compile(rb"[A-Za-z0-9+/]{600,}={0,2}")
PRINTABLE_RUN_RE = re.compile(rb"[ -~]{5,}")

INTERESTING_SCRIPT_KEYWORDS = [
    "File3dm",
    "FromByteArray",
    "i3dmBase64",
    "archive.Objects",
    "GeometryBase",
    "Rhino.Compute",
    "compute.rhino3d",
]

CLUSTER_STRING_KEYWORDS = [
    "MAIN_", "RH_OUT", "Beam", "Curve", "Column", "Moment", "AISC",
    "Text", "Cluster", "Catalog", "GridLine", "Highlight", "Offset",
]


@dataclass
class GhxObject:
    order_index: int
    type_name: Optional[str]
    nickname: Optional[str]
    description: Optional[str]
    instance_guid: Optional[str]
    is_script: bool = False
    is_cluster: bool = False
    is_rh_out: bool = False
    is_group: bool = False
    group_member_guids: list = field(default_factory=list)


@dataclass
class ScriptFinding:
    order_index: int
    nickname: Optional[str]
    language_hint: str
    was_base64: bool
    length_chars: int
    keyword_hits: list = field(default_factory=list)
    snippet: str = ""


@dataclass
class BlobFinding:
    byte_offset: int
    raw_length: int
    decoded: bool
    decompressed: bool
    decompressed_length: int
    sample_strings: list = field(default_factory=list)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_parent_map(root: ET.Element) -> dict:
    parent_map = {}
    for parent in root.iter():
        for child in parent:
            parent_map[child] = parent
    return parent_map


def first_item_text(container: ET.Element, name: str, direct_items_only: bool = False) -> Optional[str]:
    """Return the text of the first <item name="..."> found.

    If direct_items_only, only look at an immediate <items> child (not the
    whole subtree) -- used to read a chunk's own scalar fields without
    picking up a nested parameter's field of the same name.
    """
    if direct_items_only:
        items_el = container.find("items")
        if items_el is None:
            return None
        for item in items_el.findall("item"):
            if item.get("name") == name:
                return (item.text or "").strip()
        return None
    for item in container.iter("item"):
        if item.get("name") == name:
            return (item.text or "").strip()
    return None


def find_definition_objects(root: ET.Element) -> list[ET.Element]:
    """Find the DefinitionObjects chunk and return its direct Object chunks."""
    for chunk in root.iter("chunk"):
        if chunk.get("name") == "DefinitionObjects":
            chunks_el = chunk.find("chunks")
            if chunks_el is None:
                continue
            return [c for c in chunks_el.findall("chunk") if c.get("name") == "Object"]
    return []


def extract_objects(object_chunks: list[ET.Element]) -> list[GhxObject]:
    objects = []
    for idx, obj_chunk in enumerate(object_chunks):
        type_name = first_item_text(obj_chunk, "Name", direct_items_only=True)
        # Container holds the instance-level fields (nickname, guid, description)
        container = None
        chunks_el = obj_chunk.find("chunks")
        if chunks_el is not None:
            for c in chunks_el.findall("chunk"):
                if c.get("name") == "Container":
                    container = c
                    break
        nickname = first_item_text(container, "NickName", direct_items_only=True) if container is not None else None
        description = first_item_text(container, "Description", direct_items_only=True) if container is not None else None
        instance_guid = first_item_text(container, "InstanceGuid", direct_items_only=True) if container is not None else None

        # A Cluster is identified by carrying an embedded ClusterDocument payload,
        # not by its Name field -- a cluster's Name is the user's custom cluster
        # name (e.g. "MAIN_PlanPurging"), not the literal string "Cluster".
        has_cluster_document = False
        is_group = bool(type_name and type_name.strip() == "Group")
        group_member_guids: list = []
        if container is not None:
            items_el = container.find("items")
            if items_el is not None:
                for item in items_el.findall("item"):
                    if item.get("name") == "ClusterDocument":
                        has_cluster_document = True
                    if is_group and item.get("name") == "ID" and item.get("type_name") == "gh_guid":
                        text = (item.text or "").strip()
                        if text:
                            group_member_guids.append(text)

        is_script = bool(type_name and ("Script" in type_name or "Python" in type_name or "C#" in type_name))
        is_cluster = has_cluster_document
        is_rh_out = bool(nickname and nickname.startswith("RH_OUT:"))

        objects.append(GhxObject(
            order_index=idx,
            type_name=type_name,
            nickname=nickname,
            description=description,
            instance_guid=instance_guid,
            is_script=is_script,
            is_cluster=is_cluster,
            is_rh_out=is_rh_out,
            is_group=is_group,
            group_member_guids=group_member_guids,
        ))
    return objects


def _is_probably_base64(text: str) -> bool:
    if len(text) < 40:
        return False
    sample = text[:2000]
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=\r\n \t")
    return all(ch in allowed for ch in sample)


def extract_scripts(object_chunks: list[ET.Element], objects: list[GhxObject]) -> list[ScriptFinding]:
    findings = []
    for idx, obj_chunk in enumerate(object_chunks):
        meta = objects[idx]
        if not meta.is_script:
            continue
        language_hint = "python" if meta.type_name and "Python" in meta.type_name else (
            "csharp" if meta.type_name and "C#" in meta.type_name else "unknown"
        )
        best_text = None
        best_len = 0
        title = None
        for item in obj_chunk.iter("item"):
            name = item.get("name") or ""
            if name == "Title" and item.get("type_name") == "gh_string":
                title = (item.text or "").strip() or title
            if name not in ("Text", "Source", "Code", "ScriptSource", "SourceCode", "m_source"):
                continue
            if item.get("type_name") != "gh_string":
                continue
            text = (item.text or "").strip()
            if len(text) > best_len:
                best_text = text
                best_len = len(text)
        if title:
            meta.description = meta.description or title
        if not best_text:
            findings.append(ScriptFinding(
                order_index=idx, nickname=meta.nickname, language_hint=language_hint,
                was_base64=False, length_chars=0, snippet="<no source text field found>",
            ))
            continue

        was_base64 = False
        decoded_text = best_text
        if _is_probably_base64(best_text):
            try:
                raw = base64.b64decode(best_text, validate=False)
                candidate = raw.decode("utf-8", errors="ignore")
                if candidate.strip():
                    decoded_text = candidate
                    was_base64 = True
            except (binascii.Error, ValueError):
                pass

        hits = [kw for kw in INTERESTING_SCRIPT_KEYWORDS if kw.lower() in decoded_text.lower()]
        findings.append(ScriptFinding(
            order_index=idx,
            nickname=meta.nickname,
            language_hint=language_hint,
            was_base64=was_base64,
            length_chars=len(decoded_text),
            keyword_hits=hits,
            snippet=decoded_text[:1600],
        ))
    return findings


def scan_large_base64_blobs(raw_bytes: bytes, max_blobs: int = 40) -> tuple[list[BlobFinding], int]:
    findings = []
    count = 0
    for m in BASE64_BLOB_RE.finditer(raw_bytes):
        count += 1
        if len(findings) >= max_blobs:
            continue
        blob = m.group(0)
        decoded = False
        decompressed = False
        decompressed_len = 0
        sample_strings = []
        try:
            raw = base64.b64decode(blob, validate=False)
            decoded = True
        except (binascii.Error, ValueError):
            raw = b""
        if decoded:
            for wbits in (15, -15, 31):
                try:
                    out = zlib.decompress(raw, wbits)
                    decompressed = True
                    decompressed_len = len(out)
                    strings_found = PRINTABLE_RUN_RE.findall(out)
                    seen = []
                    for s in strings_found:
                        s_txt = s.decode("ascii", errors="ignore")
                        if any(kw.lower() in s_txt.lower() for kw in CLUSTER_STRING_KEYWORDS):
                            seen.append(s_txt)
                        if len(seen) >= 25:
                            break
                    sample_strings = seen
                    break
                except zlib.error:
                    continue
        findings.append(BlobFinding(
            byte_offset=m.start(),
            raw_length=len(blob),
            decoded=decoded,
            decompressed=decompressed,
            decompressed_length=decompressed_len,
            sample_strings=sample_strings,
        ))
    return findings, count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ghx_path", type=Path)
    parser.add_argument("--out-manifest", type=Path, default=None)
    parser.add_argument("--out-report", type=Path, default=None)
    args = parser.parse_args()

    ghx_path: Path = args.ghx_path
    if not ghx_path.exists():
        raise SystemExit(f"GHX not found: {ghx_path}")

    file_size = ghx_path.stat().st_size
    digest = sha256_of(ghx_path)
    raw_bytes = ghx_path.read_bytes()

    tree = ET.parse(ghx_path)
    root = tree.getroot()

    object_chunks = find_definition_objects(root)
    objects = extract_objects(object_chunks)

    rh_out_objects = [o for o in objects if o.is_rh_out]
    script_objects = [o for o in objects if o.is_script]
    cluster_objects = [o for o in objects if o.is_cluster]
    main_named = [o for o in objects if o.nickname and o.nickname.startswith("MAIN_")]

    guid_index = {o.instance_guid: o for o in objects if o.instance_guid}

    def resolve_group_members(group_obj: GhxObject) -> list[dict]:
        resolved = []
        for guid in group_obj.group_member_guids:
            member = guid_index.get(guid)
            if member is not None:
                resolved.append({
                    "instance_guid": guid,
                    "type_name": member.type_name,
                    "nickname": member.nickname,
                    "is_script": member.is_script,
                    "is_cluster": member.is_cluster,
                })
            else:
                resolved.append({"instance_guid": guid, "type_name": None, "nickname": None, "unresolved": True})
        return resolved

    rh_out_resolved = [
        {
            "nickname": o.nickname,
            "instance_guid": o.instance_guid,
            "member_count": len(o.group_member_guids),
            "members": resolve_group_members(o),
        }
        for o in rh_out_objects
    ]

    script_findings = extract_scripts(object_chunks, objects)
    blob_findings, total_blob_count = scan_large_base64_blobs(raw_bytes)

    all_nicknames_raw = sorted({o.nickname for o in objects if o.nickname})

    manifest = {
        "definition": {
            "path": str(ghx_path),
            "sha256": digest,
            "file_size_bytes": file_size,
            "top_level_object_count": len(objects),
        },
        "rh_out_contract": rh_out_resolved,
        "main_clusters_or_groups": [
            {
                "nickname": o.nickname,
                "type_name": o.type_name,
                "instance_guid": o.instance_guid,
                "is_cluster_component": o.is_cluster,
            }
            for o in main_named
        ],
        "cluster_components": [
            {"nickname": o.nickname, "instance_guid": o.instance_guid}
            for o in cluster_objects
        ],
        "scripts": [
            {
                "order_index": s.order_index,
                "nickname": s.nickname,
                "language_hint": s.language_hint,
                "was_base64_encoded": s.was_base64,
                "length_chars": s.length_chars,
                "keyword_hits": s.keyword_hits,
                "snippet": s.snippet,
            }
            for s in script_findings
        ],
        "embedded_base64_blob_scan": {
            "total_blob_candidates_found": total_blob_count,
            "inspected": [
                {
                    "byte_offset": b.byte_offset,
                    "raw_length": b.raw_length,
                    "base64_decoded_ok": b.decoded,
                    "zlib_decompressed_ok": b.decompressed,
                    "decompressed_length": b.decompressed_length,
                    "sample_strings": b.sample_strings,
                }
                for b in blob_findings
            ],
        },
        "type_name_histogram": _histogram([o.type_name for o in objects if o.type_name]),
        "all_nicknames": all_nicknames_raw,
    }

    if args.out_manifest:
        args.out_manifest.parent.mkdir(parents=True, exist_ok=True)
        args.out_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Wrote manifest: {args.out_manifest}")

    if args.out_report:
        report = _render_report(manifest, ghx_path, script_findings)
        args.out_report.parent.mkdir(parents=True, exist_ok=True)
        args.out_report.write_text(report, encoding="utf-8")
        print(f"Wrote report: {args.out_report}")

    print(json.dumps({
        "sha256": digest,
        "file_size_bytes": file_size,
        "top_level_object_count": len(objects),
        "rh_out_count": len(rh_out_objects),
        "script_count": len(script_objects),
        "cluster_component_count": len(cluster_objects),
        "main_named_count": len(main_named),
        "base64_blob_candidates": total_blob_count,
    }, indent=2))


def _histogram(values: list[str]) -> dict:
    hist: dict = {}
    for v in values:
        hist[v] = hist.get(v, 0) + 1
    return dict(sorted(hist.items(), key=lambda kv: -kv[1]))


def _render_report(manifest: dict, ghx_path: Path, script_findings: list[ScriptFinding]) -> str:
    d = manifest["definition"]
    lines = []
    lines.append("# GHX Geometry Audit (static, read-only)\n")
    lines.append(f"- Path: `{d['path']}`")
    lines.append(f"- SHA-256: `{d['sha256']}`")
    lines.append(f"- File size: {d['file_size_bytes']:,} bytes")
    lines.append(f"- Top-level object count (DefinitionObjects): {d['top_level_object_count']}")
    lines.append("")
    lines.append("## Method")
    lines.append(
        "Static XML parse of the GH_IO archive format (no Rhino/Grasshopper install "
        "available in this environment, so OPTION A/C from the audit brief were not "
        "possible; this is OPTION B). Top-level objects were read directly from the "
        "`DefinitionObjects` chunk's own `Object` children -- type name from the "
        "object's direct `<items>`, nickname/description/instance guid from its "
        "nested `Container` chunk's direct `<items>`. Nested Cluster documents are "
        "opaque (embedded as separate encoded payloads, not literal child Object "
        "chunks), so cluster internals below are from best-effort base64/deflate "
        "recovery, not full GH_IO deserialization -- treat cluster-internal findings "
        "as indicative, not authoritative."
    )
    lines.append("")
    lines.append("## RH_OUT contract found")
    lines.append(
        f"{len(manifest['rh_out_contract'])} named Groups with a nickname starting `RH_OUT:`. "
        "Each is a GH Group annotation whose `ID`/`ID_Count` items enumerate the instance guids "
        "of the actual components it boxes -- resolved below against the full object index to "
        "identify what really produces each output:\n"
    )
    for o in manifest["rh_out_contract"]:
        member_desc = ", ".join(
            f"{m.get('type_name') or '?'}" + (f" \"{m['nickname']}\"" if m.get("nickname") else "")
            for m in o["members"]
        ) or "(no members resolved)"
        lines.append(f"- `{o['nickname']}` ({o['member_count']} member(s)): {member_desc}")
    lines.append("")
    lines.append("## MAIN_ / cluster-like named objects")
    for o in manifest["main_clusters_or_groups"]:
        lines.append(f"- `{o['nickname']}` (type={o['type_name']}, is_cluster_component={o['is_cluster_component']})")
    lines.append("")
    lines.append(f"## Cluster components found: {len(manifest['cluster_components'])}")
    for o in manifest["cluster_components"]:
        lines.append(f"- nickname=`{o['nickname']}` guid=`{o['instance_guid']}`")
    lines.append("")
    lines.append(f"## Script components found: {len(manifest['scripts'])}")
    for s in manifest["scripts"]:
        lines.append(f"### `{s['nickname']}` ({s['language_hint']})")
        lines.append(f"- base64-encoded in archive: {s['was_base64_encoded']}")
        lines.append(f"- decoded length: {s['length_chars']} chars")
        lines.append(f"- keyword hits: {s['keyword_hits'] or 'none'}")
        lines.append("```")
        lines.append(s["snippet"])
        lines.append("```")
    lines.append("")
    lines.append("## Embedded base64 blob scan (candidate cluster/nested-doc payloads)")
    blob_scan = manifest["embedded_base64_blob_scan"]
    lines.append(f"- total blob candidates (>=600 base64 chars) found in raw file: {blob_scan['total_blob_candidates_found']}")
    lines.append(f"- inspected in detail: {len(blob_scan['inspected'])}")
    for b in blob_scan["inspected"][:15]:
        lines.append(
            f"- offset {b['byte_offset']}: raw_len={b['raw_length']}, "
            f"base64_ok={b['base64_decoded_ok']}, zlib_ok={b['zlib_decompressed_ok']}, "
            f"decompressed_len={b['decompressed_length']}, "
            f"sample_strings={b['sample_strings'][:8]}"
        )
    lines.append("")
    lines.append("## Component type histogram (top-level)")
    for type_name, count in list(manifest["type_name_histogram"].items())[:40]:
        lines.append(f"- {type_name}: {count}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
