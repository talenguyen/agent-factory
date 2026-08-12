---
name: delegate-to-pi
description: Delegate a coding goal to a `pi` agent running under herdr — spawn or reuse it, feed it prompts, observe its interactive session, verify its work against the actual diff, and iterate until the goal is met or escalation is needed. Automatically sizes the model/thinking profile to the goal, confirming once before using the most capable tier; for `M`/`L`-tier goals, also spawns a second `pi` agent as an independent reviewer, stacked in its own herdr pane, and loops fixes between worker and reviewer until the reviewer approves. Use when the user asks to delegate to pi, have pi build/fix/implement something, or invokes /delegate-to-pi <goal>.
user-invocable: true
---

# delegate-to-pi

Set `FACTORY_MUX=herdr` and `FACTORY_WORKER=pi`, then invoke `orchestrate` with the
same goal. This compatibility alias preserves existing `/delegate-to-pi <goal>`
workflows while `bin/crew` executes the delegation mechanism.
