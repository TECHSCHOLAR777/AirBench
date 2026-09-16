/**
 * Tauri's `invoke()` rejects a failed command with the plain string from its
 * Rust `Result<T, String>` — not an `Error` — so `catch` blocks that only
 * handle `instanceof Error` silently swallow the real reason. Route rejected
 * native calls through this so callers always get a real Error to inspect.
 */
export function toError(thrown: unknown): Error {
  if (thrown instanceof Error) return thrown;
  if (typeof thrown === "string" && thrown.trim()) return new Error(thrown);
  return new Error("The desktop process returned an unrecognized error.");
}

export async function invokeOrThrow<T>(call: Promise<T>): Promise<T> {
  try {
    return await call;
  } catch (thrown) {
    throw toError(thrown);
  }
}
