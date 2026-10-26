import os
import stat
import tempfile
import sqlite3
import pytest

from persistence.database import Database


def make_readonly(path):
    # Set file as read-only (platform-specific)
    if os.name == 'nt':
        os.chmod(path, stat.S_IREAD)
    else:
        os.chmod(path, stat.S_IRUSR)


def make_writable(path):
    if os.name == 'nt':
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    else:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def test_database_check_writable_fails_on_readonly(tmp_path):
    db_path = tmp_path / "test_readonly.db"
    # Create DB
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE IF NOT EXISTS foo(id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    # Make file readonly
    make_readonly(str(db_path))

    db = Database(str(db_path))
    with pytest.raises(PermissionError):
        db.check_writable()

    # Cleanup: make writable again so tmpdir can be removed
    make_writable(str(db_path))
