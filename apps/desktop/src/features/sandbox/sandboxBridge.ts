import { invoke } from "@airbench/tauri-invoke";
import { invokeOrThrow } from "../../lib/errors";

class InvalidSandboxResponse extends Error {
  readonly code = "invalid_sandbox_response";
}

function requireRecord(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new InvalidSandboxResponse(`The desktop process returned an invalid ${label}.`);
  return value as Record<string, unknown>;
}

function requireString(value: unknown, label: string): string {
  if (typeof value !== "string") throw new InvalidSandboxResponse(`The desktop process returned an invalid ${label}.`);
  return value;
}

function requireInteger(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isInteger(value)) throw new InvalidSandboxResponse(`The desktop process returned an invalid ${label}.`);
  return value;
}

function requireBoolean(value: unknown, label: string): boolean {
  if (typeof value !== "boolean") throw new InvalidSandboxResponse(`The desktop process returned an invalid ${label}.`);
  return value;
}

export interface SandboxRunResult {
  stdout: string;
  stderr: string;
  exitCode: number;
  timedOut: boolean;
}

export async function runPythonSandbox(code: string): Promise<SandboxRunResult> {
  const raw = await invokeOrThrow(invoke<unknown>("run_python_sandbox", { code }));
  const record = requireRecord(raw, "sandbox run result");
  return {
    stdout: requireString(record.stdout, "sandbox stdout"),
    stderr: requireString(record.stderr, "sandbox stderr"),
    exitCode: requireInteger(record.exit_code, "sandbox exit code"),
    timedOut: requireBoolean(record.timed_out, "sandbox timeout flag"),
  };
}
