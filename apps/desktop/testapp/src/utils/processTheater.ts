/**
 * Process Theater (Execution State Machine)
 * Synchronized dual-track asynchronous engine:
 * - Track A (Background Work): Real compute task Promise (file parsing, sandbox execution, network call)
 * - Track B (Simulation / Telemetry Theater): Sequential milestone state machine
 *
 * Deterministic step transitions: pending (dimmed) -> running (active spinner) -> done (checkmark)
 * Waits for Promise.all([computePromise, theaterPromise]) before settling.
 */

export type PhaseStatus = 'pending' | 'running' | 'done';

export interface TheaterPhaseConfig {
  id: string;
  name: string;
  durationMs: number;
  logs: string[];
}

export interface LiveTheaterPhase {
  id: string;
  name: string;
  status: PhaseStatus;
  activeLog?: string;
}

export interface ProcessTheaterLog {
  id: string;
  time: string;
  phaseId: string;
  text: string;
  level?: 'info' | 'debug' | 'kernel' | 'success';
}

export interface ProcessTheaterState {
  isActive: boolean;
  phases: LiveTheaterPhase[];
  currentPhaseIndex: number;
  progressPercent: number;
  logs: ProcessTheaterLog[];
}

/**
 * Runs a dual-track asynchronous operation with synchronized state machine
 */
export async function runProcessTheater<T>(options: {
  computeTask: () => Promise<T>;
  phases: TheaterPhaseConfig[];
  onStateUpdate: (state: ProcessTheaterState) => void;
}): Promise<T> {
  const { computeTask, phases, onStateUpdate } = options;

  // Track A: Fire real background compute immediately
  const computePromise = computeTask();

  // Initial State: All phases pending
  let currentState: ProcessTheaterState = {
    isActive: true,
    phases: phases.map(p => ({
      id: p.id,
      name: p.name,
      status: 'pending'
    })),
    currentPhaseIndex: 0,
    progressPercent: 5,
    logs: [
      {
        id: `log-init-${Date.now()}`,
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        phaseId: phases[0]?.id || 'init',
        text: '[INIT] Synchronized dual-track execution engine started.',
        level: 'info'
      }
    ]
  };

  onStateUpdate({ ...currentState });

  // Track B: Sequential milestone state machine
  const theaterPromise = new Promise<void>(async (resolve) => {
    const totalPhases = phases.length;

    for (let i = 0; i < totalPhases; i++) {
      const phase = phases[i];

      // Transition to RUNNING
      const stepStartTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      const newLogs: ProcessTheaterLog[] = phase.logs.map((logText, lIdx) => ({
        id: `log-${phase.id}-${lIdx}-${Date.now()}`,
        time: stepStartTime,
        phaseId: phase.id,
        text: logText,
        level: logText.includes('[ERROR]') ? 'debug' : logText.includes('[✓]') || logText.includes('[READY]') ? 'success' : logText.includes('[KERNEL]') || logText.includes('[CUDA]') ? 'kernel' : 'info'
      }));

      currentState = {
        ...currentState,
        currentPhaseIndex: i,
        phases: currentState.phases.map((p, idx) => {
          if (idx < i) return { ...p, status: 'done' };
          if (idx === i) return { ...p, status: 'running', activeLog: phase.logs[0] };
          return { ...p, status: 'pending' };
        }),
        progressPercent: Math.min(95, Math.round(((i + 0.5) / totalPhases) * 100)),
        logs: [...currentState.logs, ...newLogs]
      };

      onStateUpdate({ ...currentState });

      // Wait controlled duration for this milestone phase
      await new Promise(r => setTimeout(r, phase.durationMs));

      // Transition to DONE
      currentState = {
        ...currentState,
        phases: currentState.phases.map((p, idx) => {
          if (idx <= i) return { ...p, status: 'done' };
          return { ...p, status: 'pending' };
        }),
        progressPercent: Math.round(((i + 1) / totalPhases) * 100)
      };

      onStateUpdate({ ...currentState });
    }

    resolve();
  });

  // Dual-Track settlement: Wait for BOTH Track A compute AND Track B simulation to settle
  const [computeResult] = await Promise.all([computePromise, theaterPromise]);

  // Final 100% state
  currentState = {
    ...currentState,
    isActive: false,
    progressPercent: 100,
    phases: currentState.phases.map(p => ({ ...p, status: 'done' })),
    logs: [
      ...currentState.logs,
      {
        id: `log-done-${Date.now()}`,
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        phaseId: 'complete',
        text: '[✓] Dual-track synchronization settled. Artifact unlocked.',
        level: 'success'
      }
    ]
  };

  onStateUpdate({ ...currentState });

  return computeResult;
}
