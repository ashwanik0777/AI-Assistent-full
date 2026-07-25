"""Bootstrap manager to handle environment detection, directory setup,
and configuration validation.
"""

from pathlib import Path
from typing import Any

import structlog
from dotenv import load_dotenv

from aira.infrastructure.config import AppConfig, load_config
from aira.infrastructure.logger import setup_logger

logger = structlog.getLogger("aira.bootstrap")


class BootstrapManager:
    """Manages the startup and initialization sequence of the AIRA runtime."""

    def __init__(self) -> None:
        self.config: AppConfig | None = None
        self.logger: Any = None
        from aira.infrastructure.di_container import DependencyContainer

        self.container: DependencyContainer = DependencyContainer()

    def execute_bootstrap(self) -> AppConfig:
        """Run the complete boot lifecycle step-by-step."""
        # 1. Environment Validation / dotenv load
        self.validate_environment()

        # 2. Configuration Load
        self.config = load_config()

        # 3. Directory Creation
        self.create_directories(self.config)

        # 4. Logger Bootstrap
        self.logger = setup_logger(self.config)

        # 5. Dependency Container Registration
        self.container.register_singleton("config", self.config, "Root Application Settings")
        self.container.register_singleton("logger", self.logger, "Structured Logger Utility")

        # Instantiate EventBus
        from aira.infrastructure.event_bus import EventBus

        self.event_bus = EventBus()
        self.container.register_singleton("event_bus", self.event_bus, "Enterprise Event Bus")

        # 6. Future Service Placeholders Registration (Sprint 1.4 requirements)
        self.container.register_singleton(
            "database", lambda: None, "[Placeholder] Database Manager"
        )
        self.container.register_singleton("memory", lambda: None, "[Placeholder] Memory Manager")
        self.container.register_singleton(
            "plugin_manager", lambda: None, "[Placeholder] Plugin Manager"
        )
        self.container.register_singleton(
            "skill_manager", lambda: None, "[Placeholder] Skill Manager"
        )
        self.container.register_singleton(
            "model_router", lambda: None, "[Placeholder] Model Router"
        )
        self.container.register_singleton(
            "permission_manager", lambda: None, "[Placeholder] Permission Manager"
        )
        self.container.register_singleton(
            "health_monitor", lambda: None, "[Placeholder] Health Monitor"
        )

        # 7. Service Registry Initialization
        from aira.infrastructure.service_registry import ServiceDescriptor, ServiceRegistry

        self.registry = ServiceRegistry(self.container)
        self.container.register_singleton(
            "service_registry", self.registry, "Centralized Service Registry"
        )

        # Instantiate LifecycleOrchestrator
        from aira.infrastructure.lifecycle import LifecycleOrchestrator

        self.lifecycle = LifecycleOrchestrator(self.container, self.registry, self.event_bus)
        self.container.register_singleton(
            "lifecycle_orchestrator", self.lifecycle, "Enterprise Lifecycle Orchestrator"
        )

        # Instantiate AIRAKernel
        from aira.infrastructure.kernel import AIRAKernel

        self.kernel = AIRAKernel(
            self.config, self.container, self.registry, self.event_bus, self.lifecycle
        )
        self.container.register_singleton("kernel", self.kernel, "Enterprise Runtime Kernel")

        # Instantiate ObservabilityFramework
        from aira.infrastructure.observability import ObservabilityFramework

        self.observability = ObservabilityFramework(
            self.config, self.container, self.registry, self.event_bus, self.lifecycle, self.kernel
        )
        self.container.register_singleton(
            "observability", self.observability, "Enterprise Observability Framework"
        )

        # Instantiate AudioManager
        from aira.infrastructure.audio import AudioManager

        self.audio = AudioManager(self.config, self.registry, self.event_bus)
        self.container.register_singleton("audio", self.audio, "Enterprise Audio Engine")

        # Instantiate WakeWordManager
        from aira.infrastructure.wake_word import WakeWordManager

        self.wake_word = WakeWordManager(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "wake_word", self.wake_word, "Enterprise Wake Word Engine"
        )

        # Instantiate SpeechRecognitionManager
        from aira.infrastructure.speech_recognition import SpeechRecognitionManager

        self.speech_recognition = SpeechRecognitionManager(
            self.config, self.registry, self.event_bus
        )
        self.container.register_singleton(
            "speech_recognition", self.speech_recognition, "Enterprise Speech Recognition Platform"
        )

        # Instantiate VoiceSessionManager
        from aira.infrastructure.voice_session import VoiceSessionManager

        self.voice_session = VoiceSessionManager(
            self.config,
            self.registry,
            self.event_bus,
            self.audio,
            self.wake_word,
            self.speech_recognition,
        )
        self.container.register_singleton(
            "voice_session", self.voice_session, "Enterprise Voice Session Manager"
        )

        # Instantiate IntentManager
        from aira.infrastructure.intent import IntentManager

        self.intent = IntentManager(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "intent", self.intent, "Enterprise Intent Recognition Layer"
        )

        # Instantiate RequestManager
        from aira.infrastructure.request_normalization import RequestManager

        self.request_normalization = RequestManager(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "request_normalization",
            self.request_normalization,
            "Enterprise Request Normalization Layer",
        )

        # Instantiate BrainManager
        from aira.infrastructure.brain_core import BrainManager

        self.brain = BrainManager(self.config, self.registry, self.event_bus)
        self.container.register_singleton("brain", self.brain, "Enterprise Brain Core Layer")

        # Instantiate ModelRouterManager
        from aira.infrastructure.model_router import ModelRouterManager

        self.model_router = ModelRouterManager(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "model_router", self.model_router, "Enterprise Model Router Layer", allow_overwrite=True
        )

        # Instantiate ReasoningManager
        from aira.infrastructure.reasoning_interface import ReasoningManager

        self.reasoning = ReasoningManager(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "reasoning", self.reasoning, "Enterprise Reasoning Interface Layer"
        )

        # Instantiate PlannerManager
        from aira.infrastructure.planner import PlannerManager

        self.planner = PlannerManager(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "planner", self.planner, "Enterprise Planner Engine Layer"
        )

        # Instantiate GoalManager
        from aira.infrastructure.goal_manager import GoalManager

        self.goal_manager = GoalManager(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "goal_manager", self.goal_manager, "Enterprise Goal Manager Layer"
        )

        # Instantiate TaskGraphManager
        from aira.infrastructure.task_graph import TaskGraphManager

        self.task_graph = TaskGraphManager(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "task_graph", self.task_graph, "Enterprise Task Graph Builder Layer"
        )

        # Instantiate ExecutionPlannerManager
        from aira.infrastructure.execution_planner import ExecutionPlannerManager

        self.execution_planner = ExecutionPlannerManager(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "execution_planner", self.execution_planner, "Enterprise Execution Planner Layer"
        )

        # Instantiate BrainRuntimePipeline
        from aira.infrastructure.brain_runtime import BrainRuntimePipeline

        self.brain_runtime = BrainRuntimePipeline(
            self.config,
            self.registry,
            self.event_bus,
            self.brain,
            self.model_router,
            self.reasoning,
            self.goal_manager,
            self.planner,
            self.task_graph,
            self.execution_planner,
        )
        self.container.register_singleton(
            "brain_runtime", self.brain_runtime, "Enterprise Brain Runtime Integration Layer"
        )

        # Instantiate BrainEvaluatorManager
        from aira.infrastructure.brain_evaluator import BrainEvaluatorManager

        self.brain_evaluator = BrainEvaluatorManager(
            self.config, self.registry, self.event_bus, self.brain_runtime
        )
        self.container.register_singleton(
            "brain_evaluator", self.brain_evaluator, "Enterprise Brain Evaluation Layer"
        )

        # Instantiate SkillEngineManager
        from aira.infrastructure.skill_engine import SkillEngineManager

        self.skill_engine = SkillEngineManager(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "skill_engine", self.skill_engine, "Enterprise Skill Engine Foundation Layer"
        )

        # Instantiate PermissionManager
        from aira.infrastructure.permission_manager import PermissionManager

        self.permission_manager = PermissionManager(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "permission_manager",
            self.permission_manager,
            "Enterprise Permission & Capability Layer",
            allow_overwrite=True,
        )

        # Instantiate ApplicationManager
        from aira.infrastructure.app_skills import (
            ApplicationCloseSkill,
            ApplicationManager,
            ApplicationOpenSkill,
        )

        self.application_manager = ApplicationManager(
            self.config, self.registry, self.event_bus, self.permission_manager
        )
        self.container.register_singleton(
            "application_manager",
            self.application_manager,
            "Enterprise Application Skill Pack Layer",
        )

        # Register Application Open/Close skills to the skill engine registry
        self.skill_engine.register_skill(ApplicationOpenSkill(self.application_manager))
        self.skill_engine.register_skill(ApplicationCloseSkill(self.application_manager))

        # Instantiate FilesystemManager
        from aira.infrastructure.fs_skills import (
            CreateFolderSkill,
            FileReadSkill,
            FilesystemManager,
            FileWriteSkill,
        )

        self.filesystem_manager = FilesystemManager(
            self.config, self.registry, self.event_bus, self.permission_manager
        )
        self.container.register_singleton(
            "filesystem_manager", self.filesystem_manager, "Enterprise Filesystem Skill Pack Layer"
        )

        # Register Filesystem skills to the skill engine registry
        self.skill_engine.register_skill(FileReadSkill(self.filesystem_manager))
        self.skill_engine.register_skill(FileWriteSkill(self.filesystem_manager))
        self.skill_engine.register_skill(CreateFolderSkill(self.filesystem_manager))

        # Instantiate TerminalManager
        from aira.infrastructure.terminal_skills import TerminalExecuteSkill, TerminalManager

        self.terminal_manager = TerminalManager(
            self.config,
            self.registry,
            self.event_bus,
            self.permission_manager,
            self.filesystem_manager,
        )
        self.container.register_singleton(
            "terminal_manager", self.terminal_manager, "Enterprise Terminal Skill Pack Layer"
        )

        # Register Terminal skills to the skill engine registry
        self.skill_engine.register_skill(TerminalExecuteSkill(self.terminal_manager))

        # Instantiate BrowserManager
        from aira.infrastructure.browser_skills import (
            BrowserManager,
            BrowserNavigateSkill,
            BrowserOpenSkill,
        )

        self.browser_manager = BrowserManager(
            self.config, self.registry, self.event_bus, self.permission_manager
        )
        self.container.register_singleton(
            "browser_manager", self.browser_manager, "Enterprise Browser Skill Pack Layer"
        )

        # Register Browser skills to the skill engine registry
        self.skill_engine.register_skill(BrowserOpenSkill(self.browser_manager))
        self.skill_engine.register_skill(BrowserNavigateSkill(self.browser_manager))

        # Instantiate SkillRuntimeManager
        from aira.infrastructure.skill_runtime import SkillRuntimeManager

        self.skill_runtime = SkillRuntimeManager(
            self.config, self.registry, self.event_bus, self.permission_manager, self.skill_engine
        )
        self.container.register_singleton(
            "skill_runtime",
            self.skill_runtime,
            "Enterprise Skill Runtime & Orchestration Engine Layer",
        )

        # Instantiate SafetyEngine
        from aira.infrastructure.safety_framework import SafetyEngine

        self.safety_engine = SafetyEngine(
            self.config, self.registry, self.event_bus, self.permission_manager
        )
        self.container.register_singleton(
            "safety_engine", self.safety_engine, "Enterprise Execution Safety Framework Layer"
        )

        # Instantiate SkillEvaluationManager
        from aira.infrastructure.skill_evaluator import SkillEvaluationManager

        self.skill_evaluator = SkillEvaluationManager(
            self.config,
            self.registry,
            self.event_bus,
            self.permission_manager,
            self.safety_engine,
            self.skill_runtime,
        )
        self.container.register_singleton(
            "skill_evaluator",
            self.skill_evaluator,
            "Enterprise Skill Evaluation & Reliability Framework Layer",
        )

        # Instantiate WorkflowEngineManager
        from aira.infrastructure.workflow_engine import WorkflowEngineManager

        self.workflow_engine = WorkflowEngineManager(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "workflow_engine",
            self.workflow_engine,
            "Enterprise Workflow & Automation Engine Foundation Layer",
        )

        # Instantiate WdlParser
        from aira.infrastructure.wdl_parser import WdlParser

        self.wdl_parser = WdlParser(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "wdl_parser", self.wdl_parser, "Enterprise Workflow Definition Language Parser Layer"
        )

        # Instantiate WorkflowRuntimeManager
        from aira.infrastructure.workflow_runtime import WorkflowRuntimeManager

        self.workflow_runtime = WorkflowRuntimeManager(
            self.config, self.registry, self.event_bus, self.skill_runtime
        )
        self.container.register_singleton(
            "workflow_runtime_service",
            self.workflow_runtime,
            "Enterprise Workflow Runtime & Execution Engine Layer",
        )

        # Instantiate WorkflowContextManager
        from aira.infrastructure.workflow_context import WorkflowContextManager

        self.workflow_context_manager = WorkflowContextManager(
            self.config, self.registry, self.event_bus
        )
        self.container.register_singleton(
            "workflow_context",
            self.workflow_context_manager,
            "Enterprise Workflow Context, Variables & State Engine Layer",
        )

        # Instantiate DecisionEngineManager
        from aira.infrastructure.decision_engine import DecisionEngineManager

        self.decision_engine = DecisionEngineManager(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "decision_engine",
            self.decision_engine,
            "Enterprise Conditional Execution & Decision Engine Layer",
        )

        # Instantiate DependencySchedulerManager
        from aira.infrastructure.dependency_scheduler import DependencySchedulerManager

        self.dependency_scheduler = DependencySchedulerManager(
            self.config, self.registry, self.event_bus
        )
        self.container.register_singleton(
            "dependency_scheduler",
            self.dependency_scheduler,
            "Enterprise Parallel Execution & Dependency Graph Scheduler Layer",
        )

        # Instantiate CheckpointEngineManager
        from aira.infrastructure.recovery_engine import CheckpointEngineManager

        self.recovery_engine = CheckpointEngineManager(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "recovery_engine",
            self.recovery_engine,
            "Enterprise Checkpoint, Recovery & Resume Engine Layer",
        )

        # Instantiate WorkflowAnalyticsManager
        from aira.infrastructure.workflow_analytics import WorkflowAnalyticsManager

        self.workflow_analytics = WorkflowAnalyticsManager(
            self.config, self.registry, self.event_bus
        )
        self.container.register_singleton(
            "workflow_analytics",
            self.workflow_analytics,
            "Enterprise Workflow Analytics, Optimization & Evaluation Framework Layer",
        )

        # Instantiate MemoryOrchestrator
        from aira.infrastructure.memory_engine import MemoryOrchestrator

        self.memory_engine = MemoryOrchestrator(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "memory_engine", self.memory_engine, "Enterprise Memory Engine Foundation Layer"
        )

        # Instantiate WorkingMemoryManager
        from aira.infrastructure.working_memory import WorkingMemoryManager

        self.working_memory = WorkingMemoryManager(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "working_memory", self.working_memory, "Enterprise Working Memory Engine Layer"
        )

        # Instantiate EpisodeStore
        from aira.infrastructure.episodic_memory import EpisodeStore

        self.episodic_memory = EpisodeStore(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "episodic_memory", self.episodic_memory, "Enterprise Episodic Memory Engine Layer"
        )

        # Instantiate SemanticStore
        from aira.infrastructure.semantic_memory import SemanticStore

        self.semantic_memory = SemanticStore(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "semantic_memory",
            self.semantic_memory,
            "Enterprise Semantic Memory & Knowledge Store Layer",
        )

        # Instantiate ProcedureLibrary
        from aira.infrastructure.procedural_memory import ProcedureLibrary

        self.procedural_memory = ProcedureLibrary(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "procedural_memory", self.procedural_memory, "Enterprise Procedural Memory Engine Layer"
        )

        # Instantiate KnowledgeGraphStore
        from aira.infrastructure.knowledge_graph import KnowledgeGraphStore

        self.knowledge_graph = KnowledgeGraphStore(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "knowledge_graph", self.knowledge_graph, "Enterprise Knowledge Graph Engine Layer"
        )

        # Instantiate HybridRetrievalEngine
        from aira.infrastructure.retrieval_engine import HybridRetrievalEngine

        self.retrieval_engine = HybridRetrievalEngine(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "retrieval_engine",
            self.retrieval_engine,
            "Enterprise Hybrid Retrieval & Context Assembly Engine Layer",
        )

        # Instantiate MemoryConsolidationEngine
        from aira.infrastructure.learning_engine import MemoryConsolidationEngine

        self.learning_engine = MemoryConsolidationEngine(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "learning_engine",
            self.learning_engine,
            "Enterprise Memory Consolidation & Learning Engine Layer",
        )

        # Instantiate MemoryEvaluatorEngine
        from aira.infrastructure.memory_evaluator import MemoryEvaluatorEngine

        self.memory_evaluator = MemoryEvaluatorEngine(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "memory_evaluator",
            self.memory_evaluator,
            "Enterprise Memory Quality, Evaluation & Benchmark Framework Layer",
        )

        # Instantiate BackupManager
        from aira.infrastructure.memory_backup import BackupManager

        self.backup_manager = BackupManager(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "backup_manager",
            self.backup_manager,
            "Enterprise Backup & Recovery manager framework Layer",
        )

        # Instantiate CapabilityEngine
        from aira.infrastructure.capability_engine import CapabilityEngine

        self.capability_engine = CapabilityEngine(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "capability_engine", self.capability_engine, "Enterprise Capability Engine Layer"
        )

        # Instantiate DeveloperWorkspaceEngine
        from aira.infrastructure.workspace_engine import DeveloperWorkspaceEngine

        self.workspace_engine = DeveloperWorkspaceEngine(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "workspace_engine", self.workspace_engine, "Developer Workspace Engine Layer"
        )

        # Instantiate WorkspaceDiscoveryManager
        from aira.infrastructure.workspace_discovery import WorkspaceDiscoveryManager

        self.discovery_manager = WorkspaceDiscoveryManager(
            self.config, self.registry, self.event_bus, self.workspace_engine.ws_registry
        )
        self.container.register_singleton(
            "discovery_manager", self.discovery_manager, "Enterprise Workspace Discovery Layer"
        )

        # Instantiate ProjectIntelligenceManager
        from aira.infrastructure.project_intelligence import ProjectIntelligenceManager

        self.intelligence_manager = ProjectIntelligenceManager(
            self.config, self.registry, self.event_bus
        )
        self.container.register_singleton(
            "intelligence_manager",
            self.intelligence_manager,
            "Enterprise Project Intelligence Layer",
        )

        # Instantiate IDEIntelligenceManager
        from aira.infrastructure.ide_intelligence import IDEIntelligenceManager

        self.ide_intelligence = IDEIntelligenceManager(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "ide_intelligence",
            self.ide_intelligence,
            "Enterprise IDE Intelligence Layer",
        )

        # Instantiate RepositoryIntelligenceManager
        from aira.infrastructure.repository_intelligence import RepositoryIntelligenceManager

        self.repository_intelligence = RepositoryIntelligenceManager(
            self.config, self.registry, self.event_bus
        )
        self.container.register_singleton(
            "repository_intelligence",
            self.repository_intelligence,
            "Enterprise Repository Intelligence Layer",
        )

        # Instantiate CommandIntelligenceManager
        from aira.infrastructure.command_intelligence import CommandIntelligenceManager

        self.command_intelligence = CommandIntelligenceManager(
            self.config, self.registry, self.event_bus
        )
        self.container.register_singleton(
            "command_intelligence",
            self.command_intelligence,
            "Enterprise Command Intelligence Layer",
        )

        # Instantiate DocumentationIntelligenceManager
        from aira.infrastructure.documentation_intelligence import DocumentationIntelligenceManager

        self.documentation_intelligence = DocumentationIntelligenceManager(
            self.config, self.registry, self.event_bus
        )
        self.container.register_singleton(
            "documentation_intelligence",
            self.documentation_intelligence,
            "Enterprise Documentation & Engineering Knowledge Layer",
        )

        # Instantiate EngineeringDiagnosticsEngine
        from aira.infrastructure.engineering_diagnostics import EngineeringDiagnosticsEngine

        self.engineering_diagnostics = EngineeringDiagnosticsEngine(
            self.config, self.registry, self.event_bus
        )
        self.container.register_singleton(
            "engineering_diagnostics",
            self.engineering_diagnostics,
            "Enterprise Engineering Diagnostics & Refactoring Layer",
        )

        # Instantiate WorkspaceIntelligenceManager
        from aira.infrastructure.workspace_intelligence import WorkspaceIntelligenceManager

        self.workspace_intelligence = WorkspaceIntelligenceManager(
            self.config, self.registry, self.event_bus
        )
        self.container.register_singleton(
            "workspace_intelligence",
            self.workspace_intelligence,
            "Enterprise Workspace Intelligence Layer",
        )

        # Instantiate EngineeringObservabilityManager
        from aira.infrastructure.engineering_observability import EngineeringObservabilityManager

        self.engineering_observability = EngineeringObservabilityManager(
            self.config, self.registry, self.event_bus
        )
        self.container.register_singleton(
            "engineering_observability",
            self.engineering_observability,
            "Enterprise Engineering Observability Layer",
        )

        # Instantiate PerceptionEngine
        from aira.infrastructure.perception_engine import PerceptionEngine

        self.perception_engine = PerceptionEngine(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "perception_engine",
            self.perception_engine,
            "Enterprise Perception Engine Layer",
        )

        # Instantiate ScreenIntelligenceManager
        from aira.infrastructure.screen_intelligence import ScreenIntelligenceManager

        self.screen_intelligence = ScreenIntelligenceManager(
            self.config, self.registry, self.event_bus, self.perception_engine
        )
        self.container.register_singleton(
            "screen_intelligence",
            self.screen_intelligence,
            "Enterprise Screen Intelligence Layer",
        )

        # Instantiate DocumentOCRIntelligenceManager
        from aira.infrastructure.document_ocr_intelligence import DocumentOCRIntelligenceManager

        self.document_ocr_intelligence = DocumentOCRIntelligenceManager(
            self.config, self.registry, self.event_bus, self.perception_engine
        )
        self.container.register_singleton(
            "document_ocr_intelligence",
            self.document_ocr_intelligence,
            "Enterprise Document OCR Intelligence Layer",
        )

        # Instantiate BrowserPerceptionEngine
        from aira.infrastructure.browser_perception import BrowserPerceptionEngine

        self.browser_perception = BrowserPerceptionEngine(
            self.config, self.registry, self.event_bus, self.perception_engine
        )
        self.container.register_singleton(
            "browser_perception",
            self.browser_perception,
            "Enterprise Browser Perception Layer",
        )

        # Instantiate UISemanticIntelligenceManager
        from aira.infrastructure.ui_semantic_intelligence import UISemanticIntelligenceManager

        self.ui_semantic_intelligence = UISemanticIntelligenceManager(
            self.config, self.registry, self.event_bus, self.perception_engine
        )
        self.container.register_singleton(
            "ui_semantic_intelligence",
            self.ui_semantic_intelligence,
            "Enterprise UI Semantic Intelligence Layer",
        )

        # Instantiate DesktopPerceptionEngine
        from aira.infrastructure.desktop_application_intelligence import DesktopPerceptionEngine

        self.desktop_perception = DesktopPerceptionEngine(
            self.config, self.registry, self.event_bus, self.perception_engine
        )
        self.container.register_singleton(
            "desktop_perception",
            self.desktop_perception,
            "Enterprise Desktop Application Intelligence Layer",
        )

        # Instantiate VisualMemoryManager
        from aira.infrastructure.visual_memory_intelligence import VisualMemoryManager

        self.visual_memory_intelligence = VisualMemoryManager(
            self.config, self.registry, self.event_bus, self.perception_engine
        )
        self.container.register_singleton(
            "visual_memory_intelligence",
            self.visual_memory_intelligence,
            "Enterprise Visual Memory & Spatial Intelligence Layer",
        )

        # Instantiate UnifiedContextFusionEngine
        from aira.infrastructure.unified_context_fusion import UnifiedContextFusionEngine

        self.context_fusion = UnifiedContextFusionEngine(
            self.config, self.registry, self.event_bus, self.perception_engine
        )
        self.container.register_singleton(
            "context_fusion",
            self.context_fusion,
            "Enterprise Unified Context Fusion Layer",
        )

        # Instantiate PerceptionEvaluationEngine
        from aira.infrastructure.perception_evaluation import PerceptionEvaluationEngine

        self.perception_evaluation = PerceptionEvaluationEngine(
            self.config, self.registry, self.event_bus
        )
        self.container.register_singleton(
            "perception_evaluation",
            self.perception_evaluation,
            "Enterprise Perception Evaluation Layer",
        )

        # Instantiate PerceptionTrustEngine
        from aira.infrastructure.perception_security import PerceptionTrustEngine

        self.perception_security = PerceptionTrustEngine(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "perception_security",
            self.perception_security,
            "Enterprise Perception Security Layer",
        )

        # Instantiate AgentRuntimeKernel
        from aira.infrastructure.agent_runtime import AgentRuntimeKernel

        self.agent_runtime = AgentRuntimeKernel(self.config, self.registry, self.event_bus)
        self.container.register_singleton(
            "agent_runtime",
            self.agent_runtime,
            "Enterprise Agent Runtime Kernel",
        )

        # 8. Register service descriptors in Service Registry (Metadata only - NO object creation!)
        config_desc = ServiceDescriptor(
            name="config",
            category="Configuration",
            description="Root Application Settings Configuration Manager",
            version="0.1.0",
        )
        logger_desc = ServiceDescriptor(
            name="logger",
            category="Logging",
            description="Structured Logging Manager Wrapper",
            version="0.1.0",
        )
        registry_desc = ServiceDescriptor(
            name="service_registry",
            category="Core",
            description="Central Runtime Service Registry",
            version="0.1.0",
        )
        event_bus_desc = ServiceDescriptor(
            name="event_bus",
            category="Core",
            description="Central Communication Event Bus",
            version="0.1.0",
        )
        lifecycle_desc = ServiceDescriptor(
            name="lifecycle_orchestrator",
            category="Core",
            description="Enterprise Lifecycle Orchestrator",
            version="0.1.0",
        )
        kernel_desc = ServiceDescriptor(
            name="kernel", category="Core", description="Enterprise Runtime Kernel", version="0.1.0"
        )
        observability_desc = ServiceDescriptor(
            name="observability",
            category="Core",
            description="Enterprise Observability Framework",
            version="0.1.0",
        )
        audio_desc = ServiceDescriptor(
            name="audio", category="Core", description="Enterprise Audio Engine", version="0.1.0"
        )
        wake_word_desc = ServiceDescriptor(
            name="wake_word",
            category="Core",
            description="Enterprise Wake Word Engine",
            version="0.1.0",
        )
        speech_recognition_desc = ServiceDescriptor(
            name="speech_recognition",
            category="Core",
            description="Enterprise Speech Recognition Platform",
            version="0.1.0",
        )
        voice_session_desc = ServiceDescriptor(
            name="voice_session",
            category="Core",
            description="Enterprise Voice Session Manager",
            version="0.1.0",
        )
        intent_desc = ServiceDescriptor(
            name="intent",
            category="Core",
            description="Enterprise Intent Recognition Layer",
            version="0.1.0",
        )
        request_normalization_desc = ServiceDescriptor(
            name="request_normalization",
            category="Core",
            description="Enterprise Request Normalization Layer",
            version="0.1.0",
        )
        brain_desc = ServiceDescriptor(
            name="brain",
            category="Core",
            description="Enterprise Brain Core Layer",
            version="0.1.0",
        )
        model_router_desc = ServiceDescriptor(
            name="model_router",
            category="Core",
            description="Enterprise Model Router Layer",
            version="0.1.0",
        )
        reasoning_desc = ServiceDescriptor(
            name="reasoning",
            category="Core",
            description="Enterprise Reasoning Interface Layer",
            version="0.1.0",
        )
        planner_desc = ServiceDescriptor(
            name="planner",
            category="Core",
            description="Enterprise Planner Engine Layer",
            version="0.1.0",
        )
        goal_manager_desc = ServiceDescriptor(
            name="goal_manager",
            category="Core",
            description="Enterprise Goal Manager Layer",
            version="0.1.0",
        )
        task_graph_desc = ServiceDescriptor(
            name="task_graph",
            category="Core",
            description="Enterprise Task Graph Builder Layer",
            version="0.1.0",
        )
        execution_planner_desc = ServiceDescriptor(
            name="execution_planner",
            category="Core",
            description="Enterprise Execution Planner Layer",
            version="0.1.0",
        )
        brain_runtime_desc = ServiceDescriptor(
            name="brain_runtime",
            category="Core",
            description="Enterprise Brain Runtime Integration Layer",
            version="0.1.0",
        )
        brain_evaluator_desc = ServiceDescriptor(
            name="brain_evaluator",
            category="Core",
            description="Enterprise Brain Evaluation Layer",
            version="0.1.0",
        )
        skill_engine_desc = ServiceDescriptor(
            name="skill_engine",
            category="Core",
            description="Enterprise Skill Engine Foundation Layer",
            version="0.1.0",
        )
        permission_manager_desc = ServiceDescriptor(
            name="permission_manager",
            category="Core",
            description="Enterprise Permission & Capability Layer",
            version="0.1.0",
        )
        application_manager_desc = ServiceDescriptor(
            name="application_manager",
            category="Core",
            description="Enterprise Application Skill Pack Layer",
            version="0.1.0",
        )
        filesystem_manager_desc = ServiceDescriptor(
            name="filesystem_manager",
            category="Core",
            description="Enterprise Filesystem Skill Pack Layer",
            version="0.1.0",
        )
        terminal_manager_desc = ServiceDescriptor(
            name="terminal_manager",
            category="Core",
            description="Enterprise Terminal Skill Pack Layer",
            version="0.1.0",
        )
        browser_manager_desc = ServiceDescriptor(
            name="browser_manager",
            category="Core",
            description="Enterprise Browser Skill Pack Layer",
            version="0.1.0",
        )
        skill_runtime_desc = ServiceDescriptor(
            name="skill_runtime",
            category="Core",
            description="Enterprise Skill Runtime & Orchestration Engine Layer",
            version="0.1.0",
        )
        safety_engine_desc = ServiceDescriptor(
            name="safety_engine",
            category="Core",
            description="Enterprise Execution Safety Framework Layer",
            version="0.1.0",
        )
        skill_evaluator_desc = ServiceDescriptor(
            name="skill_evaluator",
            category="Core",
            description="Enterprise Skill Evaluation & Reliability Framework Layer",
            version="0.1.0",
        )
        workflow_engine_desc = ServiceDescriptor(
            name="workflow_engine",
            category="Core",
            description="Enterprise Workflow & Automation Engine Foundation Layer",
            version="0.1.0",
        )
        wdl_parser_desc = ServiceDescriptor(
            name="wdl_parser",
            category="Core",
            description="Enterprise Workflow Definition Language Parser Layer",
            version="0.1.0",
        )
        workflow_runtime_desc = ServiceDescriptor(
            name="workflow_runtime_service",
            category="Core",
            description="Enterprise Workflow Runtime & Execution Engine Layer",
            version="0.1.0",
        )
        workflow_context_desc = ServiceDescriptor(
            name="workflow_context",
            category="Core",
            description="Enterprise Workflow Context, Variables & State Engine Layer",
            version="0.1.0",
        )
        decision_engine_desc = ServiceDescriptor(
            name="decision_engine",
            category="Core",
            description="Enterprise Conditional Execution & Decision Engine Layer",
            version="0.1.0",
        )
        dependency_scheduler_desc = ServiceDescriptor(
            name="dependency_scheduler",
            category="Core",
            description="Enterprise Parallel Execution & Dependency Graph Scheduler Layer",
            version="0.1.0",
        )
        recovery_engine_desc = ServiceDescriptor(
            name="recovery_engine",
            category="Core",
            description="Enterprise Checkpoint, Recovery & Resume Engine Layer",
            version="0.1.0",
        )
        workflow_analytics_desc = ServiceDescriptor(
            name="workflow_analytics",
            category="Core",
            description="Enterprise Workflow Analytics, Optimization & Evaluation Framework Layer",
            version="0.1.0",
        )
        memory_engine_desc = ServiceDescriptor(
            name="memory_engine",
            category="Core",
            description="Enterprise Memory Engine Foundation Layer",
            version="0.1.0",
        )
        working_memory_desc = ServiceDescriptor(
            name="working_memory",
            category="Core",
            description="Enterprise Working Memory Engine Layer",
            version="0.1.0",
        )
        episodic_memory_desc = ServiceDescriptor(
            name="episodic_memory",
            category="Core",
            description="Enterprise Episodic Memory Engine Layer",
            version="0.1.0",
        )
        semantic_memory_desc = ServiceDescriptor(
            name="semantic_memory",
            category="Core",
            description="Enterprise Semantic Memory & Knowledge Store Layer",
            version="0.1.0",
        )
        procedural_memory_desc = ServiceDescriptor(
            name="procedural_memory",
            category="Core",
            description="Enterprise Procedural Memory Engine Layer",
            version="0.1.0",
        )
        knowledge_graph_desc = ServiceDescriptor(
            name="knowledge_graph",
            category="Core",
            description="Enterprise Knowledge Graph Engine Layer",
            version="0.1.0",
        )
        retrieval_engine_desc = ServiceDescriptor(
            name="retrieval_engine",
            category="Core",
            description="Enterprise Hybrid Retrieval & Context Assembly Engine Layer",
            version="0.1.0",
        )
        learning_engine_desc = ServiceDescriptor(
            name="learning_engine",
            category="Core",
            description="Enterprise Memory Consolidation & Learning Engine Layer",
            version="0.1.0",
        )
        memory_evaluator_desc = ServiceDescriptor(
            name="memory_evaluator",
            category="Core",
            description="Enterprise Memory Quality, Evaluation & Benchmark Framework Layer",
            version="0.1.0",
        )
        backup_manager_desc = ServiceDescriptor(
            name="backup_manager",
            category="Core",
            description="Enterprise Backup & Recovery manager framework Layer",
            version="0.1.0",
        )
        capability_engine_desc = ServiceDescriptor(
            name="capability_engine",
            category="Core",
            description="Enterprise Capability Engine Layer",
            version="0.1.0",
        )
        workspace_engine_desc = ServiceDescriptor(
            name="workspace_engine",
            category="Core",
            description="Developer Workspace Engine Layer",
            version="0.1.0",
        )
        discovery_manager_desc = ServiceDescriptor(
            name="discovery_manager",
            category="Core",
            description="Enterprise Workspace Discovery Layer",
            version="0.1.0",
        )
        intelligence_manager_desc = ServiceDescriptor(
            name="intelligence_manager",
            category="Core",
            description="Enterprise Project Intelligence Layer",
            version="0.1.0",
        )
        ide_intelligence_desc = ServiceDescriptor(
            name="ide_intelligence",
            category="Core",
            description="Enterprise IDE Intelligence Layer",
            version="0.1.0",
        )
        repository_intelligence_desc = ServiceDescriptor(
            name="repository_intelligence",
            category="Core",
            description="Enterprise Repository Intelligence Layer",
            version="0.1.0",
        )
        command_intelligence_desc = ServiceDescriptor(
            name="command_intelligence",
            category="Core",
            description="Enterprise Command Intelligence Layer",
            version="0.1.0",
        )
        documentation_intelligence_desc = ServiceDescriptor(
            name="documentation_intelligence",
            category="Core",
            description="Enterprise Documentation & Engineering Knowledge Layer",
            version="0.1.0",
        )
        engineering_diagnostics_desc = ServiceDescriptor(
            name="engineering_diagnostics",
            category="Core",
            description="Enterprise Engineering Diagnostics & Refactoring Layer",
            version="0.1.0",
        )
        workspace_intelligence_desc = ServiceDescriptor(
            name="workspace_intelligence",
            category="Core",
            description="Enterprise Workspace Intelligence Layer",
            version="0.1.0",
        )
        engineering_observability_desc = ServiceDescriptor(
            name="engineering_observability",
            category="Core",
            description="Enterprise Engineering Observability Layer",
            version="0.1.0",
        )
        perception_engine_desc = ServiceDescriptor(
            name="perception_engine",
            category="Core",
            description="Enterprise Perception Engine & Observation Framework Layer",
            version="0.1.0",
        )
        screen_intelligence_desc = ServiceDescriptor(
            name="screen_intelligence",
            category="Core",
            description="Enterprise Screen Intelligence Layer",
            version="0.1.0",
        )
        document_ocr_intelligence_desc = ServiceDescriptor(
            name="document_ocr_intelligence",
            category="Core",
            description="Enterprise Document OCR Intelligence Layer",
            version="0.1.0",
        )
        browser_perception_desc = ServiceDescriptor(
            name="browser_perception",
            category="Core",
            description="Enterprise Browser Perception Layer",
            version="0.1.0",
        )
        ui_semantic_intelligence_desc = ServiceDescriptor(
            name="ui_semantic_intelligence",
            category="Core",
            description="Enterprise UI Semantic Intelligence Layer",
            version="0.1.0",
        )
        desktop_perception_desc = ServiceDescriptor(
            name="desktop_perception",
            category="Core",
            description="Enterprise Desktop Application Intelligence Layer",
            version="0.1.0",
        )
        visual_memory_intelligence_desc = ServiceDescriptor(
            name="visual_memory_intelligence",
            category="Core",
            description="Enterprise Visual Memory & Spatial Intelligence Layer",
            version="0.1.0",
        )
        context_fusion_desc = ServiceDescriptor(
            name="context_fusion",
            category="Core",
            description="Enterprise Unified Context Fusion Layer",
            version="0.1.0",
        )
        perception_evaluation_desc = ServiceDescriptor(
            name="perception_evaluation",
            category="Core",
            description="Enterprise Perception Evaluation Layer",
            version="0.1.0",
        )
        perception_security_desc = ServiceDescriptor(
            name="perception_security",
            category="Core",
            description="Enterprise Perception Security Layer",
            version="0.1.0",
        )
        agent_runtime_desc = ServiceDescriptor(
            name="agent_runtime",
            category="Core",
            description="Enterprise Agent Runtime Kernel",
            version="0.1.0",
        )

        self.registry.register_service(config_desc)
        self.registry.register_service(logger_desc)
        self.registry.register_service(registry_desc)
        self.registry.register_service(event_bus_desc)
        self.registry.register_service(lifecycle_desc)
        self.registry.register_service(kernel_desc)
        self.registry.register_service(observability_desc)
        self.registry.register_service(audio_desc)
        self.registry.register_service(wake_word_desc)
        self.registry.register_service(speech_recognition_desc)
        self.registry.register_service(voice_session_desc)
        self.registry.register_service(intent_desc)
        self.registry.register_service(request_normalization_desc)
        self.registry.register_service(brain_desc)
        self.registry.register_service(model_router_desc)
        self.registry.register_service(reasoning_desc)
        self.registry.register_service(planner_desc)
        self.registry.register_service(goal_manager_desc)
        self.registry.register_service(task_graph_desc)
        self.registry.register_service(execution_planner_desc)
        self.registry.register_service(brain_runtime_desc)
        self.registry.register_service(brain_evaluator_desc)
        self.registry.register_service(skill_engine_desc)
        self.registry.register_service(permission_manager_desc)
        self.registry.register_service(application_manager_desc)
        self.registry.register_service(filesystem_manager_desc)
        self.registry.register_service(terminal_manager_desc)
        self.registry.register_service(browser_manager_desc)
        self.registry.register_service(skill_runtime_desc)
        self.registry.register_service(safety_engine_desc)
        self.registry.register_service(skill_evaluator_desc)
        self.registry.register_service(workflow_engine_desc)
        self.registry.register_service(wdl_parser_desc)
        self.registry.register_service(workflow_runtime_desc)
        self.registry.register_service(workflow_context_desc)
        self.registry.register_service(decision_engine_desc)
        self.registry.register_service(dependency_scheduler_desc)
        self.registry.register_service(recovery_engine_desc)
        self.registry.register_service(workflow_analytics_desc)
        self.registry.register_service(memory_engine_desc)
        self.registry.register_service(working_memory_desc)
        self.registry.register_service(episodic_memory_desc)
        self.registry.register_service(semantic_memory_desc)
        self.registry.register_service(procedural_memory_desc)
        self.registry.register_service(knowledge_graph_desc)
        self.registry.register_service(retrieval_engine_desc)
        self.registry.register_service(learning_engine_desc)
        self.registry.register_service(memory_evaluator_desc)
        self.registry.register_service(backup_manager_desc)
        self.registry.register_service(capability_engine_desc)
        self.registry.register_service(workspace_engine_desc)
        self.registry.register_service(discovery_manager_desc)
        self.registry.register_service(intelligence_manager_desc)
        self.registry.register_service(ide_intelligence_desc)
        self.registry.register_service(repository_intelligence_desc)
        self.registry.register_service(command_intelligence_desc)
        self.registry.register_service(documentation_intelligence_desc)
        self.registry.register_service(engineering_diagnostics_desc)
        self.registry.register_service(workspace_intelligence_desc)
        self.registry.register_service(engineering_observability_desc)
        self.registry.register_service(perception_engine_desc)
        self.registry.register_service(screen_intelligence_desc)
        self.registry.register_service(document_ocr_intelligence_desc)
        self.registry.register_service(browser_perception_desc)
        self.registry.register_service(ui_semantic_intelligence_desc)
        self.registry.register_service(desktop_perception_desc)
        self.registry.register_service(visual_memory_intelligence_desc)
        self.registry.register_service(context_fusion_desc)
        self.registry.register_service(perception_evaluation_desc)
        self.registry.register_service(perception_security_desc)
        self.registry.register_service(agent_runtime_desc)

        # Set status to READY for startup completed core components
        self.registry.update_service("config", "READY")
        self.registry.update_service("logger", "READY")
        self.registry.update_service("service_registry", "READY")
        self.registry.update_service("event_bus", "READY")
        self.registry.update_service("lifecycle_orchestrator", "READY")
        self.registry.update_service("kernel", "READY")
        self.registry.update_service("observability", "READY")
        self.registry.update_service("audio", "READY")
        self.registry.update_service("wake_word", "READY")
        self.registry.update_service("speech_recognition", "READY")
        self.registry.update_service("voice_session", "READY")
        self.registry.update_service("intent", "READY")
        self.registry.update_service("request_normalization", "READY")
        self.registry.update_service("brain", "READY")
        self.registry.update_service("model_router", "READY")
        self.registry.update_service("reasoning", "READY")
        self.registry.update_service("planner", "READY")
        self.registry.update_service("goal_manager", "READY")
        self.registry.update_service("task_graph", "READY")
        self.registry.update_service("execution_planner", "READY")
        self.registry.update_service("brain_runtime", "READY")
        self.registry.update_service("brain_evaluator", "READY")
        self.registry.update_service("skill_engine", "READY")
        self.registry.update_service("permission_manager", "READY")
        self.registry.update_service("application_manager", "READY")
        self.registry.update_service("filesystem_manager", "READY")
        self.registry.update_service("terminal_manager", "READY")
        self.registry.update_service("browser_manager", "READY")
        self.registry.update_service("skill_runtime", "READY")
        self.registry.update_service("safety_engine", "READY")
        self.registry.update_service("skill_evaluator", "READY")
        self.registry.update_service("workflow_engine", "READY")
        self.registry.update_service("wdl_parser", "READY")
        self.registry.update_service("workflow_runtime_service", "READY")
        self.registry.update_service("workflow_context", "READY")
        self.registry.update_service("decision_engine", "READY")
        self.registry.update_service("dependency_scheduler", "READY")
        self.registry.update_service("recovery_engine", "READY")
        self.registry.update_service("workflow_analytics", "READY")
        self.registry.update_service("memory_engine", "READY")
        self.registry.update_service("working_memory", "READY")
        self.registry.update_service("episodic_memory", "READY")
        self.registry.update_service("semantic_memory", "READY")
        self.registry.update_service("procedural_memory", "READY")
        self.registry.update_service("knowledge_graph", "READY")
        self.registry.update_service("retrieval_engine", "READY")
        self.registry.update_service("learning_engine", "READY")
        self.registry.update_service("memory_evaluator", "READY")
        self.registry.update_service("backup_manager", "READY")
        self.registry.update_service("capability_engine", "READY")
        self.registry.update_service("workspace_engine", "READY")
        self.registry.update_service("discovery_manager", "READY")
        self.registry.update_service("intelligence_manager", "READY")
        self.registry.update_service("ide_intelligence", "READY")
        self.registry.update_service("repository_intelligence", "READY")
        self.registry.update_service("command_intelligence", "READY")
        self.registry.update_service("documentation_intelligence", "READY")
        self.registry.update_service("engineering_diagnostics", "READY")
        self.registry.update_service("workspace_intelligence", "READY")
        self.registry.update_service("engineering_observability", "READY")
        self.registry.update_service("perception_engine", "READY")
        self.registry.update_service("screen_intelligence", "READY")
        self.registry.update_service("document_ocr_intelligence", "READY")
        self.registry.update_service("browser_perception", "READY")
        self.registry.update_service("ui_semantic_intelligence", "READY")
        self.registry.update_service("desktop_perception", "READY")
        self.registry.update_service("visual_memory_intelligence", "READY")
        self.registry.update_service("context_fusion", "READY")
        self.registry.update_service("perception_evaluation", "READY")
        self.registry.update_service("perception_security", "READY")
        self.registry.update_service("agent_runtime", "READY")

        # 9. Validate Registries constraints
        self.container.validate_container()
        self.registry.validate_registry()

        self.logger.info(
            "System bootstrap completed with DI and Service Registry wired",
            env=self.config.env.profile,
            data_dir=str(self.config.paths.data_dir),
            services=self.registry.export_registry(),
        )

        return self.config

    @staticmethod
    def validate_environment() -> None:
        """Validate base requirements and load env files."""
        # Load dotenv file if present
        if Path(".env").exists():
            load_dotenv()

    @staticmethod
    def create_directories(config: AppConfig) -> None:
        """Ensure all required system paths exist on disk."""
        directories = [
            config.paths.data_dir,
            config.paths.config_dir,
            config.paths.log_dir,
            config.paths.backup_dir,
            config.paths.skills_dir,
            config.paths.plugins_dir,
        ]
        for dir_path in directories:
            dir_path.mkdir(parents=True, exist_ok=True)
            # Log directly using stdout since structlog is not wired yet
            if config.env.profile == "development":
                print(f"[Bootstrap] Ensuring directory exists: {dir_path}")


class ShutdownManager:
    """Handles Graceful Shutdown procedures and resource release."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def execute_shutdown(self) -> None:
        """Safely close active system hooks, files, and DB engines."""
        logger.info("Executing system shutdown lifecycle...")
        # Placeholder for later phases:
        # - Close DB connection pools
        # - Stop scheduler and thread pool execution loops
        # - Deactivate plugins
        logger.info("Shutdown lifecycle completed. Exit successful.")
