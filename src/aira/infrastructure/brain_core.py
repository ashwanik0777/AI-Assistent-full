"""Enterprise Brain Core Layer for AIRA.

Acts as the central decision coordinator, receiving standardized Runtime Requests,
managing Brain session contexts and queues, and dispatching requests to future planners.
"""

import contextlib
import heapq
import uuid
from datetime import datetime
from typing import Any, ClassVar, Literal

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.request_normalization import RuntimeRequest
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.brain")

BrainState = Literal[
    "IDLE",
    "RECEIVING",
    "VALIDATING",
    "PROCESSING",
    "WAITING",
    "READY",
    "FAILED",
    "RECOVERING",
    "SHUTTING_DOWN",
]


class BrainCoreError(Exception):
    """Base exception for all Brain Core failures."""

    pass


class InvalidBrainStateError(BrainCoreError):
    """Raised when trying to perform an invalid brain state transition."""

    pass


class BrainContext:
    """Consolidated state metadata mapping the active execution request context."""

    def __init__(
        self,
        brain_session_id: str,
        request_id: str,
        voice_session_id: str,
        language: str,
        priority: int,
        current_state: BrainState,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.brain_session_id = brain_session_id
        self.request_id = request_id
        self.voice_session_id = voice_session_id
        self.timestamp: datetime = datetime.now()
        self.language = language
        self.priority = priority
        self.current_state: BrainState = current_state
        self.metadata: dict[str, Any] = metadata or {}
        # Future-proofing extensions
        self.future_user_context: dict[str, Any] = {}
        self.future_memory_context: dict[str, Any] = {}
        self.future_ai_context: dict[str, Any] = {}
        self.future_goal_context: dict[str, Any] = {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize brain context properties."""
        return {
            "brain_session_id": self.brain_session_id,
            "request_id": self.request_id,
            "voice_session_id": self.voice_session_id,
            "timestamp": self.timestamp.isoformat(),
            "language": self.language,
            "priority": self.priority,
            "current_state": self.current_state,
            "metadata": self.metadata,
        }


class BrainSession:
    """Lifecycle controller representing one active reasoning workflow sequence."""

    def __init__(self, session_id: str, request_id: str) -> None:
        self.session_id = session_id
        self.request_id = request_id
        self.created_at: datetime = datetime.now()
        self.updated_at: datetime = datetime.now()
        self.is_completed: bool = False
        self.is_failed: bool = False

    def update(self) -> None:
        """Mark refresh time indicator."""
        self.updated_at = datetime.now()

    def complete(self) -> None:
        """Close session successfully."""
        self.is_completed = True
        self.update()

    def fail(self) -> None:
        """Close session with error indicator."""
        self.is_failed = True
        self.update()


class BrainRequestQueue:
    """Thread-safe priority request queue maintaining sorted execution orders."""

    def __init__(self) -> None:
        # Heap elements: (-priority, entry_counter, request_object)
        self._queue: list[tuple[int, int, RuntimeRequest]] = []
        self._counter: int = 0

    def push(self, request: RuntimeRequest) -> None:
        """Insert runtime request matching designated priority levels (higher first)."""
        self._counter += 1
        heapq.heappush(self._queue, (-request.priority, self._counter, request))

    def pop(self) -> RuntimeRequest:
        """Remove and return the highest priority request."""
        if not self._queue:
            raise BrainCoreError("Cannot pop from empty request queue.")
        return heapq.heappop(self._queue)[2]

    def peek(self) -> RuntimeRequest | None:
        """View the next highest priority request without extraction."""
        if not self._queue:
            return None
        return self._queue[0][2]

    def cancel(self, request_id: str) -> bool:
        """Filter out and delete specific request matching unique ID."""
        orig_len = len(self._queue)
        self._queue = [item for item in self._queue if item[2].request_id != request_id]
        heapq.heapify(self._queue)
        return len(self._queue) < orig_len

    @property
    def size(self) -> int:
        """Get length of active requests."""
        return len(self._queue)


class BrainStateManager:
    """Validates state machine transitions for the Brain Engine."""

    VALID_TRANSITIONS: ClassVar[dict[BrainState, list[BrainState]]] = {
        "IDLE": ["RECEIVING", "SHUTTING_DOWN"],
        "RECEIVING": ["VALIDATING", "FAILED"],
        "VALIDATING": ["PROCESSING", "FAILED"],
        "PROCESSING": ["WAITING", "READY", "FAILED"],
        "WAITING": ["PROCESSING", "FAILED"],
        "READY": ["IDLE", "SHUTTING_DOWN"],
        "FAILED": ["RECOVERING", "SHUTTING_DOWN"],
        "RECOVERING": ["IDLE", "FAILED"],
        "SHUTTING_DOWN": [],
    }

    def __init__(self) -> None:
        self._state: BrainState = "IDLE"

    @property
    def current_state(self) -> BrainState:
        """Fetch active brain state."""
        return self._state

    def transition_to(self, new_state: BrainState) -> None:
        """Execute state machine validation. Raises InvalidBrainStateError on fault."""
        allowed = self.VALID_TRANSITIONS.get(self._state, [])
        if new_state not in allowed:
            raise InvalidBrainStateError(
                f"Transition from {self._state} to {new_state} is illegal."
            )
        old_state = self._state
        self._state = new_state
        logger.info("Brain state transitioned", old_state=old_state, new_state=new_state)


class BrainValidator:
    """Ensures input parameters are strictly validated RuntimeRequest instances."""

    @staticmethod
    def validate_request(request: Any) -> None:
        """Confirm object type match. Raises BrainCoreError on failure."""
        if not isinstance(request, RuntimeRequest):
            raise BrainCoreError(f"Input must be of type RuntimeRequest. Received: {type(request)}")


class BrainDispatcher:
    """Dispatches requests to future planners, router engines, and memory layers."""

    def __init__(self) -> None:
        pass

    def dispatch_to_planner(self, context: BrainContext) -> None:
        """Hook preparing workflow details for future Planner Engine integrations."""
        logger.info(
            "Forwarding request to planning pipeline placeholder",
            request_id=context.request_id,
            session_id=context.brain_session_id,
        )


class BrainManager:
    """Central orchestrator managing contexts, state changes, dispatches, and events."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.state_manager = BrainStateManager()
        self.validator = BrainValidator()
        self.queue = BrainRequestQueue()
        self.dispatcher = BrainDispatcher()

        self.active_session: BrainSession | None = None
        self.active_context: BrainContext | None = None

        # Publish initial start indicator
        self.event_bus.publish_sync(
            Event(
                name="brain.started",
                category="Brain",
                source="BrainManager",
                payload={"status": "INITIALIZED"},
            )
        )
        self.state_manager.transition_to("RECEIVING")
        self.state_manager.transition_to("VALIDATING")
        self.state_manager.transition_to("PROCESSING")
        self.state_manager.transition_to("READY")
        self.state_manager.transition_to("IDLE")

        self.event_bus.publish_sync(
            Event(
                name="brain.ready",
                category="Brain",
                source="BrainManager",
                payload={"status": "READY"},
            )
        )

    def process_request(self, request: RuntimeRequest) -> BrainContext:
        """Validate request structure, queue if processing is active, and update session."""
        # 1. Validation check
        self.validator.validate_request(request)

        self.state_manager.transition_to("RECEIVING")

        # 2. Dispatch Request Received
        self.event_bus.publish_sync(
            Event(
                name="brain.request_received",
                category="Brain",
                source="BrainManager",
                payload={"request_id": request.request_id},
            )
        )

        try:
            self.state_manager.transition_to("VALIDATING")

            self.event_bus.publish_sync(
                Event(
                    name="brain.request_validated",
                    category="Brain",
                    source="BrainManager",
                    payload={"request_id": request.request_id},
                )
            )

            # 3. Create Session
            brain_session_id = uuid.uuid4().hex
            self.active_session = BrainSession(brain_session_id, request.request_id)

            self.event_bus.publish_sync(
                Event(
                    name="brain.session_created",
                    category="Brain",
                    source="BrainManager",
                    payload={"session_id": brain_session_id, "request_id": request.request_id},
                )
            )

            # 4. Processing context creation
            self.state_manager.transition_to("PROCESSING")
            context = BrainContext(
                brain_session_id=brain_session_id,
                request_id=request.request_id,
                voice_session_id=request.session_id,
                language=request.language,
                priority=request.priority,
                current_state="PROCESSING",
            )
            self.active_context = context

            # 5. Push request to internal Queue
            self.queue.push(request)
            self.event_bus.publish_sync(
                Event(
                    name="brain.request_queued",
                    category="Brain",
                    source="BrainManager",
                    payload={"request_id": request.request_id, "priority": request.priority},
                )
            )

            # 6. Dispatch and notify planner hook
            self.dispatcher.dispatch_to_planner(context)

            # Mark session as completed
            self.active_session.complete()
            self.state_manager.transition_to("READY")
            self.state_manager.transition_to("IDLE")

            return context

        except Exception as e:
            logger.error("Brain processing pipeline failed", error=str(e))
            if self.active_session:
                self.active_session.fail()

            self.event_bus.publish_sync(
                Event(
                    name="brain.failed",
                    category="Brain",
                    source="BrainManager",
                    payload={"error": str(e)},
                )
            )

            # Transition to FAILED state safely
            with contextlib.suppress(Exception):
                self.state_manager.transition_to("FAILED")
            raise BrainCoreError(f"Brain failed to coordinate request: {e}") from e

    def shutdown(self) -> None:
        """Gracefully transition brain elements to SHUTTING_DOWN state."""
        with contextlib.suppress(Exception):
            self.state_manager.transition_to("SHUTTING_DOWN")
        self.event_bus.publish_sync(
            Event(
                name="brain.shutdown",
                category="Brain",
                source="BrainManager",
                payload={"status": "SHUTDOWN"},
            )
        )
