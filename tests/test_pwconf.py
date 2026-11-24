from gf63_mic_fix.pwconf import build_conf

SRC = "alsa_input.X"


def conf(**kw):
    args = {"physical_source": SRC, "rnnoise_plugin": None, "description": "Mic (fixed)"}
    args.update(kw)
    return build_conf(**args)


def test_conf_captures_only_right_channel():
    c = conf()
    assert 'target.object = "alsa_input.X"' in c
    assert "audio.position = [ FR ]" in c
    assert "stream.dont-remix = true" in c
    assert "node.passive = true" in c


def test_conf_has_two_highpass_in_series():
    c = conf()
    assert c.count('"Freq" = 120.0') == 2
    assert '"Q" = 0.54' in c
    assert '"Q" = 1.31' in c
    assert '{ output = "hp1:Out" input = "hp2:In" }' in c
    assert 'outputs = [ "hp2:Out" ]' in c


def test_conf_virtual_source_props():
    c = conf()
    assert 'node.name = "gf63_mic_fix"' in c
    assert "media.class = Audio/Source" in c
    assert "audio.position = [ MONO ]" in c
    assert "priority.session = 3000" in c
    assert "priority.driver = 3000" in c


def test_conf_with_rnnoise_appends_plugin():
    c = conf(rnnoise_plugin="/usr/lib64/ladspa/librnnoise_ladspa.so")
    assert "type = ladspa" in c
    assert "label = noise_suppressor_mono" in c
    assert '"/usr/lib64/ladspa/librnnoise_ladspa.so"' in c
    assert '{ output = "hp2:Out" input = "rnnoise:Input" }' in c
    assert 'outputs = [ "rnnoise:Output" ]' in c


def test_conf_escapes_description():
    c = conf(description='Mic "fixed" \\ ok')
    assert 'node.description = "Mic \\"fixed\\" \\\\ ok"' in c


def test_conf_is_standalone_client():
    c = conf()
    assert "libpipewire-module-protocol-native" in c
    assert "libpipewire-module-adapter" in c
    assert "libpipewire-module-filter-chain" in c
