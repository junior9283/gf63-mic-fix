from gf63_mic_fix import state
from gf63_mic_fix.state import SavedState


def test_roundtrip(tmp_path):
    s = SavedState(default_source="alsa_input.x", physical_volume_percent=54, noise_suppression=True)
    state.save(tmp_path / "cfg", s)
    assert state.load(tmp_path / "cfg") == s


def test_save_leaves_no_temp_files(tmp_path):
    state.save(tmp_path, SavedState(None, None))
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_load_missing_returns_none(tmp_path):
    assert state.load(tmp_path / "nope") is None


def test_load_corrupt_returns_none(tmp_path):
    (tmp_path / "state.json").write_text("{not json")
    assert state.load(tmp_path) is None


def test_load_wrong_shape_returns_none(tmp_path):
    (tmp_path / "state.json").write_text('["a list"]')
    assert state.load(tmp_path) is None


def test_clear_missing_dir_ok(tmp_path):
    state.clear(tmp_path / "nope")


def test_clear_removes_dir(tmp_path):
    d = tmp_path / "cfg"
    state.save(d, SavedState(None, None))
    (d / "pipewire.conf").write_text("x")
    state.clear(d)
    assert not d.exists()
