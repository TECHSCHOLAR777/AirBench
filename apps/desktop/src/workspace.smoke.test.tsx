// @vitest-environment jsdom
import { createElement, act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it, vi } from "vitest";

vi.mock("@airbench/tauri-invoke", () => ({ invoke: vi.fn(async () => null) }));

// jsdom does not implement element scrolling.
Element.prototype.scrollTo = () => {};

import { HomeView } from "./features/home/HomeView";
import { PidView } from "./features/pid/PidView";
import { ChatView } from "./features/chat/ChatView";
import { KnowledgeView } from "./features/knowledge/KnowledgeView";
import { ReviewView } from "./features/review/ReviewView";
import { SandboxView } from "./features/sandbox/SandboxView";
import { recordDeliverable } from "./features/deliverables/deliverableStore";

function mount(element: React.ReactElement): string {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => { root.render(element); });
  const html = container.innerHTML;
  act(() => { root.unmount(); });
  container.remove();
  return html;
}

describe("P&ID ground truth parses", () => {
  it("matches the shipped node and edge counts for every drawing", async () => {
    const { parsePidGraphml, pidSymbolsJson, processSymbols } = await import("./lib/pidGraphml");
    const { PID_DRAWINGS, loadPidGraphml } = await import("./features/pid/pidCorpus");
    for (const drawing of PID_DRAWINGS) {
      const graph = parsePidGraphml(await loadPidGraphml(drawing));
      expect(graph.nodes.length, drawing.tag).toBe(drawing.nodeCount);
      expect(graph.edges.length, drawing.tag).toBe(drawing.edgeCount);
      // Every node must carry a real bounding box from the drawing.
      expect(graph.nodes.every((node) => node.xmax >= node.xmin && node.ymax >= node.ymin)).toBe(true);
      expect(graph.bounds.maxX).toBeGreaterThan(graph.bounds.minX);
      // Edges must only reference nodes that exist.
      const ids = new Set(graph.nodes.map((node) => node.id));
      expect(graph.edges.every((edge) => ids.has(edge.source) && ids.has(edge.target))).toBe(true);
      // Equipment-only export stays a strict subset and is valid JSON.
      const symbols = processSymbols(graph);
      expect(symbols.length).toBeGreaterThan(0);
      expect(symbols.length).toBeLessThan(graph.nodes.length);
      expect(() => JSON.parse(pidSymbolsJson(graph, drawing))).not.toThrow();
    }
  });
});

describe("workspace screens render", () => {
  it("Home shows the composer and quick start", () => {
    const html = mount(createElement(HomeView, { outcomeInputRef: { current: null } }));
    expect(html).toContain("What do you need?");
    expect(html).toContain("--route:");
    expect(html).toContain("Quick start");
  });

  it("P&ID lists all five drawings", () => {
    const html = mount(createElement(PidView));
    for (const tag of ["PID-101", "PID-102", "PID-103", "PID-104", "PID-105"]) {
      expect(html).toContain(tag);
    }
  });

  it("Chat renders an empty conversation", () => {
    expect(mount(createElement(ChatView))).toContain("No messages yet");
  });

  it("Knowledge shows the indexed library", () => {
    const html = mount(createElement(KnowledgeView));
    expect(html).toContain("SOP-MNT-022");
    expect(html).toContain("Indexed passages");
  });

  it("Sandbox renders the terminal", () => {
    expect(mount(createElement(SandboxView))).toContain("Run");
  });

  it("Review is empty, then lists a recorded deliverable", () => {
    expect(mount(createElement(ReviewView))).toContain("Nothing generated yet");
    recordDeliverable({ title: "Smoke deliverable", kind: "markdown", source: "Test", content: "# hi", fileName: "smoke.md" });
    expect(mount(createElement(ReviewView))).toContain("Smoke deliverable");
  });

  it("no screen mentions the model vendor", () => {
    const screens = [
      mount(createElement(HomeView, { outcomeInputRef: { current: null } })),
      mount(createElement(PidView)),
      mount(createElement(ChatView)),
      mount(createElement(KnowledgeView)),
      mount(createElement(SandboxView)),
    ].join(" ");
    expect(screens.toLowerCase()).not.toContain("gemini");
  });
});
