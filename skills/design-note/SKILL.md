---
name: design-note
description: Write a structured design note for a feature or change BEFORE building it — problem, the core reframe/insight, the design with options and tradeoffs, edge cases, and the open questions to decide at build time. Use when scoping a feature, weighing approaches, or capturing a design decision so it can be built (or resumed) later. Produces a <feature>-DESIGN.md.
---

# /design-note

Capture a design as a structured note **before** building, so the thinking is
explicit and a future session — or another person — can build it cold. Produces
a `<feature>-DESIGN.md` in the repo.

## Gather (ask only what you can't infer)
- What's being designed, and why now.
- The constraints that actually matter (existing system, scale, who uses it).

Don't interrogate — pull what you can from the codebase, ask only the gaps.

## The note's structure — use these sections, in order

Open with a title and a status line:
`# <Feature> — design note` then `**Status:** DESIGN, not built. <date>`

1. **Problem / motivation** — what's broken or missing, and why it's worth
   solving. Concrete, not abstract.
2. **Core reframe** — the one insight that makes the right design obvious (often
   "it's actually X, not Y"). If you can't name one yet, that's a signal to think
   more before building.
3. **The design — options with tradeoffs** — the real candidates, each with its
   tradeoff. Recommend one and say *why*. Never present a single path as if no
   alternative existed.
4. **Edge cases** — the cases that break a naive version, named so they're handled
   on purpose.
5. **Open questions (decide at build time)** — what you're deliberately *not*
   deciding yet, listed so it isn't forgotten.
6. **Rollout / cost** *(only if it touches a deployed or outward-facing surface)* —
   what shipping it costs or risks, and what must be confirmed before deploy.

## Principles
- **Options with tradeoffs, not one path.** A note presenting one option hasn't
  done the work.
- **Name the reframe.** The best designs hinge on a single insight — surface it.
- **Honest about what's undecided.** Open questions are a feature, not a gap.
- **Don't pad.** A short note that names the reframe and the key tradeoff beats a
  long one that lists everything.
