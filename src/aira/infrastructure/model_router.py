"""Enterprise Model Router for AIRA.

Manages AI model provider abstraction adapters, registry life-cycles,
routing policies, selector matches, and dispatch pipelines.
"""

from abc import ABC, abstractmethod
from typing import Any, Literal

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.model_router")

RoutingPolicy = Literal[
    "OFFLINE_FIRST",
    "CLOUD_PREFERRED",
    "LOCAL_ONLY",
    "CLOUD_ONLY",
    "BEST_PERFORMANCE",
    "LOWEST_COST",
    "LOWEST_LATENCY",
    "PRIVACY_FIRST",
    "BALANCED",
]


class ModelRouterError(Exception):
    """Base exception for all Model Router failures."""

    pass


class ModelProviderMetadata:
    """Metadata parameters exposing provider capabilties and properties."""

    def __init__(
        self,
        provider_id: str,
        provider_name: str,
        version: str,
        capabilities: list[str],
        supported_languages: list[str],
        max_context: int = 4096,
        streaming_support: bool = False,
        vision_support: bool = False,
        reasoning_support: bool = False,
        is_local: bool = False,
        health_status: str = "HEALTHY",
    ) -> None:
        self.provider_id = provider_id
        self.provider_name = provider_name
        self.version = version
        self.capabilities = capabilities
        self.supported_languages = supported_languages
        self.max_context = max_context
        self.streaming_support = streaming_support
        self.vision_support = vision_support
        self.reasoning_support = reasoning_support
        self.is_local = is_local
        self.health_status = health_status

    def to_dict(self) -> dict[str, Any]:
        """Serialize metadata attributes."""
        return {
            "provider_id": self.provider_id,
            "provider_name": self.provider_name,
            "version": self.version,
            "capabilities": self.capabilities,
            "supported_languages": self.supported_languages,
            "max_context": self.max_context,
            "streaming_support": self.streaming_support,
            "vision_support": self.vision_support,
            "reasoning_support": self.reasoning_support,
            "is_local": self.is_local,
            "health_status": self.health_status,
        }


class ModelProvider(ABC):
    """Abstract interface defining the execution contract for all AI model adapters."""

    def __init__(self, metadata: ModelProviderMetadata) -> None:
        self.metadata = metadata
        self.is_active: bool = False

    @abstractmethod
    def initialize(self) -> None:
        """Lifecycle call to initialize parameters."""
        pass

    @abstractmethod
    def validate(self) -> bool:
        """Lifecycle validation verification check."""
        pass

    @abstractmethod
    def generate_response(self, prompt: str) -> str:
        """Call model execution flow placeholder."""
        pass


class OpenAIProvider(ModelProvider):
    """Placeholder adapter for OpenAI Cloud Models."""

    def initialize(self) -> None:
        logger.info("Initializing OpenAI Cloud Provider")

    def validate(self) -> bool:
        return self.metadata.health_status == "HEALTHY"

    def generate_response(self, prompt: str) -> str:
        return f"[OpenAI Cloud Model Response to: {prompt}]"


class GeminiProvider(ModelProvider):
    """Placeholder adapter for Gemini Cloud Models."""

    def initialize(self) -> None:
        logger.info("Initializing Gemini Cloud Provider")

    def validate(self) -> bool:
        return self.metadata.health_status == "HEALTHY"

    def generate_response(self, prompt: str) -> str:
        return f"[Gemini Cloud Model Response to: {prompt}]"


class ClaudeProvider(ModelProvider):
    """Placeholder adapter for Anthropic Claude Cloud Models."""

    def initialize(self) -> None:
        logger.info("Initializing Claude Cloud Provider")

    def validate(self) -> bool:
        return self.metadata.health_status == "HEALTHY"

    def generate_response(self, prompt: str) -> str:
        return f"[Claude Cloud Model Response to: {prompt}]"


class OllamaProvider(ModelProvider):
    """Placeholder adapter for Ollama Local Models."""

    def initialize(self) -> None:
        logger.info("Initializing Ollama Local Provider")

    def validate(self) -> bool:
        return self.metadata.health_status == "HEALTHY"

    def generate_response(self, prompt: str) -> str:
        return f"[Ollama Local Model Response to: {prompt}]"


class LMStudioProvider(ModelProvider):
    """Placeholder adapter for LM Studio Local Models."""

    def initialize(self) -> None:
        logger.info("Initializing LM Studio Local Provider")

    def validate(self) -> bool:
        return self.metadata.health_status == "HEALTHY"

    def generate_response(self, prompt: str) -> str:
        return f"[LM Studio Local Model Response to: {prompt}]"


class CustomProvider(ModelProvider):
    """Placeholder adapter for Custom/Hybrid Models."""

    def initialize(self) -> None:
        logger.info("Initializing Custom Model Provider")

    def validate(self) -> bool:
        return self.metadata.health_status == "HEALTHY"

    def generate_response(self, prompt: str) -> str:
        return f"[Custom Model Response to: {prompt}]"


