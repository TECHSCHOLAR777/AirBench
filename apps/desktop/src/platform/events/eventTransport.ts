import { invoke } from "@airbench/tauri-invoke";
import type { ApprovedNodeProfileReference } from "../node/nodeConnection";
import { toNativeNodeProfileReference } from "../node/nodeBridge";
import { CORE_CONTRACT_COMPATIBILITY_ID, CORE_CONTRACT_SCHEMA_VERSION } from "../../generated/core_contracts";
import { FRONTEND_PROTOCOL_COMPATIBILITY_ID, FRONTEND_PROTOCOL_VERSION, normalizeTaskEventBatch, type Clearance, type TaskEventBatch } from "./protocol";
import type { NodeTaskEvent, NodeTaskEventBatch } from "../../generated/core_contracts";

export type { TaskEventBatch } from "./protocol";

export class EventTransportProtocolError extends Error {
  readonly code = "event_protocol_invalid";

  constructor(message: string) {
    super(message);
    this.name = "EventTransportProtocolError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireRecord(value: unknown, label: string): Record<string, unknown> {
  if (!isRecord(value)) throw new EventTransportProtocolError(`The Node returned an invalid ${label}.`);
  return value;
}

function requireNonEmptyString(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) throw new EventTransportProtocolError(`The Node returned an invalid ${label}.`);
  return value;
}

function requireClearance(value: unknown, label: string): Clearance {
  if (value !== "public" && value !== "internal" && value !== "restricted" && value !== "secret") {
    throw new EventTransportProtocolError(`The Node returned an invalid ${label}.`);
  }
  return value;
}

function requireSequence(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    throw new EventTransportProtocolError(`The Node returned an invalid ${label}.`);
  }
  return value;
}

function requireBoolean(value: unknown, label: string): boolean {
  if (typeof value !== "boolean") throw new EventTransportProtocolError(`The Node returned an invalid ${label}.`);
  return value;
}

function validateEvent(value: unknown, expectedTaskId: string, expectedProtocolVersion: string, expectedClearance: Clearance): NodeTaskEvent {
  const source = requireRecord(value, "task event");
  const event = {
    eventId: requireNonEmptyString(source.eventId, "event identity"),
    taskId: requireNonEmptyString(source.taskId, "event task identity"),
    sequence: requireSequence(source.sequence, "event sequence"),
    schemaVersion: requireNonEmptyString(source.schemaVersion, "event schema version"),
    compatibilityId: requireNonEmptyString(source.compatibilityId, "event compatibility identity"),
    eventType: requireNonEmptyString(source.eventType, "event type"),
    occurredAt: requireNonEmptyString(source.occurredAt, "event timestamp"),
    actor: requireNonEmptyString(source.actor, "event actor"),
    clearanceContext: requireClearance(source.clearanceContext, "event clearance"),
    payloadHash: requireNonEmptyString(source.payloadHash, "event payload hash"),
    ledgerEventRef: requireNonEmptyString(source.ledgerEventRef, "event ledger reference"),
    payload: requireRecord(source.payload, "event payload"),
  } satisfies NodeTaskEvent;

  if (event.taskId !== expectedTaskId || event.schemaVersion !== expectedProtocolVersion || event.compatibilityId !== FRONTEND_PROTOCOL_COMPATIBILITY_ID || event.clearanceContext !== expectedClearance) {
    throw new EventTransportProtocolError("The Node event metadata does not match the approved task stream.");
  }
  return event;
}

/**
 * Re-validates the native event response before normalization. Rust remains
 * authoritative for transport and identity; this guard prevents malformed
 * IPC data from being treated as a temporary reconnect or entering the task
 * projection as trusted activity.
 */
