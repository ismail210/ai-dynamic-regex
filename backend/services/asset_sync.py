"""Versioned shipped assets on the data volume (containers).

The image carries ``training/`` (models, catalogs, datasets, the knowledge
base) as ``/app/training.image`` with a manifest of every file's SHA-256
(``manifest``, run at build time). The data volume's ``training/`` starts as a
copy and is then changed by the application itself (review state, learning
histories, promoted models). This module keeps the two apart:

* ``startup`` (every container start): adds shipped files the volume does
  not have yet, records what is applied (``/data/.assets/applied.json``) and
  reports updates waiting and files changed on the volume. It never replaces
  an existing file. An image whose asset format is older than the volume's
  refuses to start, with the command that resolves it.
* ``apply``: backs up every file it replaces, copies each new version to a
  temporary name, verifies its hash (and parses JSON), then swaps it in with
  an atomic rename; the applied record is written last, so an interrupted run
  is completed by running it again. Files changed on the volume are kept
  unless ``--replace-modified`` is given.
* ``rollback <backup>``: restores the files and the applied record of a backup.
* ``status``: what ``startup`` reports, without changing anything.

Display and deployment plumbing only: nothing here retrains a model or
changes how assets are read.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

# Version of the manifest / applied-record layout. Raise it when a release
# needs assets an older image cannot read; older images then refuse a volume
# that a newer one has updated, instead of misreading it.
ASSET_FORMAT = 1
MANIFEST = ".asset-manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and p.name != MANIFEST and not p.is_symlink())


def build_manifest(image_root: Path, revision: str) -> dict[str, Any]:
    files = {p.relative_to(image_root).as_posix(): {"sha256": _sha256(p), "size": p.stat().st_size}
             for p in _files(image_root)}
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:16]
    return {"format": ASSET_FORMAT, "revision": revision, "asset_version": digest, "files": files}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


class Assets:
    def __init__(self, image_root: Path, data_dir: Path) -> None:
        self.image_root = image_root
        self.live = data_dir / "training"
        self.state = data_dir / ".assets"
        self.applied_path = self.state / "applied.json"
        manifest = _read_json(image_root / MANIFEST)
        if manifest is None:
            raise SystemExit(f"asset_sync: {image_root / MANIFEST} is missing; the image was not built with "
                             "backend/Dockerfile.")
        self.manifest: dict[str, Any] = manifest

    def applied(self) -> dict[str, Any] | None:
        return _read_json(self.applied_path)

    def compatibility_error(self) -> str | None:
        applied = self.applied() or {}
        fmt = int(applied.get("format") or 0)
        if fmt > ASSET_FORMAT:
            return (f"The data volume's assets were applied by asset format {fmt} (revision "
                    f"{applied.get('revision')}), but this image reads format {ASSET_FORMAT} "
                    f"(revision {self.manifest['revision']}). Run an image of revision "
                    f"{applied.get('revision')} or newer, or restore the data backup taken before that update "
                    "(docs/DOCKER.md, 'Assets').")
        return None

    def plan(self) -> dict[str, list[str]]:
        """Each shipped file's state on the volume. ``modified``: the volume's
        copy is neither the version applied there nor this image's."""

        applied_files = (self.applied() or {}).get("files") or {}
        plan: dict[str, list[str]] = {"missing": [], "current": [], "update": [], "modified": []}
        for rel, info in self.manifest["files"].items():
            live = self.live / rel
            if not live.is_file():
                plan["missing"].append(rel)
                continue
            have = _sha256(live)
            was = (applied_files.get(rel) or {}).get("sha256")
            if have == info["sha256"]:
                plan["current"].append(rel)
            elif was is not None and have == was:
                plan["update"].append(rel)
            else:
                plan["modified"].append(rel)
        return plan

    def _record(self, plan: dict[str, list[str]], extra: dict[str, Any] | None = None) -> None:
        """The applied record: this image's entry for every file now equal to
        it, the previous entry for files left as they were."""

        previous = (self.applied() or {}).get("files") or {}
        files = {}
        for rel in plan["current"] + plan["missing"]:
            files[rel] = self.manifest["files"][rel]
        for rel in plan["update"] + plan["modified"]:
            if rel in previous:
                files[rel] = previous[rel]
        _write_json(self.applied_path, {
            "format": ASSET_FORMAT, "revision": self.manifest["revision"],
            "asset_version": self.manifest["asset_version"], "files": files,
            "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(), **(extra or {}),
        })

    def _copy_verified(self, rel: str) -> None:
        source, target = self.image_root / rel, self.live / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        staged = target.with_name(target.name + ".asset-new")
        shutil.copy2(source, staged)
        if _sha256(staged) != self.manifest["files"][rel]["sha256"]:
            staged.unlink(missing_ok=True)
            raise SystemExit(f"asset_sync: {rel} does not match the image manifest; nothing replaced.")
        if target.suffix == ".json":
            try:
                json.loads(staged.read_text(encoding="utf-8"))
            except ValueError as exc:
                staged.unlink(missing_ok=True)
                raise SystemExit(f"asset_sync: {rel} is not valid JSON ({exc}); nothing replaced.") from exc
        os.replace(staged, target)

    def startup(self) -> dict[str, Any]:
        problem = self.compatibility_error()
        if problem:
            raise SystemExit(f"asset_sync: {problem}")
        plan = self.plan()
        for rel in plan["missing"]:
            self._copy_verified(rel)
        self._record(plan)
        return plan

    def apply(self, replace_modified: bool = False) -> dict[str, Any]:
        problem = self.compatibility_error()
        if problem:
            raise SystemExit(f"asset_sync: {problem}")
        plan = self.plan()
        replace = plan["update"] + (plan["modified"] if replace_modified else [])
        backup = None
        if replace:
            stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = self.state / "backups" / f"{stamp}-from-{str((self.applied() or {}).get('revision') or 'unknown')[:7]}"
            for rel in replace:
                (backup / "files" / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(self.live / rel, backup / "files" / rel)
            if self.applied_path.is_file():
                shutil.copy2(self.applied_path, backup / "applied.json")
            _write_json(backup / "replaced.json", {"files": replace, "to_revision": self.manifest["revision"]})
        for rel in plan["missing"] + replace:
            self._copy_verified(rel)
        done = {**plan, "current": plan["current"] + plan["missing"] + replace,
                "update": [], "missing": [],
                "modified": [] if replace_modified else plan["modified"]}
        self._record(done)
        return {"replaced": replace, "kept_modified": done["modified"], "backup": str(backup) if backup else None}

    def rollback(self, backup_name: str) -> dict[str, Any]:
        backup = self.state / "backups" / backup_name
        replaced = (_read_json(backup / "replaced.json") or {}).get("files")
        if replaced is None:
            raise SystemExit(f"asset_sync: no backup named {backup_name} under {self.state / 'backups'}.")
        for rel in replaced:
            source, target = backup / "files" / rel, self.live / rel
            staged = target.with_name(target.name + ".asset-new")
            shutil.copy2(source, staged)
            os.replace(staged, target)
        if (backup / "applied.json").is_file():
            shutil.copy2(backup / "applied.json", self.applied_path)
        return {"restored": replaced}


def _summary(plan: dict[str, list[str]]) -> str:
    return ", ".join(f"{len(v)} {k}" for k, v in plan.items())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m services.asset_sync")
    parser.add_argument("command", choices=["manifest", "startup", "status", "apply", "rollback", "backups"])
    parser.add_argument("backup", nargs="?")
    parser.add_argument("--replace-modified", action="store_true")
    parser.add_argument("--image-root", default="/app/training.image")
    parser.add_argument("--data-dir", default=os.getenv("DATA_DIR", "/data"))
    args = parser.parse_args(argv)
    image_root = Path(args.image_root)

    if args.command == "manifest":
        _write_json(image_root / MANIFEST, build_manifest(image_root, os.getenv("APP_SOURCE_REVISION") or "unknown"))
        return 0
    assets = Assets(image_root, Path(args.data_dir))
    if args.command == "startup":
        plan = assets.startup()
        print(f"asset_sync: assets {assets.manifest['asset_version']} (revision "
              f"{assets.manifest['revision'][:7]}): {_summary(plan)} -- {len(plan['missing'])} added.", file=sys.stderr)
        if plan["update"]:
            print(f"asset_sync: {len(plan['update'])} shipped file(s) have a newer version in this image; "
                  "apply them with `python -m services.asset_sync apply` (docs/DOCKER.md, 'Assets').", file=sys.stderr)
        return 0
    if args.command == "status":
        problem = assets.compatibility_error()
        plan = assets.plan()
        print(json.dumps({"image_assets": assets.manifest["asset_version"], "image_revision": assets.manifest["revision"],
                          "applied": {k: (assets.applied() or {}).get(k) for k in ("asset_version", "revision", "updated_at")},
                          "problem": problem, "counts": {k: len(v) for k, v in plan.items()},
                          "update": plan["update"], "modified": plan["modified"]}, indent=1))
        return 1 if problem else 0
    if args.command == "apply":
        print(json.dumps(assets.apply(replace_modified=args.replace_modified), indent=1))
        return 0
    if args.command == "backups":
        root = assets.state / "backups"
        print("\n".join(sorted(p.name for p in root.iterdir())) if root.is_dir() else "")
        return 0
    if not args.backup:
        parser.error("rollback needs a backup name (see `backups`)")
    print(json.dumps(assets.rollback(args.backup), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
