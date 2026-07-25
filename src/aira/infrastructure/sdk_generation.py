"""Enterprise Multi-Language SDK, API Framework & Client Generation Platform for AIRA.

Provides contract registries, schema validators, client generators, and sample generators.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from aira.infrastructure.config import AppConfig
from aira.infrastructure.event_bus import Event, EventBus
from aira.infrastructure.service_registry import ServiceRegistry

logger = structlog.get_logger("aira.sdk_generation")


class SdkGenerationError(Exception):
    """Base exception raised for schema validation failures or API compatibility drifts."""

    pass


@dataclass
class ApiContract:
    """API contract defining endpoints and JSON schemas."""

    contract_id: str
    api_version: str
    endpoints: dict[str, Any]
    schema_definition: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SdkManifest:
    """SDK manifest detailing supported features, API versions, and compatibility profiles."""

    sdk_id: str
    language: str
    api_version: str
    contract_version: str
    compatibility_level: str
    auth_profile: str
    supported_features: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1


class ApiContractRegistry:
    """Registers and stores versioned API contracts."""

    def __init__(self) -> None:
        self.contracts: dict[str, ApiContract] = {}

    def register_contract(self, contract: ApiContract) -> None:
        """Add contract to memory map store."""
        self.contracts[contract.contract_id] = contract


class SchemaValidator:
    """Checks schema integrity and flags breaking API changes."""

    def validate_schema(self, contract: ApiContract) -> bool:
        """Validate JSON schema properties layout."""
        return "type" in contract.schema_definition

    def check_backward_compatibility(
        self, old_contract: ApiContract, new_contract: ApiContract
    ) -> None:
        """Block if new contract removes fields from old schema."""
        old_fields = set(old_contract.schema_definition.get("properties", {}).keys())
        new_fields = set(new_contract.schema_definition.get("properties", {}).keys())

        removed = old_fields - new_fields
        if removed:
            raise SdkGenerationError(
                f"Compatibility check failed: Breaking change detected. Removed fields: {removed}."
            )


class ClientGenerator:
    """Generates SDK templates manifests for multiple target languages."""

    def generate_sdk(self, contract: ApiContract, language: str) -> SdkManifest:
        """Assemble language-specific client config manifest."""
        allowed_languages = {"TypeScript", "Python", "Java", "Go", "C#"}
        if language not in allowed_languages:
            raise SdkGenerationError(f"Unsupported target language: '{language}'")

        return SdkManifest(
            sdk_id=f"sdk_{language.lower()}_{contract.api_version}",
            language=language,
            api_version=contract.api_version,
            contract_version=contract.contract_id,
            compatibility_level="BackwardsCompatible",
            auth_profile="ApiKeyAuth",
            supported_features=["Planning", "Observability"],
        )


class CompatibilityEngine:
    """Validates SDK and API gateway alignment."""

    def verify_alignment(self, manifest: SdkManifest, gateway_version: str) -> bool:
        """Verify version matches gateway release."""
        return manifest.api_version == gateway_version


class SampleGenerator:
    """Creates developer-ready example code snippets."""

    def generate_quickstart(self, language: str, endpoint: str) -> str:
        """Produce sample client invocations code."""
        if language == "TypeScript":
            return (
                f"import {{ AiraClient }} from '@aira/sdk';\n"
                f"const client = new AiraClient();\n"
                f"const res = await client.invoke('{endpoint}');"
            )
        if language == "Python":
            return (
                f"from aira import AiraClient\n"
                f"client = AiraClient()\n"
                f"res = client.invoke('{endpoint}')"
            )
        return f"// Quickstart snippet for {language} invoking '{endpoint}'"


class MultiLanguageSdkPlatform:
    """Coordinating manager resolving schema validations, client generations, and examples."""

    def __init__(self, config: AppConfig, registry: ServiceRegistry, event_bus: EventBus) -> None:
        self.config = config
        self.registry = registry
        self.event_bus = event_bus

        self.contract_registry = ApiContractRegistry()
        self.schema_validator = SchemaValidator()
        self.client_generator = ClientGenerator()
        self.compatibility_engine = CompatibilityEngine()
        self.sample_generator = SampleGenerator()

    def publish_contract(
        self,
        contract_id: str,
        api_version: str,
        endpoints: dict[str, Any],
        schema_definition: dict[str, Any],
    ) -> ApiContract:
        """Validate schema details, register contract, and publish event signals."""
        contract = ApiContract(
            contract_id=contract_id,
            api_version=api_version,
            endpoints=endpoints,
            schema_definition=schema_definition,
        )

        if not self.schema_validator.validate_schema(contract):
            raise SdkGenerationError("Contract publish failed: Schema lacks type definition.")

        self.contract_registry.register_contract(contract)

        self.event_bus.publish_sync(
            Event(
                name="sdk.contract.published",
                category="SdkGeneration",
                source="MultiLanguageSdkPlatform",
                payload={"contract_id": contract_id},
            )
        )

        return contract

    def generate_language_sdks(self, contract_id: str, languages: list[str]) -> list[SdkManifest]:
        """Verify contract, check compiler target, compile SDKs, and publish events."""
        contract = self.contract_registry.contracts.get(contract_id)
        if not contract:
            raise SdkGenerationError(f"Contract not registered: '{contract_id}'")

        manifests = []
        for lang in languages:
            manifest = self.client_generator.generate_sdk(contract, lang)
            manifests.append(manifest)

            self.event_bus.publish_sync(
                Event(
                    name="sdk.generated",
                    category="SdkGeneration",
                    source="MultiLanguageSdkPlatform",
                    payload={"language": lang, "sdk_id": manifest.sdk_id},
                )
            )

        return manifests

    def validate_sdk_alignment(self, manifest: SdkManifest, gateway_version: str) -> None:
        """Forward alignment check and notify events."""
        aligned = self.compatibility_engine.verify_alignment(manifest, gateway_version)
        if not aligned:
            raise SdkGenerationError(
                f"Alignment validation failed: SDK version '{manifest.api_version}' "
                f"mismatches gateway version '{gateway_version}'."
            )

        self.event_bus.publish_sync(
            Event(
                name="sdk.compatibility.validated",
                category="SdkGeneration",
                source="MultiLanguageSdkPlatform",
                payload={"sdk_id": manifest.sdk_id},
            )
        )

    def generate_sample_snippets(self, language: str, endpoint: str) -> str:
        """Produce sample quickstart templates code and notify events."""
        snippet = self.sample_generator.generate_quickstart(language, endpoint)

        self.event_bus.publish_sync(
            Event(
                name="sdk.sample.generated",
                category="SdkGeneration",
                source="MultiLanguageSdkPlatform",
                payload={"language": language, "endpoint": endpoint},
            )
        )

        return snippet
