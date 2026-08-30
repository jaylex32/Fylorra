"""
Fylorra - Universal Undo System
Handles undo for ALL file operations: rename, move, copy, delete, categorize
"""

import sqlite3
import json
import logging
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Literal
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class OperationType(Enum):
    """Types of file operations"""
    RENAME = "rename"
    MOVE = "move"
    COPY = "copy"
    DELETE = "delete"
    CATEGORIZE = "categorize"
    CREATE_FOLDER = "create_folder"
    BULK_RENAME = "bulk_rename"
    BULK_MOVE = "bulk_move"
    BULK_CATEGORIZE = "bulk_categorize"


@dataclass
class FileOperation:
    """Single file operation that can be undone"""
    operation_type: OperationType
    source_path: str
    destination_path: Optional[str]
    original_content: Optional[str]  # For deleted files (base64 if binary)
    timestamp: str
    success: bool
    error_message: Optional[str] = None
    metadata: Optional[Dict] = None  # Additional info (AI model, confidence, etc.)


@dataclass
class UndoTransaction:
    """Batch of file operations that can be undone as a group"""
    transaction_id: int
    operation_type: str
    timestamp: str
    operation_count: int
    success_count: int
    failed_count: int
    can_undo: bool
    description: str  # Human-readable description
    operations: List[FileOperation]
    metadata: Optional[Dict] = None


