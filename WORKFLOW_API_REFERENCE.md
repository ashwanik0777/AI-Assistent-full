# AIRA Workflow Foundation — Public API Reference (v0.5.1)

This reference outlines the public method contracts, input parameters, and return payloads for the frozen components of the **AIRA Enterprise Workflow Foundation**.

---

## 1. WdlParserManager

* **Class:** `aira.infrastructure.wdl_parser.WdlParserManager`
* **Method:** `parse_definition(self, filepath: Path) -> dict[str, Any]`
  - *Description:* Reads, validates, and parses a JSON WDL workflow configuration.
  - *Parameters:* `filepath` (Path to configuration file).
  - *Returns:* Structured dictionary representation of the workflow.

---

## 2. WorkflowContextManager

* **Class:** `aira.infrastructure.workflow_context.WorkflowContextManager`
* **Method:** `set_var(self, name: str, value: Any, scope: str = "WORKFLOW") -> None`
  - *Description:* Sets a variable within the specified scope block.
  - *Parameters:* `name` (str), `value` (Any), `scope` (str: `SYSTEM`, `WORKFLOW`, or `TEMP`).
* **Method:** `get_var(self, name: str) -> Any`
  - *Description:* Resolves a variable name.
  - *Returns:* Extracted value or `None`.

---

## 3. DependencySchedulerManager

* **Class:** `aira.infrastructure.dependency_scheduler.DependencySchedulerManager`
* **Method:** `run_parallel_tasks(self, graph: DependencyGraph, tasks_map: dict[str, Callable[[], Any]]) -> dict[str, Any]`
  - *Description:* Spawns parallel workers executing independent steps matching DAG.
  - *Parameters:* `graph` (DependencyGraph), `tasks_map` (dict[str, Callable]).
  - *Returns:* Dictionary of steps results mapped by task ID.

---

## 4. CheckpointEngineManager

* **Class:** `aira.infrastructure.recovery_engine.CheckpointEngineManager`
* **Method:** `create_checkpoint(self, checkpoint_id: str, workflow_id: str, execution_token: str, workflow_session_id: str, brain_session_id: str, cursor_index: int, context: WorkflowContextManager, save_path: Path) -> Checkpoint`
  - *Description:* Serializes context metrics to local JSON.
  - *Returns:* Checkpoint model instance.
