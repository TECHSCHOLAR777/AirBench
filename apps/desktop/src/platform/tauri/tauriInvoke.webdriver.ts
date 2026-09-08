import { invoke as nativeInvoke } from "@tauri-apps/api/core";

/**
 * The WDIO guest plugin intercepts the global Tauri core surface. The
 * production bridge remains the normal @tauri-apps/api/core implementation.
 */
export function invoke<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  const webdriverMock = window.__wdio_mocks__?.[command];
  if (typeof webdriverMock === "function") {
    return Promise.resolve(webdriverMock(args) as T);
  }

  const globalInvoke = window.__TAURI__?.core?.invoke as ((command: string, args?: Record<string, unknown>) => Promise<unknown>) | undefined;
  return globalInvoke ? (globalInvoke(command, args) as Promise<T>) : nativeInvoke<T>(command, args);
}