class UniversalUndoManager:
    """
    Universal undo manager for ALL file operations in Fylorra
    Handles rename, move, copy, delete, categorize, and more
    """

    # Trash folder for deleted files (can be restored)
    TRASH_FOLDER_NAME = ".fylorra_trash"

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize undo manager

        Args:
            db_path: Path to SQLite database (default: user config folder)
        """
        if db_path is None:
            # Store in the legacy app data folder for existing installations.
            app_data = Path.home() / '.fylorra'
            app_data.mkdir(exist_ok=True)
            db_path = app_data / 'universal_undo.db'

        self.db_path = db_path
        self._init_database()

    def _init_database(self):
        """Create database tables if they don't exist"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Transactions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    operation_count INTEGER NOT NULL,
                    success_count INTEGER NOT NULL,
                    failed_count INTEGER NOT NULL,
                    can_undo INTEGER NOT NULL DEFAULT 1,
                    description TEXT NOT NULL,
                    metadata TEXT
                )
            """)

            # Operations table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS operations (
                    operation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transaction_id INTEGER NOT NULL,
                    operation_type TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    destination_path TEXT,
                    original_content TEXT,
                    timestamp TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    error_message TEXT,
                    metadata TEXT,
                    FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id)
                )
            """)

            # Indices for fast lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_transaction_timestamp
                ON transactions(timestamp DESC)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_operations_transaction
                ON operations(transaction_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_operations_type
                ON operations(operation_type)
            """)

            conn.commit()

    def create_transaction(self, operations: List[FileOperation],
                          operation_type: OperationType,
                          description: str,
                          metadata: Optional[Dict] = None) -> int:
        """
        Create new undo transaction

        Args:
            operations: List of file operations
            operation_type: Type of operation (rename, move, etc.)
            description: Human-readable description
            metadata: Optional metadata

        Returns:
            transaction_id
        """
        success_count = sum(1 for op in operations if op.success)
        failed_count = len(operations) - success_count

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Insert transaction
            cursor.execute("""
                INSERT INTO transactions
                (operation_type, timestamp, operation_count, success_count, failed_count, can_undo, description, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                operation_type.value,
                datetime.now().isoformat(),
                len(operations),
                success_count,
                failed_count,
                1,  # can_undo = True initially
                description,
                json.dumps(metadata) if metadata else None
            ))

            transaction_id = cursor.lastrowid

            # Insert operations
            for op in operations:
                cursor.execute("""
                    INSERT INTO operations
                    (transaction_id, operation_type, source_path, destination_path,
                     original_content, timestamp, success, error_message, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    transaction_id,
                    op.operation_type.value,
                    op.source_path,
                    op.destination_path,
                    op.original_content,
                    op.timestamp,
                    1 if op.success else 0,
                    op.error_message,
                    json.dumps(op.metadata) if op.metadata else None
                ))

            conn.commit()

        logger.info(f"Created undo transaction {transaction_id}: {description}")
        return transaction_id

    def get_transaction(self, transaction_id: int) -> Optional[UndoTransaction]:
        """Get transaction details"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get transaction
            cursor.execute("""
                SELECT * FROM transactions WHERE transaction_id = ?
            """, (transaction_id,))

            trans_row = cursor.fetchone()
            if not trans_row:
                return None

            # Get operations
            cursor.execute("""
                SELECT * FROM operations WHERE transaction_id = ? ORDER BY operation_id
            """, (transaction_id,))

            operations = [
                FileOperation(
                    operation_type=OperationType(row['operation_type']),
                    source_path=row['source_path'],
                    destination_path=row['destination_path'],
                    original_content=row['original_content'],
                    timestamp=row['timestamp'],
                    success=bool(row['success']),
                    error_message=row['error_message'],
                    metadata=json.loads(row['metadata']) if row['metadata'] else None
                )
                for row in cursor.fetchall()
            ]

            return UndoTransaction(
                transaction_id=trans_row['transaction_id'],
                operation_type=trans_row['operation_type'],
                timestamp=trans_row['timestamp'],
                operation_count=trans_row['operation_count'],
                success_count=trans_row['success_count'],
                failed_count=trans_row['failed_count'],
                can_undo=bool(trans_row['can_undo']),
                description=trans_row['description'],
                operations=operations,
                metadata=json.loads(trans_row['metadata']) if trans_row['metadata'] else None
            )

    def get_recent_transactions(self, limit: int = 10) -> List[UndoTransaction]:
        """Get recent transactions"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT transaction_id FROM transactions
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))

            transaction_ids = [row['transaction_id'] for row in cursor.fetchall()]

        return [self.get_transaction(tid) for tid in transaction_ids if self.get_transaction(tid)]

    def undo_transaction(self, transaction_id: int) -> Tuple[bool, str, int]:
        """
        Undo a transaction (reverse all operations)

        Returns:
            (success, message, reversed_count)
        """
        transaction = self.get_transaction(transaction_id)
        if not transaction:
            return False, f"Transaction {transaction_id} not found", 0

        if not transaction.can_undo:
            return False, "Transaction has already been undone or is not reversible", 0

        # Reverse operations based on type
        reversed_count = 0
        failed_reversals = []

        for op in reversed(transaction.operations):
            if not op.success:
                continue  # Skip operations that failed originally

            try:
                if op.operation_type == OperationType.RENAME:
                    reversed_count += self._undo_rename(op, failed_reversals)
                elif op.operation_type == OperationType.MOVE:
                    reversed_count += self._undo_move(op, failed_reversals)
                elif op.operation_type == OperationType.COPY:
                    reversed_count += self._undo_copy(op, failed_reversals)
                elif op.operation_type == OperationType.DELETE:
                    reversed_count += self._undo_delete(op, failed_reversals)
                elif op.operation_type == OperationType.CATEGORIZE:
                    reversed_count += self._undo_categorize(op, failed_reversals)
                elif op.operation_type == OperationType.CREATE_FOLDER:
                    reversed_count += self._undo_create_folder(op, failed_reversals)
                else:
                    # Bulk operations are handled as individual operations
                    logger.warning(f"Unknown operation type: {op.operation_type}")

            except Exception as e:
                failed_reversals.append(f"{Path(op.source_path).name}: {str(e)}")

        # Mark transaction as undone
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE transactions SET can_undo = 0 WHERE transaction_id = ?
            """, (transaction_id,))
            conn.commit()

        if reversed_count == 0:
            message = "Failed to reverse any operations:\n" + "\n".join(failed_reversals[:5])
            return False, message, 0

        if failed_reversals:
            message = f"Reversed {reversed_count}/{transaction.success_count} operations.\n\nFailed:\n"
            message += "\n".join(failed_reversals[:5])
            if len(failed_reversals) > 5:
                message += f"\n... and {len(failed_reversals) - 5} more"
            return True, message, reversed_count

        return True, f"Successfully reversed all {reversed_count} operations", reversed_count

    def _undo_rename(self, op: FileOperation, failed_reversals: List[str]) -> int:
        """Undo a rename operation"""
        source = Path(op.source_path)
        dest = Path(op.destination_path)

        if not dest.exists():
            failed_reversals.append(f"{dest.name}: File no longer exists at renamed location")
            return 0

        if source.exists() and source != dest:
            failed_reversals.append(f"{dest.name}: Original name is now taken")
            return 0

        try:
            dest.rename(source)
            logger.info(f"Undone rename: {dest} -> {source}")
            return 1
        except Exception as e:
            failed_reversals.append(f"{dest.name}: {str(e)}")
            return 0

    def _undo_move(self, op: FileOperation, failed_reversals: List[str]) -> int:
        """Undo a move operation"""
        source = Path(op.source_path)
        dest = Path(op.destination_path)

        if not dest.exists():
            failed_reversals.append(f"{dest.name}: File no longer exists at destination")
            return 0

        if source.exists():
            failed_reversals.append(f"{dest.name}: Original location is now occupied")
            return 0

        try:
            # Ensure parent directory exists
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dest), str(source))
            logger.info(f"Undone move: {dest} -> {source}")
            return 1
        except Exception as e:
            failed_reversals.append(f"{dest.name}: {str(e)}")
            return 0

    def _undo_copy(self, op: FileOperation, failed_reversals: List[str]) -> int:
        """Undo a copy operation (delete the copy)"""
        dest = Path(op.destination_path)

        if not dest.exists():
            # Already gone, consider it undone
            return 1

        try:
            dest.unlink()
            logger.info(f"Undone copy: Deleted {dest}")
            return 1
        except Exception as e:
            failed_reversals.append(f"{dest.name}: {str(e)}")
            return 0

    def _undo_delete(self, op: FileOperation, failed_reversals: List[str]) -> int:
        """Undo a delete operation (restore from trash or content)"""
        source = Path(op.source_path)

        # Check if file is in trash
        if op.destination_path:
            trash_path = Path(op.destination_path)
            if trash_path.exists():
                try:
                    source.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(trash_path), str(source))
                    logger.info(f"Restored from trash: {source}")
                    return 1
                except Exception as e:
                    failed_reversals.append(f"{source.name}: {str(e)}")
                    return 0

        # Try to restore from saved content (if available)
        if op.original_content:
            try:
                source.parent.mkdir(parents=True, exist_ok=True)
                # For now, we don't implement content restoration
                # This would require base64 encoding/decoding for binary files
                failed_reversals.append(f"{source.name}: Content restoration not yet implemented")
                return 0
            except Exception as e:
                failed_reversals.append(f"{source.name}: {str(e)}")
                return 0

        failed_reversals.append(f"{source.name}: No backup available")
        return 0

    def _undo_categorize(self, op: FileOperation, failed_reversals: List[str]) -> int:
        """Undo a categorize operation (move back from category folder)"""
        # Categorize is essentially a move operation
        return self._undo_move(op, failed_reversals)

    def _undo_create_folder(self, op: FileOperation, failed_reversals: List[str]) -> int:
        """Undo a create folder operation"""
        folder = Path(op.source_path)

        if not folder.exists():
            # Already gone, consider it undone
            return 1

        # Only delete if empty
        try:
            if not any(folder.iterdir()):
                folder.rmdir()
                logger.info(f"Undone create folder: Deleted {folder}")
                return 1
            else:
                failed_reversals.append(f"{folder.name}: Folder is not empty")
                return 0
        except Exception as e:
            failed_reversals.append(f"{folder.name}: {str(e)}")
            return 0

    def cleanup_old_history(self, days: int = 30):
        """Remove history older than specified days"""
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Get old transaction IDs
            cursor.execute("""
                SELECT transaction_id FROM transactions WHERE timestamp < ?
            """, (cutoff_date,))

            old_transaction_ids = [row[0] for row in cursor.fetchall()]

            if old_transaction_ids:
                placeholders = ','.join('?' * len(old_transaction_ids))

                # Delete operations
                cursor.execute(f"""
                    DELETE FROM operations WHERE transaction_id IN ({placeholders})
                """, old_transaction_ids)

                # Delete transactions
                cursor.execute(f"""
                    DELETE FROM transactions WHERE transaction_id IN ({placeholders})
                """, old_transaction_ids)

                conn.commit()
                logger.info(f"Cleaned up {len(old_transaction_ids)} old transactions")

    def get_statistics(self) -> Dict:
        """Get undo history statistics"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM transactions")
            total_transactions = cursor.fetchone()[0]

            cursor.execute("SELECT SUM(operation_count) FROM transactions")
            total_operations = cursor.fetchone()[0] or 0

            cursor.execute("SELECT SUM(success_count) FROM transactions")
            total_success = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM transactions WHERE can_undo = 1")
            undoable_count = cursor.fetchone()[0]

            cursor.execute("""
                SELECT operation_type, COUNT(*) as count
                FROM transactions
                GROUP BY operation_type
            """)
            operations_by_type = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute("""
                SELECT timestamp FROM transactions
                ORDER BY timestamp DESC LIMIT 1
            """)
            last_row = cursor.fetchone()
            last_operation = last_row[0] if last_row else None

        return {
            'total_transactions': total_transactions,
            'total_operations': total_operations,
            'total_success': total_success,
            'undoable_transactions': undoable_count,
            'operations_by_type': operations_by_type,
            'last_operation': last_operation,
            'success_rate': (total_success / total_operations * 100) if total_operations > 0 else 0
        }


# Global instance
_undo_manager = None


def get_undo_manager() -> UniversalUndoManager:
    """Get or create global undo manager instance"""
    global _undo_manager
    if _undo_manager is None:
        _undo_manager = UniversalUndoManager()
    return _undo_manager


# Convenience functions for common operations

def record_rename(old_path: Path, new_path: Path, metadata: Optional[Dict] = None) -> int:
    """Record a single rename operation"""
    manager = get_undo_manager()
    operation = FileOperation(
        operation_type=OperationType.RENAME,
        source_path=str(old_path),
        destination_path=str(new_path),
        original_content=None,
        timestamp=datetime.now().isoformat(),
        success=True,
        metadata=metadata
    )
    return manager.create_transaction(
        [operation],
        OperationType.RENAME,
        f"Rename: {old_path.name} → {new_path.name}",
        metadata
    )


def record_bulk_rename(old_new_pairs: List[Tuple[Path, Path]], metadata: Optional[Dict] = None) -> int:
    """Record bulk rename operations"""
    manager = get_undo_manager()
    operations = [
        FileOperation(
            operation_type=OperationType.RENAME,
            source_path=str(old_path),
            destination_path=str(new_path),
            original_content=None,
            timestamp=datetime.now().isoformat(),
            success=True,
            metadata=metadata
        )
        for old_path, new_path in old_new_pairs
    ]
    return manager.create_transaction(
        operations,
        OperationType.BULK_RENAME,
        f"Bulk Rename: {len(operations)} files",
        metadata
    )


def record_move(source: Path, destination: Path, metadata: Optional[Dict] = None) -> int:
    """Record a move operation"""
    manager = get_undo_manager()
    operation = FileOperation(
        operation_type=OperationType.MOVE,
        source_path=str(source),
        destination_path=str(destination),
        original_content=None,
        timestamp=datetime.now().isoformat(),
        success=True,
        metadata=metadata
    )
    return manager.create_transaction(
        [operation],
        OperationType.MOVE,
        f"Move: {source.name} → {destination.parent.name}/",
        metadata
    )


def record_categorize(files_categories: List[Tuple[Path, Path]], metadata: Optional[Dict] = None) -> int:
    """Record categorization operations"""
    manager = get_undo_manager()
    operations = [
        FileOperation(
            operation_type=OperationType.CATEGORIZE,
            source_path=str(source),
            destination_path=str(dest),
            original_content=None,
            timestamp=datetime.now().isoformat(),
            success=True,
            metadata=metadata
        )
        for source, dest in files_categories
    ]
    return manager.create_transaction(
        operations,
        OperationType.BULK_CATEGORIZE,
        f"Categorize: {len(operations)} files",
        metadata
    )


def undo_last_operation() -> Tuple[bool, str, int]:
    """Undo the most recent operation"""
    manager = get_undo_manager()
    recent = manager.get_recent_transactions(limit=1)

    if not recent:
        return False, "No undo history found", 0

    transaction = recent[0]
    if not transaction.can_undo:
        return False, "Most recent operation has already been undone", 0

    return manager.undo_transaction(transaction.transaction_id)
