import pytest

from conftest import PHYS, FakeSystem, make_root
from gf63_mic_fix import SERVICE, VIRTUAL_SOURCE, state
from gf63_mic_fix.fix import DIAGNOSIS_OK, Fixer, FixError, Status

PLUGIN = "/usr/lib64/ladspa/librnnoise_ladspa.so"


def fixer(tmp_path, system, product="GF63 Thin 10SC", plugin=None, **kw):
    return Fixer(
        system,
        config_dir=tmp_path / "cfg",
        root=make_root(tmp_path, product),
        wait_s=kw.pop("wait_s", 0.5),
        rnnoise_finder=lambda: plugin,
        **kw,
    )


def index(calls, *prefix):
    return next(i for i, c in enumerate(calls) if c[: len(prefix)] == list(prefix))


def test_apply_runs_steps_in_order(tmp_path, system):
    f = fixer(tmp_path, system)
    f.apply()
    c = system.calls
    order = [
        index(c, "systemctl", "--user", "daemon-reload"),
        index(c, "systemctl", "--user", "enable", SERVICE),
        index(c, "systemctl", "--user", "restart", SERVICE),
        index(c, "pactl", "set-default-source", VIRTUAL_SOURCE),
        index(c, "pactl", "set-source-volume", PHYS, "20%"),
    ]
    assert order == sorted(order)
    conf = (tmp_path / "cfg" / "pipewire.conf").read_text()
    assert f'target.object = "{PHYS}"' in conf
    assert system.default == VIRTUAL_SOURCE and system.volumes[PHYS] == 20
    assert f.status() is Status.FIXED


def test_apply_saves_previous_state(tmp_path, system):
    fixer(tmp_path, system).apply()
    s = state.load(tmp_path / "cfg")
    assert s.default_source == PHYS and s.physical_volume_percent == 54


def test_apply_twice_keeps_first_state(tmp_path, system):
    f = fixer(tmp_path, system)
    f.apply()
    f.apply()
    s = state.load(tmp_path / "cfg")
    assert s.default_source == PHYS and s.physical_volume_percent == 54


def test_apply_rolls_back_when_node_never_appears(tmp_path):
    system = FakeSystem(node_appears=False)
    f = fixer(tmp_path, system, wait_s=0.3)
    with pytest.raises(FixError):
        f.apply()
    assert system.called("systemctl", "--user", "disable", "--now", SERVICE)
    assert not (tmp_path / "cfg" / "state.json").exists()
    assert system.default == PHYS and system.volumes[PHYS] == 54


def test_apply_refuses_unverified_without_diagnosis(tmp_path, system):
    f = fixer(tmp_path, system, product="GF63 Thin 11UC")
    assert f.status() is Status.NEEDS_DIAGNOSIS
    with pytest.raises(FixError):
        f.apply()
    assert not system.called("systemctl", "--user", "restart")


def test_apply_unverified_after_diagnosis(tmp_path, system):
    f = fixer(tmp_path, system, product="GF63 Thin 11UC")
    (tmp_path / "cfg").mkdir()
    (tmp_path / "cfg" / DIAGNOSIS_OK).write_text("")
    f.apply()
    assert f.status() is Status.FIXED


def test_apply_refuses_unsupported_and_old_pipewire(tmp_path):
    with pytest.raises(FixError):
        fixer(tmp_path / "a", FakeSystem(), product="Modern 15").apply()
    old = fixer(tmp_path / "b", FakeSystem(pipewire="0.3.48"))
    assert old.status() is Status.OLD_PIPEWIRE
    with pytest.raises(FixError):
        old.apply()
    assert fixer(tmp_path / "c", FakeSystem(pipewire=None)).status() is Status.NO_PIPEWIRE


def test_undo_restores_saved_default_and_volume(tmp_path, system):
    f = fixer(tmp_path, system)
    f.apply()
    f.undo()
    assert system.default == PHYS and system.volumes[PHYS] == 54
    assert not system.active and not system.enabled
    assert not (tmp_path / "cfg" / "state.json").exists()
    assert f.status() is Status.NOT_FIXED


