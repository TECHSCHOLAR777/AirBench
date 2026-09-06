# AirBench

AirBench is a sovereign AI workbench for sensitive industrial and government knowledge work. It runs inside the organization's network, uses local model serving, executes bounded tools, produces real deliverables, and records an auditable trace.

## Coding-agent entrypoint

Coding agents must read [AGENTS.md](AGENTS.md) before doing any work. It is the central guide for:

- the required architecture-document reading order;
- the M1-M10 GitHub issue workflow;
- the repository-owned skills in `.agents/skills/`;
- Python development, testing, review, and handoff;
- AirBench security and architecture invariants.

Start with `airbench-start-task`. It redirects the agent to the relevant skills and documents before implementation. The architecture map remains in [docs/README.md](docs/README.md). For M5 model serving, registry, and hardware scheduling setup, see [M5_SETUP_AND_PROGRESS.md](M5_SETUP_AND_PROGRESS.md).
