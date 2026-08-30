"""
Fylorra - Rename History & Undo System
SQLite-based transaction tracking with rollback capability
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import shutil

logger = logging.getLogger(__name__)


@dataclass
class RenameOperation:
    """Single rename operation"""
    old_path: str
    new_path: str
    timestamp: str
    success: bool
    error_message: Optional[str] = None


@dataclass
class RenameTransaction:
    """Batch of rename operations"""
    transaction_id: int
    timestamp: str
    operation_count: int
    success_count: int
    failed_count: int
    can_undo: bool
    operations: List[RenameOperation]


class RenameHistoryManager:
    """
    Manage rename history with undo/rollback capability
    Uses SQLite for persistent storage
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize history manager

        Args:
            db_path: Path to SQLite database (default: user config folder)
        """
        if db_path is None:
            # Store in the legacy app data folder for existing installations.
            app_data = Path.home() / '.fylorra'
            app_data.mkdir(exist_ok=True)
            db_path = app_data / 'rename_history.db'

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
                    timestamp TEXT NOT NULL,
                    operation_count INTEGER NOT NULL,
                    success_count INTEGER NOT NULL,
                    failed_count INTEGER NOT NULL,
                    can_undo INTEGER NOT NULL DEFAULT 1,
                    metadata TEXT
                )
            """)

            # Operations table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS operations (
                    operation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transaction_id INTEGER NOT NULL,
                    old_path TEXT NOT NULL,
                    new_path TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    error_message TEXT,
                    FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id)
                )
            """)

            # Index for fast lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_transaction_timestamp
                ON transactions(timestamp DESC)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_operations_transaction
                ON operations(transaction_id)
            """)

            conn.commit()

    def create_transaction(self, operations: List[RenameOperation],
                          metadata: Optional[Dict] = None) -> int:
        """
        Create new rename transaction

        Args:
            operations: List of rename operations
            metadata: Optional metadata (folder path, AI model used, etc.)

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
                (timestamp, operation_count, success_count, failed_count, can_undo, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                len(operations),
                success_count,
                failed_count,
                1,  # can_undo = True initially
                json.dumps(metadata) if metadata else None
            ))

            transaction_id = cursor.lastrowid

            # Insert operations
            for op in operations:
                cursor.execute("""
                    INSERT INTO operations
                    (transaction_id, old_path, new_path, timestamp, success, error_message)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    transaction_id,
                    op.old_path,
                    op.new_path,
                    op.timestamp,
                    1 if op.success else 0,
                    op.error_message
                ))

            conn.commit()

        logger.info(f"Created rename transaction {transaction_id} with {len(operations)} operations")
        return transaction_id

    def get_transaction(self, transaction_id: int) -> Optional[RenameTransaction]:
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
                RenameOperation(
                    old_path=row['old_path'],
                    new_path=row['new_path'],
                    timestamp=row['timestamp'],
                    success=bool(row['success']),
                    error_message=row['error_message']
                )
                for row in cursor.fetchall()
            ]

            return RenameTransaction(
                transaction_id=trans_row['transaction_id'],
                timestamp=trans_row['timestamp'],
                operation_count=trans_row['operation_count'],
                success_count=trans_row['success_count'],
                failed_count=trans_row['failed_count'],
                can_undo=bool(trans_row['can_undo']),
                operations=operations
            )

    def get_recent_transactions(self, limit: int = 10) -> List[RenameTransaction]:
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

        return [self.get_transaction(tid) for tid in transaction_ids]

    def undo_transaction(self, transaction_id: int) -> Tuple[bool, str, int]:
        """
        Undo a rename transaction (reverse all operations)

        Returns:
            (success, message, reversed_count)
        """
        transaction = self.get_transaction(transaction_id)
        if not transaction:
            return False, f"Transaction {transaction_id} not found", 0

        if not transaction.can_undo:
            return False, "Transaction has already been undone or is not reversible", 0

        # Reverse operations in reverse order
        reversed_count = 0
        failed_reversals = []

        for op in reversed(transaction.operations):
            if not op.success:
                continue  # Skip operations that failed originally

            old_path = Path(op.old_path)
            new_path = Path(op.new_path)

            # Check if current file still exists
            if not new_path.exists():
                failed_reversals.append(f"{new_path.name}: File no longer exists")
                continue

            # Check if original name is available
            if old_path.exists() and old_path != new_path:
                failed_reversals.append(f"{new_path.name}: Original name is now taken")
                continue

            try:
                # Reverse the rename
                new_path.rename(old_path)
                reversed_count += 1
                logger.info(f"Reversed: {new_path} -> {old_path}")
            except Exception as e:
                failed_reversals.append(f"{new_path.name}: {str(e)}")

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
                # Delete operations
                cursor.execute(f"""
                    DELETE FROM operations
                    WHERE transaction_id IN ({','.join('?' * len(old_transaction_ids))})
                """, old_transaction_ids)

                # Delete transactions
                cursor.execute(f"""
                    DELETE FROM transactions
                    WHERE transaction_id IN ({','.join('?' * len(old_transaction_ids))})
                """, old_transaction_ids)

                conn.commit()
                logger.info(f"Cleaned up {len(old_transaction_ids)} old transactions")

    def get_statistics(self) -> Dict:
        """Get history statistics"""
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
            'last_operation': last_operation,
            'success_rate': (total_success / total_operations * 100) if total_operations > 0 else 0
        }


# Global instance for easy access
_history_manager = None


def get_history_manager() -> RenameHistoryManager:
    """Get or create global history manager instance"""
    global _history_manager
    if _history_manager is None:
        _history_manager = RenameHistoryManager()
    return _history_manager


def record_rename_batch(old_new_pairs: List[Tuple[Path, Path]],
                        metadata: Optional[Dict] = None) -> int:
    """
    Convenience function to record a batch of renames

    Args:
        old_new_pairs: List of (old_path, new_path) tuples
        metadata: Optional metadata

    Returns:
        transaction_id
    """
    operations = [
        RenameOperation(
            old_path=str(old_path),
            new_path=str(new_path),
            timestamp=datetime.now().isoformat(),
            success=True
        )
        for old_path, new_path in old_new_pairs
    ]

    manager = get_history_manager()
    return manager.create_transaction(operations, metadata)


def undo_last_rename() -> Tuple[bool, str, int]:
    """
    Undo the most recent rename transaction

    Returns:
        (success, message, reversed_count)
    """
    manager = get_history_manager()
    recent = manager.get_recent_transactions(limit=1)

    if not recent:
        return False, "No rename history found", 0

    transaction = recent[0]
    if not transaction.can_undo:
        return False, "Most recent transaction has already been undone", 0

    return manager.undo_transaction(transaction.transaction_id)
