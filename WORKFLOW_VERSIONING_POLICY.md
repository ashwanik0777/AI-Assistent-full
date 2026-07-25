# AIRA Workflow Foundation — Versioning Policy

This document defines the compatibility requirements and progression patterns for the **AIRA Workflow Foundation**.

---

## 1. SemVer Compliance Rules

The platform adheres to [Semantic Versioning (SemVer) 2.0.0](https://semver.org/):
* **MAJOR (X.y.z):** Incremented for incompatible interface updates (e.g. altering core `WdlParserManager` signatures).
* **MINOR (x.Y.z):** Incremented for backward-compatible capabilities additions (e.g. adding new scopes parameters to `WorkflowContextManager`).
* **PATCH (x.y.Z):** Incremented for backward-compatible bug fixes or documentation updates.

---

## 2. WDL Schema Compatibility

- **Backward Compatibility:** All WDL v1 engines MUST support running configurations written for earlier v1 draft releases.
- **Deprecation Strategy:** Interface attributes deprecated in minor revisions are maintained until the next major release milestone.
