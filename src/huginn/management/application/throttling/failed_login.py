"""Process-local fixed-window throttling for failed management logins."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import RLock

from huginn.management.application.errors.errors import RateLimitError


@dataclass(eq=False)
class _Window:
    started: datetime
    failures: int = 0
    reservations: set[object] = field(default_factory=set)


@dataclass(frozen=True)
class LoginReservation:
    """A slot held while one password verification is in progress."""

    key: tuple[str, str]
    window: _Window
    token: object


class FailedLoginThrottle:
    """Count failures by client IP and normalized username in fixed windows.

    State is process-local, so this adapter is intended for one process until a
    shared store is configured.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        max_failures: int = 5,
        window: timedelta = timedelta(minutes=15),
    ) -> None:
        if max_failures < 1 or window <= timedelta(0):
            raise ValueError("throttle limits must be positive")
        self._clock = clock or (lambda: datetime.now(UTC))
        self._max_failures = max_failures
        self._window = window
        self._windows: dict[tuple[str, str], _Window] = {}
        self._lock = RLock()

    @staticmethod
    def _key(client_ip: str, username: str) -> tuple[str, str]:
        return client_ip.strip(), username.strip().lower()

    def _current(self, key: tuple[str, str], now: datetime) -> _Window | None:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("throttle clock must return a timezone-aware datetime")
        for expired_key, state in tuple(self._windows.items()):
            if now >= state.started + self._window:
                del self._windows[expired_key]
        state = self._windows.get(key)
        if state is not None and now >= state.started + self._window:
            del self._windows[key]
            return None
        return state

    def reserve(self, client_ip: str, username: str) -> LoginReservation:
        """Atomically reserve one attempt before password verification."""
        with self._lock:
            key = self._key(client_ip, username)
            now = self._clock()
            state = self._current(key, now)
            if state is None:
                state = _Window(now)
                self._windows[key] = state
            if state.failures + len(state.reservations) >= self._max_failures:
                raise RateLimitError("login attempts are temporarily limited")
            token = object()
            state.reservations.add(token)
            return LoginReservation(key, state, token)

    def is_limited(self, client_ip: str, username: str) -> bool:
        with self._lock:
            state = self._current(self._key(client_ip, username), self._clock())
            return state is not None and (
                state.failures + len(state.reservations) >= self._max_failures
            )

    def check(self, client_ip: str, username: str) -> None:
        if self.is_limited(client_ip, username):
            raise RateLimitError("login attempts are temporarily limited")

    def record_failure(
        self,
        client_ip: str,
        username: str,
        reservation: LoginReservation | None = None,
    ) -> None:
        with self._lock:
            if reservation is not None:
                state = self._take_reservation(reservation)
                if state is not None:
                    state.failures += 1
                return
            key = self._key(client_ip, username)
            now = self._clock()
            state = self._current(key, now)
            if state is None:
                state = _Window(now)
                self._windows[key] = state
            state.failures += 1

    def record_success(
        self,
        client_ip: str,
        username: str,
        reservation: LoginReservation | None = None,
    ) -> None:
        with self._lock:
            if reservation is None:
                self._windows.pop(self._key(client_ip, username), None)
                return
            state = self._take_reservation(reservation)
            if state is not None:
                state.failures = 0
                if not state.reservations:
                    self._windows.pop(reservation.key, None)

    def release(self, reservation: LoginReservation) -> None:
        """Release a slot when downstream login work fails unexpectedly."""
        with self._lock:
            state = self._take_reservation(reservation)
            if state is not None and not state.failures and not state.reservations:
                self._windows.pop(reservation.key, None)

    def _take_reservation(self, reservation: LoginReservation) -> _Window | None:
        state = self._windows.get(reservation.key)
        if (
            state is not reservation.window
            or reservation.token not in state.reservations
        ):
            return None
        state.reservations.remove(reservation.token)
        return state
