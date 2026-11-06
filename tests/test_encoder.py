import unittest
from math import pi, sin
from struct import pack
from unittest.mock import MagicMock, patch

from opuslib import Decoder as OpusDecoder

from pymumble_typed.mumble import Mumble
from pymumble_typed.sound import SAMPLE_RATE, CodecProfile
from pymumble_typed.sound.encoder import Encoder
from pymumble_typed.sound.voice import VoiceOutput

FRAME_SAMPLES = SAMPLE_RATE // 50  # 20 ms, the default packet duration, per channel


def make_voice_stack() -> MagicMock:
    voice = MagicMock()
    voice.active = True
    return voice


def tone(channels: int, samples: int = FRAME_SAMPLES) -> bytes:
    # A 440 Hz sine, the same on every channel, as interleaved signed 16 bit PCM.
    values = [int(8000 * sin(2 * pi * 440 * i / SAMPLE_RATE)) for i in range(samples)]
    return b"".join(pack("<h", value) * channels for value in values)


def is_stereo_packet(packet: bytes) -> bool:
    # RFC 6716, section 3.1: the "s" bit of the TOC byte says whether the packet is stereo.
    return bool(packet[0] & 0x04)


def decoded_samples_per_channel(packet: bytes) -> int:
    # Mumble decodes every Opus packet with a stereo decoder (AudioOutputSpeech): the duration comes from the
    # packet itself, mono or stereo.
    decoded = OpusDecoder(SAMPLE_RATE, 2).decode(packet, FRAME_SAMPLES * 6)
    return len(decoded) // (2 * 2)


class TestEncoderChannels(unittest.TestCase):
    def test_stereo_by_default(self):
        encoder = Encoder(make_voice_stack())
        self.assertEqual(encoder.channels, 2)
        self.assertEqual(encoder.sample_size, 4)
        self.assertEqual(encoder.samples, FRAME_SAMPLES * 4)
        packet = encoder.encode(tone(2))
        self.assertTrue(is_stereo_packet(packet))
        self.assertEqual(decoded_samples_per_channel(packet), FRAME_SAMPLES)

    def test_mono_frame_is_a_mono_packet_of_the_full_duration(self):
        encoder = Encoder(make_voice_stack(), channels=1)
        self.assertEqual(encoder.sample_size, 2)
        self.assertEqual(encoder.samples, FRAME_SAMPLES * 2)
        packet = encoder.encode(tone(1))
        self.assertFalse(is_stereo_packet(packet))
        # Encoded as stereo, the same bytes made half as many samples: twice the speed.
        self.assertEqual(decoded_samples_per_channel(packet), FRAME_SAMPLES)

    def test_channels_setter_rebuilds_the_opus_encoder(self):
        encoder = Encoder(make_voice_stack())
        encoder.bandwidth = 64000
        encoder.channels = 1
        self.assertEqual(encoder.samples, FRAME_SAMPLES * 2)
        packet = encoder.encode(tone(1))
        self.assertFalse(is_stereo_packet(packet))
        self.assertEqual(decoded_samples_per_channel(packet), FRAME_SAMPLES)
        encoder.channels = 2
        self.assertEqual(encoder.samples, FRAME_SAMPLES * 4)
        self.assertTrue(is_stereo_packet(encoder.encode(tone(2))))

    def test_rebuilt_encoder_keeps_the_bitrate(self):
        encoder = Encoder(make_voice_stack())
        encoder.bandwidth = 40000
        expected = encoder.bitrate
        for change in (
            lambda: setattr(encoder, "channels", 1),
            lambda: setattr(encoder, "codec_profile", CodecProfile.Voip),
            lambda: setattr(encoder, "sample_rate", SAMPLE_RATE),
        ):
            change()
            self.assertEqual(encoder._encoder.bitrate, expected)

    def test_audio_per_packet_updates_frame_and_bitrate(self):
        encoder = Encoder(make_voice_stack(), channels=1)
        encoder.audio_per_packet = 0.01
        self.assertEqual(encoder.samples, SAMPLE_RATE // 100 * 2)
        self.assertEqual(encoder._encoder.bitrate, encoder.bitrate)

    def test_invalid_channels(self):
        with self.assertRaises(ValueError):
            Encoder(make_voice_stack(), channels=3)
        encoder = Encoder(make_voice_stack())
        with self.assertRaises(ValueError):
            encoder.channels = 0
        self.assertEqual(encoder.channels, 2)

    def test_voice_output_passes_channels_and_profile(self):
        output = VoiceOutput(MagicMock(), make_voice_stack(), 1, CodecProfile.Voip)
        self.assertEqual(output.encoder.channels, 1)
        self.assertEqual(output.encoder.codec_profile, CodecProfile.Voip)


class TestMumbleStereo(unittest.TestCase):
    def make_mumble(self, **kwargs) -> Mumble:
        with patch("pymumble_typed.mumble.ControlStack"), patch("pymumble_typed.mumble.VoiceStack"):
            return Mumble(host="h", user="u", logger=MagicMock(), **kwargs)

    def test_stereo_flag_sets_the_encoder_channels(self):
        self.assertEqual(self.make_mumble().voice.encoder.channels, 1)
        self.assertEqual(self.make_mumble(stereo=False).voice.encoder.channels, 1)
        self.assertEqual(self.make_mumble(stereo=True).voice.encoder.channels, 2)

    def test_channels_and_profile_survive_a_reconnect(self):
        mumble = self.make_mumble(stereo=False)
        mumble.set_codec_profile(CodecProfile.Voip)
        self.assertEqual(mumble.voice.encoder.codec_profile, CodecProfile.Voip)
        with patch("pymumble_typed.mumble.VoiceStack"):
            mumble._init()
        self.assertEqual(mumble.voice.encoder.channels, 1)
        self.assertEqual(mumble.voice.encoder.codec_profile, CodecProfile.Voip)

    def test_stereo_setter(self):
        mumble = self.make_mumble(stereo=True)
        mumble.stereo = False
        self.assertEqual(mumble.channel_count, 1)
        self.assertEqual(mumble.voice.encoder.channels, 1)
        self.assertEqual(mumble.voice.encoder.samples, FRAME_SAMPLES * 2)


if __name__ == "__main__":
    unittest.main()
