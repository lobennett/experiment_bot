"""KeypressDeliverer — abstract interface for firing keys + reading
back what the platform recorded.

Phase 3 defines the abstraction and provides a mock implementation for
testing the calibration estimator without browser state. Phase 4
provides the real implementations (CDP-level Input.dispatchKeyEvent
plus a page.keyboard.press fallback for non-Chromium engines).

The calibration logic in :mod:`experiment_bot.calibration.estimator`
only ever sees this interface — never `page.keyboard.press`,
`page.evaluate`, or any other Playwright API. That keeps the
estimator testable in pure Python and lets Phase 4 swap in the real
delivery channels without touching estimator logic.

The reverse direction also matters: the deliverer reads back what
the platform recorded. The mock implementation lets tests inject
synthetic platform RTs with controlled offsets and noise.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class KeypressEvent:
    """A single calibration keypress: the bot pressed ``key`` at
    ``bot_intended_rt_ms`` after some reference timepoint, and the
    platform later recorded its own observation in
    ``platform_recorded_key`` / ``platform_recorded_rt_ms``.

    Either platform field may be ``None`` if the platform didn't
    record the keypress at all (e.g. fired during a non-listening
    state, or the platform's response window had already closed).

    The calibration estimator uses these events; see
    :mod:`experiment_bot.calibration.estimator` for the (mean, sd)
    offset computation and the bimodality + regression fallbacks.
    """
    key: str
    bot_intended_rt_ms: float
    platform_recorded_key: str | None
    platform_recorded_rt_ms: float | None
    # Optional metadata the deliverer may attach (e.g., delivery_channel
    # from Phase 4's CDP-vs-fallback split, raw timestamps, etc.).
    metadata: dict = field(default_factory=dict)

    @property
    def is_correctly_recorded(self) -> bool:
        """True iff the platform recorded a key AND the recorded key
        matches what the bot intended.

        The SP7 layer-d finding showed 44% of bot keypresses register
        as a different key in the platform. The calibration estimator
        MUST filter on this property — pre-SP11 work that estimated
        offset across all keypresses included the mis-recorded ones,
        polluting the offset and inflating its SD.
        """
        return (self.platform_recorded_key is not None
                and self.platform_recorded_key == self.key)


class KeypressDeliverer(ABC):
    """Abstract interface for the calibration pass.

    A concrete implementation:
      1. Fires a sequence of keys at controlled intervals.
      2. After each fire, records the bot's intended RT (the time
         between the calibration-phase reference clock and the
         dispatch).
      3. After all keys fire, reads back the platform's recorded
         keypresses (e.g. via jsPsych.data.get().values()) and
         pairs each platform observation with the bot's intended
         event.
      4. Returns the list of paired :class:`KeypressEvent`.

    Phase 3 provides:
      - :class:`MockDeliverer` — deterministic with configurable
        per-event offset + noise + drop rate.

    Phase 4 provides:
      - ``CDPDeliverer`` — fires via Chrome DevTools Protocol
        ``Input.dispatchKeyEvent`` with proper key/code/keyCode.
        This is the only surviving production deliverer; if a CDP
        session can't be acquired the executor falls through to
        ``page.keyboard.press``.
    """

    @abstractmethod
    async def deliver_sequence(
        self,
        keys: list[str],
        target_intervals_ms: list[float],
    ) -> list[KeypressEvent]:
        """Fire ``keys[i]`` at approximately ``target_intervals_ms[i]``
        relative to the previous fire (or t=0 for the first). After
        all keys fire, read back the platform's recorded responses
        and pair them with the bot's intended events.

        Returns one :class:`KeypressEvent` per intended fire, in the
        same order as ``keys``. Events whose platform observation is
        unrecoverable have ``platform_recorded_key=None`` and
        ``platform_recorded_rt_ms=None``.

        The deliverer must NOT raise on platform-side failures
        (no-recording, mis-recording, etc.) — the calibration estimator
        filters those events, surfaces the rates in its report, and
        decides whether to retry or escalate.
        """
        raise NotImplementedError


class MockDeliverer(KeypressDeliverer):
    """Test deliverer with controlled platform-side behavior.

    Construct with:
      - ``recording_offset_mean_ms`` and ``recording_offset_sd_ms``:
        the platform records each event at
        ``bot_intended_rt + N(mean, sd)`` ms.
      - ``drop_rate``: probability the platform fails to record a
        keypress at all (sets platform fields to None).
      - ``misrecording_rate``: probability the platform records a
        DIFFERENT key for a given fire (a non-bot key). Models the
        SP7 layer-d finding (~56% mis-recording on Flanker).
      - ``bimodal_second_mode``: when set to a tuple
        ``(second_offset_mean_ms, second_mode_prob)``, the platform
        offset is drawn from a mixture — useful for testing the
        bimodality detector. Default ``None`` (unimodal).

    The mock fires "instantly" (no real time elapses); the
    ``target_intervals_ms`` argument controls the bot's RECORDED
    intended RT, not real wall-clock time. This keeps tests fast
    and deterministic.
    """

    def __init__(
        self,
        *,
        recording_offset_mean_ms: float = 0.0,
        recording_offset_sd_ms: float = 0.0,
        drop_rate: float = 0.0,
        misrecording_rate: float = 0.0,
        bimodal_second_mode: tuple[float, float] | None = None,
        misrecording_alt_keys: Iterable[str] = (",", ".", " ", "Enter"),
        seed: int | None = None,
    ):
        import random
        self._offset_mean = recording_offset_mean_ms
        self._offset_sd = recording_offset_sd_ms
        self._drop_rate = drop_rate
        self._misrec_rate = misrecording_rate
        self._bimodal = bimodal_second_mode
        self._alt_keys = list(misrecording_alt_keys)
        self._rng = random.Random(seed if seed is not None else 0)

    async def deliver_sequence(
        self,
        keys: list[str],
        target_intervals_ms: list[float],
    ) -> list[KeypressEvent]:
        if len(keys) != len(target_intervals_ms):
            raise ValueError(
                f"keys and target_intervals_ms must be same length: "
                f"got {len(keys)} and {len(target_intervals_ms)}"
            )
        events: list[KeypressEvent] = []
        cumulative_t = 0.0
        for k, dt in zip(keys, target_intervals_ms):
            cumulative_t += dt
            bot_rt = cumulative_t

            # Decide whether the platform records this event at all
            if self._rng.random() < self._drop_rate:
                events.append(KeypressEvent(
                    key=k, bot_intended_rt_ms=bot_rt,
                    platform_recorded_key=None, platform_recorded_rt_ms=None,
                ))
                continue

            # Decide whether to mis-record (wrong key)
            if self._rng.random() < self._misrec_rate:
                # Pick an alt key that's not the bot's pressed key
                alts = [a for a in self._alt_keys if a != k]
                platform_key = self._rng.choice(alts) if alts else k
            else:
                platform_key = k

            # Pick the offset (bimodal mixture if configured)
            if self._bimodal is not None:
                second_mean, second_prob = self._bimodal
                if self._rng.random() < second_prob:
                    offset = self._rng.gauss(second_mean, self._offset_sd)
                else:
                    offset = self._rng.gauss(self._offset_mean, self._offset_sd)
            else:
                offset = self._rng.gauss(self._offset_mean, self._offset_sd)

            events.append(KeypressEvent(
                key=k, bot_intended_rt_ms=bot_rt,
                platform_recorded_key=platform_key,
                platform_recorded_rt_ms=bot_rt + offset,
                metadata={"mock_offset_ms": offset},
            ))
        return events