export function validateTaskEventBatch(
  value: unknown,
  profile: ApprovedNodeProfileReference,
  taskId: string,
  afterSequence: number,
): NodeTaskEventBatch {
  const source = requireRecord(value, "task event batch");
  const schemaVersion = requireNonEmptyString(source.schema_version, "event batch schema version");
  const compatibilityId = requireNonEmptyString(source.compatibility_id, "event batch compatibility identity");
  const streamId = requireNonEmptyString(source.stream_id, "event stream identity");
  const nodeIdentity = requireNonEmptyString(source.node_identity, "event stream Node identity");
  const protocolVersion = requireNonEmptyString(source.protocol_version, "event protocol version");
  const clearanceContext = requireClearance(source.clearance_context, "event batch clearance");
  if (schemaVersion !== CORE_CONTRACT_SCHEMA_VERSION || compatibilityId !== CORE_CONTRACT_COMPATIBILITY_ID || streamId !== taskId || nodeIdentity !== profile.nodeIdentity || protocolVersion !== profile.protocolVersion || clearanceContext !== profile.clearanceContext) {
    throw new EventTransportProtocolError("The Node event batch does not match the approved task stream.");
  }

  const rawEvents = source.events;
  const rawLedgerEventRefs = source.ledger_event_refs;
  if (!Array.isArray(rawEvents) || !Array.isArray(rawLedgerEventRefs)) {
    throw new EventTransportProtocolError("The Node returned an invalid event batch shape.");
  }
  if (rawLedgerEventRefs.length !== rawEvents.length) {
    throw new EventTransportProtocolError("The Node event batch is not aligned with its ledger references.");
  }

  let previousSequence = afterSequence;
  const events = rawEvents.map((value, index) => {
    const event = validateEvent(value, taskId, protocolVersion, clearanceContext);
    if (event.sequence <= previousSequence) throw new EventTransportProtocolError("The Node event sequence is not strictly increasing.");
    const ledgerEventRef = requireNonEmptyString(rawLedgerEventRefs[index], "event batch ledger reference");
    if (event.ledgerEventRef !== ledgerEventRef) throw new EventTransportProtocolError("The Node event ledger reference does not match the batch reference.");
    previousSequence = event.sequence;
    return event;
  });
  const nextSequence = requireSequence(source.next_sequence, "event batch cursor");
  const hasMore = requireBoolean(source.has_more, "event batch continuation flag");
  if (hasMore && events.length === 0) throw new EventTransportProtocolError("The Node marked an empty event batch as having more events.");
  // S3 audit fix: an empty terminal batch (events.length === 0, !hasMore) is valid when
  // nextSequence === afterSequence (nothing has changed). The old check compared against
  // previousSequence which is still afterSequence when no events are processed, and incorrectly
  // rejected batches where nextSequence === afterSequence.
  if (nextSequence < previousSequence || (!hasMore && events.length > 0 && nextSequence !== previousSequence)) {
    throw new EventTransportProtocolError("The Node event batch cursor does not match its events.");
  }

  return {
    schema_version: schemaVersion,
    compatibility_id: compatibilityId,
    stream_id: streamId,
    node_identity: nodeIdentity,
    protocol_version: protocolVersion,
    clearance_context: clearanceContext,
    events,
    next_sequence: nextSequence,
    has_more: hasMore,
    ledger_event_refs: rawLedgerEventRefs.map((value) => requireNonEmptyString(value, "event batch ledger reference")),
  };
}

export function toNativeEventProfile(profile: ApprovedNodeProfileReference) {
  return toNativeNodeProfileReference(profile);
}

/** Fetches a replayable cursor range through the Rust-owned Node transport. */
export function fetchTaskEventBatch(profile: ApprovedNodeProfileReference, taskId: string, afterSequence: number): Promise<TaskEventBatch> {
  if (!profile.approvedByPolicy || !profile.profileId.trim()) throw new Error("The approved Node profile is incomplete or not approved by policy.");
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(taskId)) throw new Error("The task identifier is invalid.");
  if (!Number.isSafeInteger(afterSequence) || afterSequence < 0) throw new Error("The event cursor is invalid.");
  return invoke<unknown>("fetch_task_events", {
    profileId: profile.profileId,
    taskId,
    afterSequence,
  }).then((value) => normalizeTaskEventBatch(validateTaskEventBatch(value, profile, taskId, afterSequence)));
}