def test_undo_without_state_is_safe(tmp_path, system):
    fixer(tmp_path, system).undo()
    assert system.called("systemctl", "--user", "disable", "--now", SERVICE)
    assert not system.called("pactl", "set-default-source")
    assert not system.called("pactl", "set-source-volume")


def test_undo_when_saved_default_missing(tmp_path, system):
    state.save(tmp_path / "cfg", state.SavedState("alsa_input.usb-headset", 54))
    fixer(tmp_path, system).undo()
    assert not system.called("pactl", "set-default-source")
    assert not system.called("pactl", "set-source-volume")


def test_undo_keeps_diagnosis(tmp_path, system):
    f = fixer(tmp_path, system, product="GF63 Thin 11UC")
    (tmp_path / "cfg").mkdir()
    (tmp_path / "cfg" / DIAGNOSIS_OK).write_text("")
    f.apply()
    f.undo()
    assert (tmp_path / "cfg" / DIAGNOSIS_OK).exists()
    f.undo(purge=True)
    assert not (tmp_path / "cfg").exists()


def test_undo_clears_state_even_when_restore_fails(tmp_path, system):
    f = fixer(tmp_path, system)
    f.apply()
    system.fail_volume = True
    with pytest.raises(FixError):
        f.undo()
    assert not system.active
    assert not (tmp_path / "cfg" / "state.json").exists()
    assert not (tmp_path / "cfg" / "pipewire.conf").exists()


def test_noise_suppression_failure_keeps_fix_without_it(tmp_path, system):
    f = fixer(tmp_path, system, plugin=PLUGIN)
    f.apply()
    system.fail_starts = 1  # the RNNoise chain will not come up; the plain one will
    with pytest.raises(FixError):
        f.set_noise_suppression(True)
    assert PLUGIN not in (tmp_path / "cfg" / "pipewire.conf").read_text()
    assert f.noise_suppression() is False
    assert state.load(tmp_path / "cfg").default_source == PHYS  # original state kept for undo
    assert f.status() is Status.FIXED


def test_status_fixed_not_default(tmp_path, system):
    f = fixer(tmp_path, system)
    f.apply()
    system.default = "alsa_input.usb-headset"
    assert f.status() is Status.FIXED_NOT_DEFAULT
    f.make_default()
    assert f.status() is Status.FIXED


def test_set_gain_clamps(tmp_path, system):
    f = fixer(tmp_path, system)
    f.set_gain(55)
    assert system.volumes[PHYS] == 30
    f.set_gain(3)
    assert system.volumes[PHYS] == 10
    assert f.get_gain() == 10


def test_noise_suppression_requires_plugin(tmp_path, system):
    f = fixer(tmp_path, system, plugin=None)
    f.apply()
    with pytest.raises(FixError):
        f.set_noise_suppression(True)


def test_noise_suppression_regenerates_conf_and_keeps_gain(tmp_path, system):
    f = fixer(tmp_path, system, plugin=PLUGIN)
    f.apply()
    f.set_gain(25)
    f.set_noise_suppression(True)
    assert PLUGIN in (tmp_path / "cfg" / "pipewire.conf").read_text()
    assert state.load(tmp_path / "cfg").noise_suppression is True
    assert system.volumes[PHYS] == 25
    assert f.noise_suppression() is True


def test_apply_drops_noise_suppression_whose_plugin_was_removed(tmp_path, system):
    # RNNoise was on, then its package was uninstalled: "Fix" must still work, without it.
    state.save(tmp_path / "cfg", state.SavedState(PHYS, 54, noise_suppression=True))
    f = fixer(tmp_path, system, plugin=None)
    f.apply()
    assert f.status() is Status.FIXED
    assert state.load(tmp_path / "cfg").noise_suppression is False
    assert "rnnoise" not in (tmp_path / "cfg" / "pipewire.conf").read_text().lower()
