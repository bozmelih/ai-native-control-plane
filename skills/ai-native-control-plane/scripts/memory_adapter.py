#!/usr/bin/env python3
"""Local Git-backed memory adapter for AI-Native Control Plane V4.

The adapter writes reviewable JSON files inside a caller-provided repository
root. It never invokes Git, contacts GitHub, or expands its own authority.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VERSION = "4.0.0"
DURABLE_DIRECTORIES = {
    "context": Path("memory/context"),
    "decision_log": Path("memory/decisions"),
    "backlog": Path("memory/backlog"),
}
WORKING_DIRECTORY = Path(".control-plane/working")
SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
DURABLE_CONTEXT_CLASSES = {"verified_fact", "user_confirmed", "primary_source", "secondary_source"}


class MemoryAdapterError(ValueError):
    """Raised when a memory read or write would violate the adapter contract."""


def _canonical_bytes(data: Any) -> bytes:
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _safe_component(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SAFE_COMPONENT.fullmatch(value):
        raise MemoryAdapterError(f"{label} must match {SAFE_COMPONENT.pattern}")
    return value


class GitMemoryAdapter:
    """Read and apply bounded memory changes under one explicit root."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    @property
    def manifest_path(self) -> Path:
        return self.root / "memory/manifest.json"

    def _ensure_inside_root(self, path: Path) -> Path:
        resolved = path.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise MemoryAdapterError(f"path escapes memory root: {path}")
        return resolved

    def _record_path(self, memory_class: str, record_id: str, task_id: str) -> Path:
        record_id = _safe_component(record_id, "record_id")
        if memory_class == "working_memory":
            task_id = _safe_component(task_id, "task_id")
            relative = WORKING_DIRECTORY / task_id / f"{record_id}.json"
        else:
            if memory_class not in DURABLE_DIRECTORIES:
                raise MemoryAdapterError(f"unsupported memory class: {memory_class}")
            relative = DURABLE_DIRECTORIES[memory_class] / f"{record_id}.json"
        return self._ensure_inside_root(self.root / relative)

    def _load_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.is_file():
            return {
                "schema_version": VERSION,
                "applied_change_ids": [],
                "last_proposal_id": None,
                "last_authorization_id": None,
            }
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise MemoryAdapterError(f"invalid memory manifest: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("applied_change_ids"), list):
            raise MemoryAdapterError("invalid memory manifest structure")
        return data

    def current_revision(self) -> str:
        """Return a deterministic revision for durable memory and its manifest."""

        digest = hashlib.sha256()
        memory_root = self.root / "memory"
        if memory_root.is_dir():
            for path in sorted(item for item in memory_root.rglob("*.json") if item.is_file()):
                resolved = self._ensure_inside_root(path)
                digest.update(resolved.relative_to(self.root).as_posix().encode("utf-8"))
                digest.update(b"\0")
                digest.update(resolved.read_bytes())
                digest.update(b"\0")
        return f"sha256:{digest.hexdigest()}"

    def read(self, selectors: dict[str, Any] | None = None) -> dict[str, Any]:
        """Read selected records without mutating memory."""

        selectors = selectors or {}
        classes = selectors.get("memory_classes", list(DURABLE_DIRECTORIES))
        record_ids = selectors.get("record_ids")
        if not isinstance(classes, list) or not all(item in {*DURABLE_DIRECTORIES, "working_memory"} for item in classes):
            raise MemoryAdapterError("selectors.memory_classes is invalid")
        if record_ids is not None and (not isinstance(record_ids, list) or not all(isinstance(item, str) for item in record_ids)):
            raise MemoryAdapterError("selectors.record_ids must be a string array")
        allowed_ids = set(record_ids) if record_ids is not None else None
        records: list[dict[str, Any]] = []
        for memory_class in classes:
            directory = self.root / (WORKING_DIRECTORY if memory_class == "working_memory" else DURABLE_DIRECTORIES[memory_class])
            if not directory.is_dir():
                continue
            for path in sorted(directory.rglob("*.json")):
                self._ensure_inside_root(path)
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    raise MemoryAdapterError(f"invalid memory record {path}: {exc}") from exc
                if not isinstance(record, dict):
                    raise MemoryAdapterError(f"memory record must be an object: {path}")
                if allowed_ids is None or record.get("record_id") in allowed_ids:
                    records.append(record)
        return {"schema_version": VERSION, "revision": self.current_revision(), "records": records}

    def _validate_authorization(self, authorization: dict[str, Any], proposal: dict[str, Any]) -> str:
        if authorization.get("schema_version") != VERSION:
            raise MemoryAdapterError("authorization must use schema_version 4.0.0")
        authorization_id = _safe_component(authorization.get("authorization_id"), "authorization_id")
        if authorization.get("status") != "active":
            raise MemoryAdapterError("memory write authorization is not active")
        scopes = authorization.get("scopes")
        if not isinstance(scopes, list) or "memory_write" not in scopes:
            raise MemoryAdapterError("authorization does not include memory_write")
        if authorization.get("task_id") != proposal.get("task_id"):
            raise MemoryAdapterError("authorization task_id does not match proposal")
        allowed_classes = authorization.get("allowed_memory_classes")
        if not isinstance(allowed_classes, list):
            raise MemoryAdapterError("allowed_memory_classes must be an array")
        proposal_classes = {change.get("target_memory_class") for change in proposal.get("changes", [])}
        if not proposal_classes <= set(allowed_classes):
            raise MemoryAdapterError("proposal includes a memory class outside authorization")
        expires_at = authorization.get("expires_at")
        try:
            expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        except ValueError as exc:
            raise MemoryAdapterError("authorization expires_at must be ISO-8601") from exc
        if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
            raise MemoryAdapterError("memory write authorization is expired or timezone-free")
        for key in ["approved_by", "evidence_reference"]:
            if not isinstance(authorization.get(key), str) or not authorization[key].strip():
                raise MemoryAdapterError(f"authorization.{key} is required")
        return authorization_id

    def _atomic_write(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _canonical_bytes(data)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def _validate_record_semantics(self, memory_class: str, record: dict[str, Any]) -> None:
        source_refs = record.get("source_refs")
        if not isinstance(source_refs, list) or not all(isinstance(item, str) and item for item in source_refs):
            raise MemoryAdapterError("record.source_refs must be a string array")
        if memory_class == "context":
            if record.get("epistemic_class") not in DURABLE_CONTEXT_CLASSES or not source_refs:
                raise MemoryAdapterError("durable context requires supported evidence and provenance")
        elif memory_class == "decision_log":
            acceptance = record.get("human_acceptance")
            if record.get("epistemic_class") != "user_confirmed" or not isinstance(acceptance, dict):
                raise MemoryAdapterError("decision log requires explicit human acceptance")
            for key in ["accepted_by", "accepted_at", "evidence_reference"]:
                if not isinstance(acceptance.get(key), str) or not acceptance[key].strip():
                    raise MemoryAdapterError(f"decision human_acceptance.{key} is required")
        elif memory_class == "backlog":
            for key in ["owner", "status", "next_gate"]:
                if not isinstance(record.get(key), str) or not record[key].strip():
                    raise MemoryAdapterError(f"backlog record.{key} is required")
            if record["status"] not in {"open", "deferred", "blocked"}:
                raise MemoryAdapterError("backlog status is invalid")
        elif memory_class == "working_memory":
            try:
                expiry = datetime.fromisoformat(str(record.get("expires_at")).replace("Z", "+00:00"))
            except ValueError as exc:
                raise MemoryAdapterError("working memory expires_at must be ISO-8601") from exc
            if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
                raise MemoryAdapterError("working memory expiry must be timezone-aware and in the future")
            if record.get("promotion_authorized") is not False:
                raise MemoryAdapterError("working memory cannot auto-promote")

    def apply(self, proposal: dict[str, Any], authorization: dict[str, Any], expected_revision: str) -> dict[str, Any]:
        """Apply one authorized proposal with optimistic and idempotent guards."""

        if proposal.get("schema_version") != VERSION:
            raise MemoryAdapterError("proposal must use schema_version 4.0.0")
        if (
            proposal.get("write_status") != "proposed"
            or proposal.get("write_authorization_required") is not True
            or proposal.get("write_authorization") != "not_authorized"
        ):
            raise MemoryAdapterError("proposal is not in a write-gated proposed state")
        proposal_id = _safe_component(proposal.get("proposal_id"), "proposal_id")
        task_id = _safe_component(proposal.get("task_id"), "task_id")
        changes = proposal.get("changes")
        if not isinstance(changes, list):
            raise MemoryAdapterError("proposal.changes must be an array")
        verified_refs = proposal.get("verified_evidence_refs")
        if not isinstance(verified_refs, list) or not all(isinstance(item, str) and item for item in verified_refs):
            raise MemoryAdapterError("proposal.verified_evidence_refs must be a string array")
        verified_ref_set = set(verified_refs)
        authorization_id = self._validate_authorization(authorization, proposal)

        manifest = self._load_manifest()
        applied = set(manifest.get("applied_change_ids", []))
        change_ids = [_safe_component(change.get("change_id"), "change_id") for change in changes if isinstance(change, dict)]
        if len(change_ids) != len(changes) or len(change_ids) != len(set(change_ids)):
            raise MemoryAdapterError("changes must be unique objects with safe change_id values")
        already_applied = [change_id for change_id in change_ids if change_id in applied]
        if already_applied:
            if len(already_applied) == len(change_ids):
                return {
                    "schema_version": VERSION,
                    "proposal_id": proposal_id,
                    "status": "no_op_already_applied",
                    "applied_change_ids": [],
                    "revision": self.current_revision(),
                }
            raise MemoryAdapterError("proposal partially overlaps previously applied changes")

        current = self.current_revision()
        if expected_revision != current or proposal.get("base_revision") != expected_revision:
            raise MemoryAdapterError(f"revision conflict: expected {expected_revision}, current {current}")

        prepared: list[tuple[Path, dict[str, Any], str]] = []
        for change in changes:
            memory_class = change.get("target_memory_class")
            operation = change.get("operation")
            if operation not in {"add", "update", "supersede"}:
                raise MemoryAdapterError(f"unsupported operation: {operation}")
            record = change.get("record")
            if not isinstance(record, dict):
                raise MemoryAdapterError("change.record must be an object")
            record_id = _safe_component(change.get("record_id"), "record_id")
            if record.get("record_id") != record_id or record.get("memory_class") != memory_class:
                raise MemoryAdapterError("change and record identity mismatch")
            self._validate_record_semantics(str(memory_class), record)
            if not set(record.get("source_refs", [])) <= verified_ref_set:
                raise MemoryAdapterError("record provenance is not in proposal.verified_evidence_refs")
            path = self._record_path(str(memory_class), record_id, task_id)
            exists = path.exists()
            if operation == "add" and exists:
                raise MemoryAdapterError(f"record already exists: {record_id}")
            if operation in {"update", "supersede"} and not exists:
                raise MemoryAdapterError(f"record does not exist for {operation}: {record_id}")
            stored = dict(record)
            stored["schema_version"] = VERSION
            stored["source_task_id"] = task_id
            stored["change_id"] = change["change_id"]
            stored["lifecycle_status"] = "superseded" if operation == "supersede" else "active"
            prepared.append((path, stored, change["change_id"]))

        for path, record, _ in prepared:
            self._atomic_write(path, record)
        manifest["schema_version"] = VERSION
        manifest["applied_change_ids"] = sorted(applied | set(change_ids))
        manifest["last_proposal_id"] = proposal_id
        manifest["last_authorization_id"] = authorization_id
        self._atomic_write(self.manifest_path, manifest)
        return {
            "schema_version": VERSION,
            "proposal_id": proposal_id,
            "status": "applied",
            "applied_change_ids": change_ids,
            "revision": self.current_revision(),
        }
