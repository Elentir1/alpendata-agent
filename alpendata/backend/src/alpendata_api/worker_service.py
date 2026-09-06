"""Worker process lifecycle: drain an admitted iteration before stopping."""

import json
import select
import signal
import socket
import time
from contextlib import contextmanager
from dataclasses import dataclass

from .database import database_factory
from .health import database_ready, release_head
from .settings import Settings


def event(service, status):
    print(json.dumps({"service": service, "status": status}), flush=True)


@contextmanager
def stop_signals():
    reader, writer = socket.socketpair()
    reader.setblocking(False)
    writer.setblocking(False)
    stopping = StopRequest(reader)
    previous = {}
    previous_fd = signal.set_wakeup_fd(writer.fileno(), warn_on_full_buffer=False)

    def stop(_number, _frame):
        # A signal handler must not acquire an Event/Condition lock held by its own interrupted thread.
        stopping.requested = True

    try:
        for number in (signal.SIGTERM, signal.SIGINT):
            previous[number] = signal.signal(number, stop)
        yield stopping
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
        signal.set_wakeup_fd(previous_fd)
        reader.close()
        writer.close()


@dataclass
class StopRequest:
    reader: socket.socket
    requested: bool = False

    def wait(self, seconds):
        deadline = time.monotonic() + seconds
        while not self.requested:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            if select.select([self.reader], [], [], remaining)[0]:
                self.reader.recv(4096)


def run_loop(engine, step, *, service, interval, delay_when_idle=False):
    try:
        with stop_signals() as stopping:
            if not database_ready(engine, release_head()):
                event(service, "database_unavailable")
                return 1
            event(service, "ready")
            while not stopping.requested:
                processed = step()
                if not delay_when_idle or not processed:
                    stopping.wait(interval)
            event(service, "stopped")
            return 0
    except Exception:
        # The supervisor needs a failure status, never SQL parameters or service credentials.
        event(service, "failed")
        return 1


def main(service):
    from .chat_worker import ChatWorker
    from .schedule_worker import ScheduleWorker

    constructors = {
        "chat": (ChatWorker, "run_once", 1, True),
        "scheduler": (ScheduleWorker, "tick", 30, False),
    }
    engine = None
    try:
        settings = Settings.from_environment()
        if not settings.chat_enabled:
            raise ValueError("Workers require model and runtime settings")
        engine, factory = database_factory(settings.database_url)
        constructor, method, interval, idle = constructors[service]
        worker = constructor(settings, factory)
        return run_loop(
            engine, getattr(worker, method), service=service, interval=interval, delay_when_idle=idle
        )
    except Exception:
        event(service, "configuration_failed")
        return 1
    finally:
        if engine is not None:
            engine.dispose()
