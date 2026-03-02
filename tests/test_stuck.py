import time
from unittest.mock import patch

from experiment_bot.navigation.stuck import StuckDetector


def test_stuck_detector_not_stuck_after_heartbeat():
    """Heartbeat resets the timer — detector should not be stuck."""
    detector = StuckDetector(timeout_seconds=0.2)
    detector.heartbeat()
    assert not detector.is_stuck
    assert detector.seconds_since_heartbeat < 0.1


def test_stuck_detector_fires_after_timeout():
    """Detector reports stuck after timeout elapses without heartbeat."""
    detector = StuckDetector(timeout_seconds=0.05)
    time.sleep(0.1)
    assert detector.is_stuck
    assert detector.seconds_since_heartbeat >= 0.05


def test_stuck_detector_heartbeat_resets_timer():
    """Heartbeat after becoming stuck resets the detector."""
    detector = StuckDetector(timeout_seconds=0.05)
    time.sleep(0.1)
    assert detector.is_stuck

    detector.heartbeat()
    assert not detector.is_stuck
