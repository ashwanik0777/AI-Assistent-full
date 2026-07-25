"""Orchestrator and application bootstrap loop for AIRA."""

import sys

import structlog
from rich.align import Align
from rich.console import Console
from rich.panel import Panel

from aira.core.bootstrap import BootstrapManager, ShutdownManager
from aira.infrastructure.config import AppConfig

logger = structlog.getLogger("aira.app")
console = Console()


class AIRAApplication:
    """Core application coordinator managing execution state and lifecycles."""

    def __init__(self) -> None:
        self.config: AppConfig | None = None
        self.shutdown_manager: ShutdownManager | None = None
        from aira.infrastructure.di_container import DependencyContainer

        self.container: DependencyContainer | None = None
        from aira.infrastructure.service_registry import ServiceRegistry

        self.registry: ServiceRegistry | None = None
        from aira.infrastructure.event_bus import EventBus

        self.event_bus: EventBus | None = None
        from aira.infrastructure.lifecycle import LifecycleOrchestrator

        self.lifecycle: LifecycleOrchestrator | None = None
        from aira.infrastructure.kernel import AIRAKernel

        self.kernel: AIRAKernel | None = None
        from aira.infrastructure.observability import ObservabilityFramework

        self.observability: ObservabilityFramework | None = None
        from aira.infrastructure.audio import AudioManager

        self.audio: AudioManager | None = None
        from aira.infrastructure.wake_word import WakeWordManager

        self.wake_word: WakeWordManager | None = None
        from aira.infrastructure.speech_recognition import SpeechRecognitionManager

        self.speech_recognition: SpeechRecognitionManager | None = None
        from aira.infrastructure.intent import IntentManager

        self.intent: IntentManager | None = None
        from aira.infrastructure.request_normalization import RequestManager

        self.request_normalization: RequestManager | None = None
        from aira.infrastructure.voice_session import VoiceSessionManager

        self.voice_session: VoiceSessionManager | None = None
        from aira.infrastructure.brain_core import BrainManager

        self.brain: BrainManager | None = None
        from aira.infrastructure.model_router import ModelRouterManager

        self.model_router: ModelRouterManager | None = None
        from aira.infrastructure.reasoning_interface import ReasoningManager

        self.reasoning: ReasoningManager | None = None
        from aira.infrastructure.planner import PlannerManager

        self.planner: PlannerManager | None = None
        from aira.infrastructure.goal_manager import GoalManager

        self.goal_manager: GoalManager | None = None
        from aira.infrastructure.task_graph import TaskGraphManager

        self.task_graph: TaskGraphManager | None = None
        from aira.infrastructure.execution_planner import ExecutionPlannerManager

        self.execution_planner: ExecutionPlannerManager | None = None
        from aira.infrastructure.brain_runtime import BrainRuntimePipeline

        self.brain_runtime: BrainRuntimePipeline | None = None
        from aira.infrastructure.brain_evaluator import BrainEvaluatorManager

        self.brain_evaluator: BrainEvaluatorManager | None = None
        from aira.infrastructure.skill_engine import SkillEngineManager

        self.skill_engine: SkillEngineManager | None = None
        from aira.infrastructure.permission_manager import PermissionManager

        self.permission_manager: PermissionManager | None = None
        from aira.infrastructure.app_skills import ApplicationManager

        self.application_manager: ApplicationManager | None = None
        from aira.infrastructure.fs_skills import FilesystemManager

        self.filesystem_manager: FilesystemManager | None = None
        from aira.infrastructure.terminal_skills import TerminalManager

        self.terminal_manager: TerminalManager | None = None
        from aira.infrastructure.browser_skills import BrowserManager

        self.browser_manager: BrowserManager | None = None
        from aira.infrastructure.skill_runtime import SkillRuntimeManager

        self.skill_runtime: SkillRuntimeManager | None = None
        from aira.infrastructure.safety_framework import SafetyEngine

        self.safety_engine: SafetyEngine | None = None
        from aira.infrastructure.skill_evaluator import SkillEvaluationManager

        self.skill_evaluator: SkillEvaluationManager | None = None
        from aira.infrastructure.workflow_engine import WorkflowEngineManager

        self.workflow_engine: WorkflowEngineManager | None = None
        from aira.infrastructure.wdl_parser import WdlParser

        self.wdl_parser: WdlParser | None = None
        from aira.infrastructure.workflow_runtime import WorkflowRuntimeManager

        self.workflow_runtime: WorkflowRuntimeManager | None = None
        from aira.infrastructure.workflow_context import WorkflowContextManager

        self.workflow_context_manager: WorkflowContextManager | None = None
        from aira.infrastructure.decision_engine import DecisionEngineManager

        self.decision_engine: DecisionEngineManager | None = None
        from aira.infrastructure.dependency_scheduler import DependencySchedulerManager

        self.dependency_scheduler: DependencySchedulerManager | None = None
        from aira.infrastructure.recovery_engine import CheckpointEngineManager

        self.recovery_engine: CheckpointEngineManager | None = None
        from aira.infrastructure.workflow_analytics import WorkflowAnalyticsManager

        self.workflow_analytics: WorkflowAnalyticsManager | None = None
        from aira.infrastructure.memory_engine import MemoryOrchestrator

        self.memory_engine: MemoryOrchestrator | None = None
        from aira.infrastructure.working_memory import WorkingMemoryManager

        self.working_memory: WorkingMemoryManager | None = None
        from aira.infrastructure.episodic_memory import EpisodeStore

        self.episodic_memory: EpisodeStore | None = None
        from aira.infrastructure.semantic_memory import SemanticStore

        self.semantic_memory: SemanticStore | None = None
        from aira.infrastructure.procedural_memory import ProcedureLibrary

        self.procedural_memory: ProcedureLibrary | None = None
        from aira.infrastructure.knowledge_graph import KnowledgeGraphStore

        self.knowledge_graph: KnowledgeGraphStore | None = None
        from aira.infrastructure.learning_engine import MemoryConsolidationEngine

        self.learning_engine: MemoryConsolidationEngine | None = None
        from aira.infrastructure.memory_evaluator import MemoryEvaluatorEngine

        self.memory_evaluator: MemoryEvaluatorEngine | None = None
        from aira.infrastructure.memory_backup import BackupManager

        self.backup_manager: BackupManager | None = None
        from aira.infrastructure.capability_engine import CapabilityEngine

        self.capability_engine: CapabilityEngine | None = None
        from aira.infrastructure.workspace_engine import DeveloperWorkspaceEngine

        self.workspace_engine: DeveloperWorkspaceEngine | None = None
        from aira.infrastructure.workspace_discovery import WorkspaceDiscoveryManager

        self.discovery_manager: WorkspaceDiscoveryManager | None = None
        from aira.infrastructure.project_intelligence import ProjectIntelligenceManager

        self.intelligence_manager: ProjectIntelligenceManager | None = None
        from aira.infrastructure.ide_intelligence import IDEIntelligenceManager

        self.ide_intelligence: IDEIntelligenceManager | None = None
        from aira.infrastructure.repository_intelligence import RepositoryIntelligenceManager

        self.repository_intelligence: RepositoryIntelligenceManager | None = None
        from aira.infrastructure.command_intelligence import CommandIntelligenceManager

        self.command_intelligence: CommandIntelligenceManager | None = None
        from aira.infrastructure.documentation_intelligence import DocumentationIntelligenceManager

        self.documentation_intelligence: DocumentationIntelligenceManager | None = None
        from aira.infrastructure.engineering_diagnostics import EngineeringDiagnosticsEngine

        self.engineering_diagnostics: EngineeringDiagnosticsEngine | None = None
        from aira.infrastructure.workspace_intelligence import WorkspaceIntelligenceManager

        self.workspace_intelligence: WorkspaceIntelligenceManager | None = None
        from aira.infrastructure.engineering_observability import EngineeringObservabilityManager

        self.engineering_observability: EngineeringObservabilityManager | None = None
        from aira.infrastructure.perception_engine import PerceptionEngine

        self.perception_engine: PerceptionEngine | None = None
        from aira.infrastructure.screen_intelligence import ScreenIntelligenceManager

        self.screen_intelligence: ScreenIntelligenceManager | None = None
        from aira.infrastructure.document_ocr_intelligence import DocumentOCRIntelligenceManager

        self.document_ocr_intelligence: DocumentOCRIntelligenceManager | None = None
        from aira.infrastructure.browser_perception import BrowserPerceptionEngine

        self.browser_perception: BrowserPerceptionEngine | None = None
        from aira.infrastructure.ui_semantic_intelligence import UISemanticIntelligenceManager

        self.ui_semantic_intelligence: UISemanticIntelligenceManager | None = None
        from aira.infrastructure.desktop_application_intelligence import DesktopPerceptionEngine

        self.desktop_perception: DesktopPerceptionEngine | None = None
        from aira.infrastructure.visual_memory_intelligence import VisualMemoryManager

        self.visual_memory_intelligence: VisualMemoryManager | None = None
        from aira.infrastructure.unified_context_fusion import UnifiedContextFusionEngine

        self.context_fusion: UnifiedContextFusionEngine | None = None
        from aira.infrastructure.perception_evaluation import PerceptionEvaluationEngine

        self.perception_evaluation: PerceptionEvaluationEngine | None = None
        from aira.infrastructure.perception_security import PerceptionTrustEngine

        self.perception_security: PerceptionTrustEngine | None = None
        from aira.infrastructure.agent_runtime import AgentRuntimeKernel

        self.agent_runtime: AgentRuntimeKernel | None = None

    def start(self) -> None:
        """Boot the application foundation, validate states, and display intro."""
        try:
            # 1. System Boot and Setup
            bootstrap = BootstrapManager()
            self.config = bootstrap.execute_bootstrap()
            self.container = bootstrap.container
            self.registry = bootstrap.registry
            self.event_bus = bootstrap.event_bus
            self.lifecycle = bootstrap.lifecycle
            self.kernel = bootstrap.kernel
            self.observability = bootstrap.observability
            self.audio = bootstrap.audio
            self.wake_word = bootstrap.wake_word
            self.speech_recognition = bootstrap.speech_recognition
            self.intent = bootstrap.intent
            self.request_normalization = bootstrap.request_normalization
            self.voice_session = bootstrap.voice_session
            self.brain = bootstrap.brain
            self.model_router = bootstrap.model_router
            self.reasoning = bootstrap.reasoning
            self.planner = bootstrap.planner
            self.goal_manager = bootstrap.goal_manager
            self.task_graph = bootstrap.task_graph
            self.execution_planner = bootstrap.execution_planner
            self.brain_runtime = bootstrap.brain_runtime
            self.brain_evaluator = bootstrap.brain_evaluator
            self.skill_engine = bootstrap.skill_engine
            self.permission_manager = bootstrap.permission_manager
            self.application_manager = bootstrap.application_manager
            self.filesystem_manager = bootstrap.filesystem_manager
            self.terminal_manager = bootstrap.terminal_manager
            self.browser_manager = bootstrap.browser_manager
            self.skill_runtime = bootstrap.skill_runtime
            self.safety_engine = bootstrap.safety_engine
            self.skill_evaluator = bootstrap.skill_evaluator
            self.workflow_engine = bootstrap.workflow_engine
            self.wdl_parser = bootstrap.wdl_parser
            self.workflow_runtime = bootstrap.workflow_runtime
            self.workflow_context_manager = bootstrap.workflow_context_manager
            self.decision_engine = bootstrap.decision_engine
            self.dependency_scheduler = bootstrap.dependency_scheduler
            self.recovery_engine = bootstrap.recovery_engine
            self.workflow_analytics = bootstrap.workflow_analytics
            self.memory_engine = bootstrap.memory_engine
            self.working_memory = bootstrap.working_memory
            self.episodic_memory = bootstrap.episodic_memory
            self.semantic_memory = bootstrap.semantic_memory
            self.procedural_memory = bootstrap.procedural_memory
            self.knowledge_graph = bootstrap.knowledge_graph
            self.learning_engine = bootstrap.learning_engine
            self.memory_evaluator = bootstrap.memory_evaluator
            self.backup_manager = bootstrap.backup_manager
            self.capability_engine = bootstrap.capability_engine
            self.workspace_engine = bootstrap.workspace_engine
            self.discovery_manager = bootstrap.discovery_manager
            self.intelligence_manager = bootstrap.intelligence_manager
            self.ide_intelligence = bootstrap.ide_intelligence
            self.repository_intelligence = bootstrap.repository_intelligence
            self.command_intelligence = bootstrap.command_intelligence
            self.documentation_intelligence = bootstrap.documentation_intelligence
            self.engineering_diagnostics = bootstrap.engineering_diagnostics
            self.workspace_intelligence = bootstrap.workspace_intelligence
            self.engineering_observability = bootstrap.engineering_observability
            self.perception_engine = bootstrap.perception_engine
            self.screen_intelligence = bootstrap.screen_intelligence
            self.document_ocr_intelligence = bootstrap.document_ocr_intelligence
            self.browser_perception = bootstrap.browser_perception
            self.ui_semantic_intelligence = bootstrap.ui_semantic_intelligence
            self.desktop_perception = bootstrap.desktop_perception
            self.visual_memory_intelligence = bootstrap.visual_memory_intelligence
            self.context_fusion = bootstrap.context_fusion
            self.perception_evaluation = bootstrap.perception_evaluation
            self.perception_security = bootstrap.perception_security
            self.agent_runtime = bootstrap.agent_runtime
            self.shutdown_manager = ShutdownManager(self.config)

            # 2. Show rich startup banner
            self.display_banner()

            # 3. Perform baseline health checks
            self.run_health_check()

            logger.info("AIRA Core application is ready.")

        except Exception as e:
            console.print(f"[bold red]CRITICAL: Application failed to boot: {e}[/bold red]")
            logger.exception("Application boot failure")
            sys.exit(1)

    def display_banner(self) -> None:
        """Render a styled CLI banner using Rich panels."""
        banner_text = (
            "[bold cyan]AIRA[/bold cyan]\n"
            "[dim]Artificial Intelligent Responsive Assistant[/dim]\n\n"
            "[green]Status: Online[/green] | "
            "[yellow]Version: 0.1.0[/yellow] | "
            "[blue]Target: macOS First[/blue]"
        )
        panel = Panel(
            Align.center(banner_text),
            border_style="cyan",
            title="[bold white]AIRA OS Baseline[/bold white]",
            subtitle="[dim]Sprint 1 Bootstrap Foundation[/dim]",
            expand=False,
        )
        console.print(panel)

    def run_health_check(self) -> None:
        """Execute diagnostic checks on base resources."""
        logger.info("Executing baseline health checks...")
        # Verify directories exist
        if self.config:
            assert self.config.paths.data_dir.exists(), "Data directory missing!"
            assert self.config.paths.config_dir.exists(), "Config directory missing!"
            assert self.config.paths.log_dir.exists(), "Log directory missing!"
        logger.info("Health Check Status: PASS")

    def stop(self) -> None:
        """Trigger Graceful Shutdown procedures."""
        if self.shutdown_manager:
            self.shutdown_manager.execute_shutdown()
        else:
            print("System shutdown triggered before complete bootstrap.")
            sys.exit(0)

    def run_interactive(self) -> None:
        """Interactive placeholder loop for users to interact."""
        console.print(
            "[bold yellow]AIRA CLI interactive loop initialized. Type 'exit' to quit.[/bold yellow]"
        )
        try:
            while True:
                user_input = input("AIRA > ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ("exit", "quit"):
                    break
                console.print(
                    f"[cyan]You typed:[/cyan] {user_input} "
                    "[dim](Core skills and NLP offline/deferred in Sprint 1)[/dim]"
                )
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Exit signal received.[/yellow]")
        finally:
            self.stop()
