import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { spawn } from "node:child_process";
import { join } from "node:path";

function emit(cwd: string, payload: object): Promise<void> {
  return new Promise((resolve) => {
    const child = spawn(join(cwd, ".claude/hooks/telemetry-log.sh"), [], {
      cwd,
      stdio: ["pipe", "ignore", "ignore"],
    });

    child.once("error", resolve);
    child.once("close", resolve);
    child.stdin.end(JSON.stringify(payload));
  });
}

export default function (pi: ExtensionAPI) {
  pi.on("session_start", async (event, ctx) => {
    await emit(ctx.cwd, {
      hook_event_name: "SessionStart",
      session_id: ctx.sessionManager.getSessionId(),
      source: event.reason,
    });
  });

  pi.on("input", async (event, ctx) => {
    await emit(ctx.cwd, {
      hook_event_name: "UserPromptSubmit",
      session_id: ctx.sessionManager.getSessionId(),
      prompt: event.text,
    });
  });

  pi.on("tool_execution_end", async (event, ctx) => {
    await emit(ctx.cwd, {
      hook_event_name: "PostToolUse",
      session_id: ctx.sessionManager.getSessionId(),
      tool_name: event.toolName,
      tool_use_succeeded: !event.isError,
      tool_input: event.args,
    });
  });

  pi.on("session_shutdown", async (event, ctx) => {
    await emit(ctx.cwd, {
      hook_event_name: "SessionEnd",
      session_id: ctx.sessionManager.getSessionId(),
      reason: event.reason,
    });
  });
}
