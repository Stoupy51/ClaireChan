""" The changes to the app's code, and which of its two processes they reach. """
# Imports
from pathlib import Path

import pytest

from clairechan import changes
from clairechan.changes import Changes, reach_this_process


# Functions
def test_a_change_is_seen_until_applied_and_reaches_a_process_only_through_a_module_it_loaded(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setattr(changes, "PACKAGE", tmp_path)
	monkeypatch.setattr(changes, "ASSETS", tmp_path / "assets")
	(tmp_path / "kept.py").write_text("A = 1", encoding="utf-8")
	(tmp_path / "gone.py").write_text("B = 1", encoding="utf-8")
	loaded = Changes()
	assert loaded.edited() == []

	(tmp_path / "kept.py").write_text("A = 2", encoding="utf-8")
	(tmp_path / "gone.py").unlink()
	(tmp_path / "new.py").write_text("", encoding="utf-8")
	assert [Path(path).name for path in loaded.edited()] == ["gone.py", "kept.py", "new.py"]
	assert not reach_this_process(loaded.edited())
	assert reach_this_process([str(changes.__file__)])

	loaded.applied()
	assert loaded.edited() == []

