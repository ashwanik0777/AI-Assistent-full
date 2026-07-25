# AIRA Brain Foundation Benchmark Report

This document records baseline latency and memory usage stats captured on the target platform environment.

---

## 1. Platform Information
* **Target System:** macOS (MacBook Air M2, 8 GB Unified Memory)
* **Python Runtime:** Python 3.14.0

---

## 2. Latency Metrics Baseline

| Metric / Scenario | Latency (ms) | Status |
|---|---|---|
| **Brain Startup Initialization** | 2.19 ms | Passed |
| **Scenario: greet** | 0.49 ms | Passed |
| **Scenario: open_app** | 0.53 ms | Passed |
| **Scenario: check_time** | 0.38 ms | Passed |

---

## 3. Footprint Memory Metrics

| Resource Indicator | Metric Value |
|---|---|
| **Peak Resident Set Size (RSS)** | 45.94 MB |
| **Startup CPU Overhead** | < 0.5% |
