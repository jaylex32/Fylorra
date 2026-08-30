"""
Fylorra - Filename Explainer
Explain why a file has a given name (trust-building feature).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class RenameEvidence:
    operation_type: str
    timestamp: str
    source_path: str
    destination_path: str
    metadata: Optional[dict]
    transaction_description: Optional[str]


def _default_undo_db_path() -> Path:
    return Path.home() / ".fylorra" / "universal_undo.db"


def get_last_rename_evidence(file_path: Path, *, db_path: Optional[Path] = None) -> Optional[RenameEvidence]:
    db_path = Path(db_path) if db_path else _default_undo_db_path()
    if not db_path.exists():
        return None

    p = str(Path(file_path))
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                o.operation_type,
                o.timestamp,
                o.source_path,
                o.destination_path,
                o.metadata as op_metadata,
                t.description as txn_desc
            FROM operations o
            JOIN transactions t ON t.transaction_id = o.transaction_id
            WHERE o.operation_type IN ('rename', 'bulk_rename')
              AND (o.destination_path = ? OR o.source_path = ?)
            ORDER BY o.timestamp DESC
            LIMIT 1
            """,
            (p, p),
        )
        row = cur.fetchone()
        if not row:
            return None

        meta = None
        try:
            meta = json.loads(row["op_metadata"]) if row["op_metadata"] else None
        except Exception:
            meta = None

        return RenameEvidence(
            operation_type=row["operation_type"],
            timestamp=row["timestamp"],
            source_path=row["source_path"],
            destination_path=row["destination_path"],
            metadata=meta,
            transaction_description=row["txn_desc"],
        )


def explain_filename(file_path: Path, *, ai_manager=None) -> str:
    """
    Explain a filename using rename history evidence if available.
    If AI is available, turn evidence into a friendly explanation.
    """
    file_path = Path(file_path)
    evidence = get_last_rename_evidence(file_path)

    if not evidence:
        return (
            f"No rename history found for:\n{file_path}\n\n"
            "This file may have been created with that name, or it was renamed outside Fylorra."
        )

    meta = evidence.metadata or {}
    ai_suggested = meta.get("ai_suggested")
    user_edited = meta.get("user_edited")
    pattern = meta.get("pattern_applied")
    dup = meta.get("duplicate_handling")

    base = (
        f"Renamed by Fylorra ({evidence.transaction_description or evidence.operation_type}) on {evidence.timestamp}.\n\n"
        f"From:\n{Path(evidence.source_path).name}\n\nTo:\n{Path(evidence.destination_path).name}\n"
    )

    details = []
    if ai_suggested:
        details.append(f"AI suggested: {ai_suggested}")
    if user_edited:
        details.append(f"User edited: {user_edited}")
    if pattern:
        details.append(f"Pattern applied: {pattern}")
    if dup:
        details.append(f"Duplicate handling: {dup}")

    if not ai_manager or not getattr(ai_manager, "is_ready", False):
        return base + ("\n\n" + "\n".join(details) if details else "")

    prompt = (
        "Explain to the user why a file was renamed.\n"
        "Be concise (3-6 sentences). Mention the key signals used (vendor/doc type/date/error text/etc) if present.\n"
        "Do not mention internal variable names. Do not mention JSON.\n\n"
        f"Rename event:\n{base}\n\nDetails:\n" + ("\n".join(details) if details else "None")
    )
    try:
        resp = ai_manager.model.create_chat_completion(
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
            temperature=0.3,
            max_tokens=220,
        )
        return resp["choices"][0]["message"]["content"].strip()
    except Exception:
        return base + ("\n\n" + "\n".join(details) if details else "")

