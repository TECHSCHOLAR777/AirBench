import type { ProcessPhase } from "../../lib/processTheater";

/**
 * Cosmetic-only "container" framing for the sandbox terminal. The Python
 * code still runs for real via `runPythonSandbox` (see sandboxBridge.ts) —
 * this module only manufactures the boot chatter and identity chips shown
 * around that real run, matching the demo's CLI look.
 */

export interface ContainerIdentity {
  containerId: string;
  image: string;
  ipcSocket: string;
  ledgerCursor: string;
  workerPool: string;
}

function hex(length: number): string {
  let out = "";
  for (let index = 0; index < length; index += 1) out += Math.floor(Math.random() * 16).toString(16);
  return out;
}

export function createContainerIdentity(): ContainerIdentity {
  return {
    containerId: `sbx-${hex(12)}`,
    image: "airbench/sandbox-runtime:py3.11-slim",
    ipcSocket: "ipc:///tmp/airbench.sock",
    ledgerCursor: `0x${hex(8)}`,
    workerPool: "2/4 idle",
  };
}

export function createIdleLines(identity: ContainerIdentity): string[] {
  return [
    `STATUS: IDLE | CURSOR: ${identity.ledgerCursor} | LISTEN: ${identity.ipcSocket}`,
    "",
    `[DAEMON] Sovereign handshake verified. Local crypto engine initialized: Ed25519-SHA512.`,
    `[ENCLAVE] Zero unauthorized mutations detected in workspace journal since genesis block 0x0000.`,
  ];
}

export function createBootPhases(identity: ContainerIdentity): ProcessPhase[] {
  return [
    {
      id: "spawn",
      label: "Spawn",
      durationMs: 700,
      logs: [
        `[DAEMON] Requesting worker lease from pool (${identity.workerPool})...`,
        `[DAEMON] Container ${identity.containerId} scheduled from image ${identity.image}.`,
      ],
    },
    {
      id: "attach",
      label: "Attach",
      durationMs: 500,
      logs: [
        `[ENCLAVE] Mounting ephemeral workspace, network egress disabled.`,
        `[DAEMON] stdout/stderr pipes attached over ${identity.ipcSocket}.`,
      ],
    },
    {
      id: "exec",
      label: "Exec",
      durationMs: 400,
      logs: [`[DAEMON] Executing script.py inside ${identity.containerId}...`],
    },
  ];
}
