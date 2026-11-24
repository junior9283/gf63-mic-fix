import json

from conftest import FakeRunner
from gf63_mic_fix import hardware
from gf63_mic_fix.sysrun import Result

ALC233 = "Codec: Realtek ALC233\nAddress: 0\nVendor Id: 0x10ec0235\nSubsystem Id: 0x146212f4\n"
HDMI = "Codec: Intel Kabylake HDMI\nVendor Id: 0x8086280b\n"


def make_root(tmp_path, product, codecs):
    """codecs: {card_index: [codec file contents]}"""
    dmi = tmp_path / "sys/class/dmi/id"
    dmi.mkdir(parents=True)
    (dmi / "product_name").write_text(product + "\n")
    for card, files in codecs.items():
        d = tmp_path / f"proc/asound/card{card}"
        d.mkdir(parents=True)
        for i, text in enumerate(files):
            (d / f"codec#{i}").write_text(text)
    return tmp_path


def test_detect_verified_10sc(tmp_path):
    hw = hardware.detect_hardware(make_root(tmp_path, "GF63 Thin 10SC", {0: [ALC233, HDMI]}))
    assert hw.supported and hw.verified and hw.codec_card == 0
    assert hw.product == "GF63 Thin 10SC"


def test_detect_other_gf63_variant_not_verified(tmp_path):
    hw = hardware.detect_hardware(make_root(tmp_path, "GF63 Thin 11UC", {0: [ALC233]}))
    assert hw.supported and not hw.verified


def test_detect_unsupported_other_laptop(tmp_path):
    hw = hardware.detect_hardware(make_root(tmp_path, "Modern 15 A11M", {0: [ALC233]}))
    assert not hw.supported


def test_detect_gf63_without_alc233_unsupported(tmp_path):
    hw = hardware.detect_hardware(make_root(tmp_path, "GF63 Thin 10SC", {0: [HDMI]}))
    assert not hw.supported and hw.codec_card is None


def test_detect_missing_dmi(tmp_path):
    hw = hardware.detect_hardware(tmp_path)
    assert not hw.supported and hw.product == ""


def _src(name, card, cls="sound", monitor=""):
    props = {"device.class": cls}
    if card is not None:
        props["alsa.card"] = str(card)
    return {"name": name, "monitor_source": monitor, "properties": props}


def pactl_sources(sources):
    return FakeRunner(
        {("pactl", "-f", "json", "list", "sources"): Result(0, json.dumps(sources), "Invalid non-ASCII")}
    )


def test_find_physical_source_on_card1():
    runner = pactl_sources(
        [
            _src("alsa_output.pci-0000_00_1f.3.hdmi.monitor", 0, "monitor", "alsa_output.hdmi"),
            _src("alsa_output.usb.monitor", 1, "monitor", "alsa_output.usb"),
            _src("alsa_input.pci-0000_00_1f.3.analog-stereo.2", 1),
            _src("gf63_mic_fix", None),
        ]
    )
    assert hardware.find_physical_source(runner, 1) == "alsa_input.pci-0000_00_1f.3.analog-stereo.2"


def test_find_physical_source_none_when_pactl_fails():
    runner = FakeRunner({("pactl",): Result(1, "", "Connection refused")})
    assert hardware.find_physical_source(runner, 0) is None


def test_pipewire_version_parses():
    runner = FakeRunner({("pactl", "info"): Result(0, "Server Name: PulseAudio (on PipeWire 1.6.11)\n", "")})
    assert hardware.pipewire_version(runner) == (1, 6, 11)


def test_pipewire_version_none_on_pulseaudio():
    runner = FakeRunner({("pactl", "info"): Result(0, "Server Name: pulseaudio\n", "")})
    assert hardware.pipewire_version(runner) is None


def test_pipewire_version_none_without_pactl():
    runner = FakeRunner({("pactl", "info"): Result(127, "", "not found")})
    assert hardware.pipewire_version(runner) is None


def test_find_rnnoise_plugin(tmp_path):
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "librnnoise_ladspa.so").write_bytes(b"")
    dirs = (str(tmp_path / "a"), str(tmp_path / "b"))
    assert hardware.find_rnnoise_plugin(dirs) == str(tmp_path / "b" / "librnnoise_ladspa.so")
    assert hardware.find_rnnoise_plugin((str(tmp_path / "a"),)) is None
