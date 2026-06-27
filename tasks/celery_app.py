"""
tasks/celery_app.py - Celery application instance for betatp.io

Broker  : Redis at redis://localhost:6379/0
Backend : Redis at redis://localhost:6379/0
Timezone: Europe/Warsaw

If Celery is not installed, a lightweight stub is created so that
importing this module never raises ImportError.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

BROKER_URL    = "redis://localhost:6379/0"
RESULT_BACKEND = "redis://localhost:6379/0"

CELERY_AVAILABLE = False

try:
    from celery import Celery
    CELERY_AVAILABLE = True
except ImportError:
    Celery = None  # type: ignore[assignment,misc]


if CELERY_AVAILABLE and Celery is not None:
    app = Celery(
        "betatp",
        broker=BROKER_URL,
        backend=RESULT_BACKEND,
    )
    app.config_from_object({
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],
        "timezone": "Europe/Warsaw",
        "enable_utc": True,
    })

else:
    # ---- Stub: Celery is not installed --------------------------------
    import warnings
    warnings.warn(
        "Celery is not installed. Task decorators will run synchronously.",
        ImportWarning,
        stacklevel=2,
    )

    class _TaskStub:
        """Wraps a plain function so it can be called like a Celery task."""

        def __init__(self, fn):
            self._fn = fn
            self.__name__   = fn.__name__
            self.__doc__    = fn.__doc__
            self.__module__ = fn.__module__

        def __call__(self, *args, **kwargs):
            return self._fn(*args, **kwargs)

        def delay(self, *args, **kwargs):
            logger.warning(
                "Celery not available -- running task %s synchronously.",
                self.__name__,
            )
            return self._fn(*args, **kwargs)

        def apply_async(self, args=None, kwargs=None, **options):
            logger.warning(
                "Celery not available -- running task %s synchronously.",
                self.__name__,
            )
            return self._fn(*(args or []), **(kwargs or {}))

        def __repr__(self):
            return f"<StubTask: {self.__name__}>"

    class _StubCelery:
        """Minimal Celery stand-in that records tasks without executing them."""

        def __init__(self, name: str):
            self.name = name
            logger.warning(
                "StubCelery(%r) instantiated -- Celery is not installed.",
                name,
            )

        def task(self, *args, **kwargs):
            """Decorator: works both as @app.task and @app.task(...)."""
            if len(args) == 1 and callable(args[0]):
                # Bare decorator: @app.task
                return _TaskStub(args[0])

            # With arguments: @app.task(bind=True, ...)
            def _decorator(fn):
                return _TaskStub(fn)

            return _decorator

        def config_from_object(self, obj):
            pass  # no-op

    app = _StubCelery("betatp")


__all__ = ["app", "CELERY_AVAILABLE", "BROKER_URL", "RESULT_BACKEND"]
