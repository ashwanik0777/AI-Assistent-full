# AIRA Workflow Foundation — WDL Migration Guide

This guide describes migrating legacy workflows definitions to standard **WDL v1** configurations.

---

## 1. Upgrading Variables Syntax

Legacy config files defined variables inside single dictionaries. WDL v1 organizes variables into scoped mappings:

### Legacy Config Format
```json
{
  "variables": {
    "user_id": "usr_99"
  }
}
```

### WDL v1 Scoped Format
```json
{
  "variables": {
    "WORKFLOW": {
      "user_id": "usr_99"
    }
  }
}
```

---

## 2. Checkpoint Snapshot Updates

Checkpoint formats are self-contained. Snapshots from legacy draft systems must have their `version` field updated to `"1.0.0"` before context restoration runs will succeed.
