import unittest
from random import Random
from statistics import fmean, pstdev
from unittest import mock

from pymumble_typed.network import ping as ping_module
from pymumble_typed.network.ping import Ping, PingStats


class TestPingStats(unittest.TestCase):
    def test_mean_and_standard_deviation(self):
        rnd = Random(1)
        pings = [rnd.gauss(5, 1.5) for _ in range(500)]
        stats = PingStats()
        for value in pings:
            stats.update(value)
        self.assertEqual(stats.number, len(pings))
        self.assertAlmostEqual(stats.average, fmean(pings), places=9)
        self.assertAlmostEqual(stats.deviation, pstdev(pings), places=9)

    def test_constant_pings_have_no_deviation(self):
        # The mean of the squares minus the squared mean rounds below zero here, which made sqrt raise.
        for value in (0.1, 0.3, 4.7, 5.1, 12.345, 1e3 / 7):
            stats = PingStats()
            for _ in range(1000):
                stats.update(value)
            self.assertAlmostEqual(stats.average, value, places=9)
            self.assertAlmostEqual(stats.deviation, 0.0, places=6)

    def test_zero_ping_is_a_measure(self):
        stats = PingStats()
        stats.update(0.0)
        self.assertEqual(stats.average, 0.0)
        self.assertEqual(stats.number, 1)

    def test_missing_ping_is_measured_from_the_last_send(self):
        with mock.patch.object(ping_module, "time", side_effect=[100.0, 100.0, 100.0, 100.025]):
            stats = PingStats()
            stats.send()
            stats.update()
        self.assertAlmostEqual(stats.average, 25.0, places=6)


class TestPingTimeout(unittest.TestCase):
    def make_ping(self) -> tuple[Ping, mock.Mock]:
        ping = Ping()
        control = mock.Mock()
        control.is_connected.return_value = True
        voice = mock.Mock()
        voice.check_connection = False
        voice.ocb.ui_good = voice.ocb.ui_late = voice.ocb.ui_lost = 0
        ping.set_control(control)
        ping.set_voice(voice)
        return ping, control

    def test_timeout_after_a_minute_without_answers(self):
        ping, control = self.make_ping()
        ping.tcp.last_received = 1000.0
        with mock.patch.object(ping_module, "time", return_value=1000.0 + Ping.TIMEOUT + 1):
            ping.send()
        control.timeout.assert_called_once()

    def test_timeout_without_any_answer_since_the_start(self):
        ping, control = self.make_ping()
        ping.tcp.started = 1000.0
        with mock.patch.object(ping_module, "time", return_value=1000.0 + Ping.TIMEOUT + 1):
            ping.send()
        control.timeout.assert_called_once()

    def test_no_timeout_while_answers_come(self):
        ping, control = self.make_ping()
        ping.tcp.last_received = 1000.0
        with mock.patch.object(ping_module, "time", return_value=1000.0 + Ping.DELAY):
            ping.send()
        control.timeout.assert_not_called()


if __name__ == "__main__":
    unittest.main()
