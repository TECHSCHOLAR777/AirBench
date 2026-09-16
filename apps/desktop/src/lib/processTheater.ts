/**
 * Drives a staged "the pipeline is really working" sequence: a fixed set of
 * named phases, each revealing a few log lines over ~3s, so the UI shows
 * planning/retrieval/verification-style progress before a final answer
 * appears. When `waitFor` is supplied (e.g. a real backend call), the last
 * phase holds until that promise settles too, so the staged pacing never
 * outruns — or hides — genuine completion.
 */

export interface ProcessPhase {
  id: string;
  label: string;
  logs: string[];
  durationMs?: number;
}

export interface ProcessTheaterState {
  phaseIndex: number;
  phase: ProcessPhase | null;
  lines: string[];
  done: boolean;
}

const DEFAULT_PHASE_DURATION_MS = 3000;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export async function runProcessTheater(
  phases: ProcessPhase[],
  onUpdate: (state: ProcessTheaterState) => void,
  opts: { waitFor?: Promise<unknown> } = {},
): Promise<void> {
  const revealed: string[] = [];
  for (let index = 0; index < phases.length; index += 1) {
    const phase = phases[index];
    const duration = phase.durationMs ?? DEFAULT_PHASE_DURATION_MS;
    const slice = duration / (phase.logs.length + 1);
    onUpdate({ phaseIndex: index, phase, lines: [...revealed], done: false });
    for (const line of phase.logs) {
      await sleep(slice);
      revealed.push(line);
      onUpdate({ phaseIndex: index, phase, lines: [...revealed], done: false });
    }
    await sleep(slice);
  }
  if (opts.waitFor) {
    onUpdate({ phaseIndex: phases.length - 1, phase: phases[phases.length - 1] ?? null, lines: revealed, done: false });
    await opts.waitFor;
  }
  onUpdate({ phaseIndex: phases.length, phase: null, lines: revealed, done: true });
}