class ProviderRegistry:
    """Manages active registrations, lookups, and lifecycle actions for providers."""

    def __init__(self) -> None:
        self._providers: dict[str, ModelProvider] = {}

    def register(self, provider: ModelProvider) -> None:
        """Register a new provider adapter."""
        provider.initialize()
        self._providers[provider.metadata.provider_id] = provider

    def get(self, provider_id: str) -> ModelProvider | None:
        """Lookup provider by key."""
        return self._providers.get(provider_id)

    def list_all(self) -> list[ModelProvider]:
        """Fetch all registered instances."""
        return list(self._providers.values())

    def unload(self, provider_id: str) -> None:
        """Remove adapter registration."""
        if provider_id in self._providers:
            del self._providers[provider_id]


class ProviderSelector:
    """Evaluates selection metrics and matches optimal candidate to policies."""

    @staticmethod
    def select(
        providers: list[ModelProvider], policy: RoutingPolicy, internet_available: bool = True
    ) -> ModelProvider:
        """Select optimal provider matching constraints. Raises ModelRouterError on fault."""
        healthy = [p for p in providers if p.validate()]
        if not healthy:
            raise ModelRouterError("No healthy model providers are registered.")

        if policy == "LOCAL_ONLY":
            local_provs = [p for p in healthy if p.metadata.is_local]
            if not local_provs:
                raise ModelRouterError("Local-only policy defined, but no local providers exist.")
            return local_provs[0]

        if policy == "CLOUD_ONLY":
            if not internet_available:
                raise ModelRouterError("Cloud-only policy defined, but internet is offline.")
            cloud_provs = [p for p in healthy if not p.metadata.is_local]
            if not cloud_provs:
                raise ModelRouterError("Cloud-only policy defined, but no cloud providers exist.")
            return cloud_provs[0]

        if policy == "OFFLINE_FIRST":
            local_provs = [p for p in healthy if p.metadata.is_local]
            if local_provs:
                return local_provs[0]
            # fallback to cloud if local missing
            if not internet_available:
                raise ModelRouterError(
                    "Offline First policy fallback to cloud failed: internet offline."
                )
            return healthy[0]

        # Default fallback
        return healthy[0]


class ModelRouterManager:
    """Coordinates registrations, selection evaluations, and router executions."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.provider_registry = ProviderRegistry()
        self.selector = ProviderSelector()
        self._policy: RoutingPolicy = "OFFLINE_FIRST"

        # Register core placeholder providers during setup
        self._register_default_providers()

    def _register_default_providers(self) -> None:
        """Initialize mock providers to satisfy bootstrap check expectations."""
        openai_meta = ModelProviderMetadata(
            provider_id="openai",
            provider_name="OpenAI Cloud API",
            version="1.0.0",
            capabilities=["chat", "reasoning"],
            supported_languages=["en", "hi"],
            is_local=False,
        )
        gemini_meta = ModelProviderMetadata(
            provider_id="gemini",
            provider_name="Gemini Cloud API",
            version="1.0.0",
            capabilities=["chat", "vision"],
            supported_languages=["en", "hi"],
            is_local=False,
        )
        ollama_meta = ModelProviderMetadata(
            provider_id="ollama",
            provider_name="Ollama Local Engine",
            version="1.0.0",
            capabilities=["chat"],
            supported_languages=["en"],
            is_local=True,
        )

        self.register_provider(OpenAIProvider(openai_meta))
        self.register_provider(GeminiProvider(gemini_meta))
        self.register_provider(OllamaProvider(ollama_meta))

    @property
    def current_policy(self) -> RoutingPolicy:
        """Get active selection policy."""
        return self._policy

    def set_policy(self, policy: RoutingPolicy) -> None:
        """Update active selection policy."""
        self._policy = policy

    def register_provider(self, provider: ModelProvider) -> None:
        """Add provider instance and dispatch registry events."""
        self.provider_registry.register(provider)
        provider.is_active = True

        self.event_bus.publish_sync(
            Event(
                name="model_router.provider_registered",
                category="Brain",
                source="ModelRouterManager",
                payload={"provider_id": provider.metadata.provider_id},
            )
        )

    def route_request(self, prompt: str, internet_available: bool = True) -> str:
        """Route request through selector to target provider execution pipeline."""
        self.event_bus.publish_sync(
            Event(
                name="model_router.routing_started",
                category="Brain",
                source="ModelRouterManager",
                payload={"policy": self._policy},
            )
        )

        try:
            providers = self.provider_registry.list_all()
            selected = self.selector.select(providers, self._policy, internet_available)

            self.event_bus.publish_sync(
                Event(
                    name="model_router.provider_selected",
                    category="Brain",
                    source="ModelRouterManager",
                    payload={"provider_id": selected.metadata.provider_id},
                )
            )

            # Run execution pipeline
            response = selected.generate_response(prompt)

            self.event_bus.publish_sync(
                Event(
                    name="model_router.routing_completed",
                    category="Brain",
                    source="ModelRouterManager",
                    payload={"provider_id": selected.metadata.provider_id},
                )
            )

            return response

        except Exception as e:
            logger.error("Routing pipeline failed", error=str(e))
            self.event_bus.publish_sync(
                Event(
                    name="model_router.provider_failed",
                    category="Brain",
                    source="ModelRouterManager",
                    payload={"error": str(e)},
                )
            )
            raise ModelRouterError(f"AI Routing cycle failed: {e}") from e
