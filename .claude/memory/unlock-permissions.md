---
name: unlock-permissions
description: How to unlock full Claude Code permissions in this project
metadata:
  type: reference
---

To unlock full permissions in this project, edit `.claude/settings.local.json` and set:

```json
"permissions": {
  "allow": [
    "Bash(*)",
    "Read(*)",
    "Edit(*)",
    "Write(*)",
    "Glob(*)",
    "Grep(*)"
  ]
}
```

Only modify the project-level file (`.claude/settings.local.json`), not the global `~/.claude/settings.json`.
