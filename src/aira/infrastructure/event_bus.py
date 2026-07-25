"""Enterprise Event Bus for AIRA.

Provides synchronous and asynchronous message routing, wildcard matching,
filtering, middleware chains, and subscriber tracking.
"""

import asyncio
import fnmatch
import inspect
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal

import structlog

logger = structlog.get_logger("aira.events")

EventPriorityType = Literal["CRITICAL", "HIGH", "NORMAL", "LOW", "BACKGROUND"]
EventStatusType = Literal[
    "Created", "Validated", "Published", "Delivered", "Processed", "Completed", "Failed"
]


class EventBusError(Exception):
    """Base exception for all event bus failures."""

    pass


class InvalidEventError(EventBusError):
    """Raised when validating events with invalid payload formats."""

    pass


class MiddlewareError(EventBusError):
    """Raised when a middleware execution raises an unhandled exception."""

    pass


class Event:
    """Standardized message payload structure dispatched across the system."""

    def __init__(
        self,
        name: str,
        category: str,
        source: str,
        payload: dict[str, Any],
        priority: EventPriorityType = "NORMAL",
        target: str | None = None,
        correlation_id: str | None = None,
        session_id: str | None = None,
        version: str = "1.0.0",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.id = str(uuid.uuid4())
        self.name = name
        self.category = category
        self.source = source
        self.payload = payload
        self.priority = priority
        self.target = target
        self.correlation_id = correlation_id
        self.session_id = session_id
        self.version = version
        self.metadata = metadata or {}
        self.timestamp = datetime.now()
        self.status: EventStatusType = "Created"

    def transition_to(self, status: EventStatusType) -> None:
        """Update and record the event lifecycle status."""
        self.status = status


class Subscriber:
    """Wrapper tracking subscriber handlers, matches, and temporary states."""

    def __init__(
        self,
        pattern: str,
        handler: Callable[[Event], Any],
        filter_func: Callable[[Event], bool] | None = None,
        is_temporary: bool = False,
    ) -> None:
        self.pattern = pattern
        self.handler = handler
        self.filter_func = filter_func
        self.is_temporary = is_temporary

    def matches(self, event: Event) -> bool:
        """Check if subscriber pattern and custom filter matches the event."""
        # Use shell wildcard matching (e.g. aira.security.* matches aira.security.unauthorized)
        if not fnmatch.fnmatch(event.name, self.pattern):
            return False
        if self.filter_func:
            try:
                return self.filter_func(event)
            except Exception as e:
                logger.error(
                    "Subscriber filter evaluation failed", pattern=self.pattern, error=str(e)
                )
                return False
        return True


class EventBus:
    """Enterprise-grade Event Bus orchestrating async/sync event dispatches and middleware."""

    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []
        self._middlewares: list[Callable[[Event, Callable[[Event], Any]], Any]] = []

        # Diagnostics metrics
        self._published_count = 0
        self._failed_count = 0
        self._dropped_count = 0
        self._categories_seen: set[str] = set()

    def subscribe(
        self,
        pattern: str,
        handler: Callable[[Event], Any],
        filter_func: Callable[[Event], bool] | None = None,
        is_temporary: bool = False,
    ) -> None:
        """Register a handler to listen to events matching wildcard patterns."""
        subscriber = Subscriber(pattern, handler, filter_func, is_temporary)
        self._subscribers.append(subscriber)
        logger.debug("Registered subscriber pattern", pattern=pattern, is_temporary=is_temporary)

    def unsubscribe(self, pattern: str, handler: Callable[[Event], Any]) -> None:
        """Unregister a previously matched subscriber handler."""
        original_len = len(self._subscribers)
        self._subscribers = [
            s for s in self._subscribers if not (s.pattern == pattern and s.handler == handler)
        ]
        removed_count = original_len - len(self._subscribers)
        logger.debug("Removed subscriber pattern", pattern=pattern, removed_count=removed_count)

    def add_middleware(self, middleware: Callable[[Event, Callable[[Event], Any]], Any]) -> None:
        """Add an execution wrapper middleware intercepting event flows."""
        self._middlewares.append(middleware)
        logger.debug("Added middleware to event bus")

    def publish_sync(self, event: Event) -> None:
        """Publish an event to all matching subscribers synchronously."""
        self._published_count += 1
        self._categories_seen.add(event.category)
        event.transition_to("Published")

        matching_subs = [s for s in self._subscribers if s.matches(event)]
        if not matching_subs:
            self._dropped_count += 1
            event.transition_to("Delivered")
            return

        for sub in matching_subs:
            event.transition_to("Delivered")

            # Form handler invocation wrapped with middleware chains
            def make_handler(subscriber: Subscriber) -> Callable[[Event], Any]:
                return lambda ev: subscriber.handler(ev)

            try:
                self._dispatch_with_middleware(event, make_handler(sub))
                event.transition_to("Completed")
            except Exception as e:
                self._failed_count += 1
                event.transition_to("Failed")
                logger.error(
                    "Subscriber sync processing failed",
                    event=event.name,
                    pattern=sub.pattern,
                    error=str(e),
                )

            # Cleanup temporary subscriptions
            if sub.is_temporary:
                self.unsubscribe(sub.pattern, sub.handler)

    async def publish_async(self, event: Event) -> None:
        """Asynchronously dispatch events, preventing blocking execution chains."""
        self._published_count += 1
        self._categories_seen.add(event.category)
        event.transition_to("Published")

        matching_subs = [s for s in self._subscribers if s.matches(event)]
        if not matching_subs:
            self._dropped_count += 1
            event.transition_to("Delivered")
            return

        # Execute in non-blocking async loops
        async def run_sub(sub: Subscriber) -> None:
            event.transition_to("Delivered")

            def make_handler(subscriber: Subscriber) -> Callable[[Event], Any]:
                return lambda ev: subscriber.handler(ev)

            try:
                # Middleware execution
                res = self._dispatch_with_middleware(event, make_handler(sub))
                if inspect.iscoroutine(res) or asyncio.iscoroutine(res):
                    await res
                event.transition_to("Completed")
            except Exception as e:
                self._failed_count += 1
                event.transition_to("Failed")
                logger.error(
                    "Subscriber async processing failed",
                    event=event.name,
                    pattern=sub.pattern,
                    error=str(e),
                )
            finally:
                if sub.is_temporary:
                    self.unsubscribe(sub.pattern, sub.handler)

        tasks = [asyncio.create_task(run_sub(sub)) for sub in matching_subs]
        await asyncio.gather(*tasks, return_exceptions=True)

    def _dispatch_with_middleware(self, event: Event, final_handler: Callable[[Event], Any]) -> Any:
        """Wrap final handler inside sequential middleware chains (FIFO execution)."""
        next_call = final_handler
        for middleware in reversed(self._middlewares):

            def make_next(
                mw: Callable[[Event, Callable[[Event], Any]], Any], nc: Callable[[Event], Any]
            ) -> Callable[[Event], Any]:
                return lambda ev: mw(ev, nc)

            next_call = make_next(middleware, next_call)

        try:
            return next_call(event)
        except Exception as e:
            raise MiddlewareError(f"Middleware chain execution failed: {e}") from e

    def get_diagnostics(self) -> dict[str, Any]:
        """Expose statistical overview mapping active subscriptions and events."""
        return {
            "total_subscribers": len(self._subscribers),
            "published_events": self._published_count,
            "failed_events": self._failed_count,
            "dropped_events": self._dropped_count,
            "categories": list(self._categories_seen),
            "middlewares_count": len(self._middlewares),
        }

    def clear(self) -> None:
        """Reset diagnostics metrics and unregister all subscribers."""
        self._subscribers.clear()
        self._middlewares.clear()
        self._published_count = 0
        self._failed_count = 0
        self._dropped_count = 0
        self._categories_seen.clear()
        logger.debug("Cleared Event Bus registries")
