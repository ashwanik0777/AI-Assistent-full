# CHANGELOG — AIRA AI Operating System

All notable changes to the AIRA AI Operating System will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.5.0-alpha1] — 2026-07-12

### Added
- **Workflow Definition Language (WDL):** Unified workflow parser converting serializable JSON configurations into DAG models.
- **Workflow Runtime:** Steps sequence execution manager delegating execution tasks down to the Skill Runtime.
- **Workflow Context Store:** Scoped system variables context mapping system.
- **Decision Branching Engine:** Multi-branch conditional resolvers and loop controls.
- **Dependency Graph Scheduler:** Parallel multi-threaded execution queue supporting independent task nodes execution concurrently.
- **Checkpoint, Recovery & Resume:** Snapshot serialization mechanism saving cursor records and restoring state context on restarts.
- **Workflow Analytics:** Optimization scanners recommending bottlenecks improvements and execution replayer.
