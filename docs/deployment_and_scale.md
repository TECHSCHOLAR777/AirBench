# Deployment and Scale

## Purpose

This covers how AirBench is packaged, installed, updated, and run inside an organization that has no internet, on a fixed amount of hardware, and possibly across many sites. It is what makes the system a thing you can actually ship into a plant, a hospital, or a secure office, not just a design.

## Where it sits

The ground the whole system runs on. It hosts every engine, and it is bound by the sovereignty rules, install and update are themselves things that must not open a path out.

This document describes the target deployment shape. The first scope is intentionally narrower: one local node, one measured hardware profile, a small qualified model set, and no fleet-management claim.

## The shape of a deployment

AirBench runs as a set of services in containers on the organization's own machine. The services are the ones named across the other specs: the orchestrator, the model serving tier, the embeddings service, the specialist vision and drawing service, the tool sandbox, and the stores for search, the world model, the state and records, and the audit trail. They are kept as separate services so a fault in one does not take down the rest.

The first scope is a single-node local deployment with a small model set and offline installation assumptions. Full signed-appliance lifecycle, key rotation, rollback, encrypted consistent backups, and multi-site fleet distribution are deferred to `future_full_fledged_must_have.md`.

## Running on a fixed machine

The hardware is fixed and there is no cloud to burst into, so the design treats the machine as a budget to manage, not a pool to grow.

- Models share the machine's memory as a managed pool with hard per model limits, not as fixed hardware slabs, because slabs strand memory for small models and starve the big one. Frequently used models stay resident, rare ones are parked in a fast waking sleep state. This is detailed in `serving_and_routing.md`.
- The system admits work against a live budget of memory and compute, and under pressure it sheds by importance and steps down to a smaller model rather than dropping work, tied to the Autonomy Governor's sense of what matters.
- High availability of the model tier on a single machine is not possible, so the design aims for graceful degradation, not failover. When the machine is saturated, low importance work waits and important work is protected.

## Shipping and updating without internet

Software reaches the organization as one signed bundle that carries everything, the service images, the model weights, the starting knowledge, all together, so the weights and the knowledge travel inside the same chain of custody as the code, which is exactly where a poisoned model would otherwise slip in. Install is a single offline step. Updates arrive the same way, as signed bundles on approved media, staged and verified before they replace what is running, never pulled in the background.

Because there is no internet, the usual online verification of signatures does not work, so the bundle ships with an offline way to verify it against a key the organization holds. The organization can also verify that what is running matches what was shipped, using its own held reference, so it does not have to trust the vendor's word.

## Scaling up and out

The first machine has a hard ceiling, one card with a slow link to any second card, so growth follows a clear order. Within a machine, use the memory pool and sleep state well. Beyond one card, replicate whole models across cards or nodes behind the router, never split a model across cards, because the link between them is too slow. The stateless parts, the agent workers and retrieval, scale out horizontally, while the stores stay as carefully backed single points or small clusters. A single box uses a simple container setup, and a multi node site moves to a proper cluster manager suited to disconnected environments.

## Many sites, one product

For an organization with many sites, a central place qualifies models, packs, and configurations, signs them, and ships them out to each site on approved media. The flow is one way by design: qualified models and settings flow to the sites, and no site data ever flows back, except at most a sanitized health signal over a one way path. The center can never reach into a site, and a site's data can never reach the center. Two sites running the same signed configuration are provably identical without either being reachable, which is how a fleet is managed without breaking each site's isolation.

## Reliability and recovery

The stores cross reference each other, a world model fact points to a document piece points to an audit record, so they must be backed up together at one consistent moment, not separately, or a restore leaves dangling references, which is corruption of the exact trail an auditor inspects. Backups are captured as one signed, restorable unit, and that same unit can restore onto a smaller machine for a remote site running a reduced set of models. Monitoring runs entirely inside the walls, with nothing reporting out.

## Interfaces

Input: a signed appliance bundle and, over time, signed update and pack bundles.

Output: a running, verifiable deployment, and consistent signed backups that can be restored on the same or a smaller machine.

## Failure handling

A bundle that fails verification does not install, and the running system stays on the last good version. A saturated machine degrades gracefully rather than failing. A site that loses contact with the center keeps running fully on its own, because it was never dependent on the center to operate.

## What is core and what is pack

Core: the packaging, the offline install and update, the memory pool and budget, the scaling model, the fleet distribution, the consistent backup and restore.

Pack: which models and configurations a given site runs, delivered as signed bundles.
