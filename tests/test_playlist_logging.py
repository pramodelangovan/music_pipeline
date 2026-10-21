from pathlib import Path

from scripts.playlist_utils import get_logs_dir


def test_get_logs_dir_creates_logs_directory(tmp_path):
    logs_dir = get_logs_dir(tmp_path)
    assert logs_dir.exists()
    assert logs_dir.name == "logs"
    assert logs_dir.is_dir()
