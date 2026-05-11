"""Polling scheduler. Ticks the automation engine every N seconds."""

import threading

from agent_core.constants import SCHEDULER_TICK_INTERVAL_SECONDS


class Scheduler:
    def __init__(self, engine, interval: float = SCHEDULER_TICK_INTERVAL_SECONDS):
        self.engine = engine
        self.interval = interval
        self._stop = threading.Event()

    def start(self) -> None:
        while not self._stop.is_set():
            try:
                self.engine.tick()
            except Exception as e:
                print(f"[scheduler error] {e}")
            # Use wait() so stop() can interrupt sleep
            self._stop.wait(self.interval)

    def stop(self) -> None:
        self._stop.set()
