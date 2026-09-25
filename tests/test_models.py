"""
Tests for MongoDB database connection — verifies the connection layer
imports and behaves correctly.
"""

import os
import sys

# Ensure backend/src is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


class TestDatabaseModule:
    """Test that the database module imports correctly."""

    def test_database_imports(self):
        """Verify database module can be imported without errors."""
        from src.api.db.database import close_db, get_database, get_db, get_users_collection
        assert callable(get_db)
        assert callable(get_database)
        assert callable(get_users_collection)
        assert callable(close_db)

    def test_db_init_imports(self):
        """Verify db __init__ imports cleanly."""
        import src.api.db
        assert hasattr(src.api.db, "database")
