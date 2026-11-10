"""Intent to handler routing. The integration seam for module owners."""

from collections.abc import Callable

Handler = Callable[..., dict]

_HANDLERS: dict[str, Handler] = {}


def register(intent: str, handler: Handler) -> None:
    _HANDLERS[intent] = handler


def resolve(intent: str) -> Handler | None:
    return _HANDLERS.get(intent)


def routed_action(intent: str) -> str:
    return f"{intent}_planning" if intent in _HANDLERS else "human_triage"


def registered_intents() -> tuple[str, ...]:
    return tuple(sorted(_HANDLERS))
