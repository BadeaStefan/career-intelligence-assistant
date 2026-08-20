# Career Intelligence Dashboard — Visual Direction

The production frontend follows the approved reference in
`docs/design_handoff_career_intelligence/`. It is an analytical workspace for candidates comparing
one resume against several roles. Its single job is to make every fit verdict inspectable down to
the cited resume span.

## System

- **Typography:** IBM Plex Sans for readable analysis copy; IBM Plex Mono for provenance, scores,
  status, and system metadata.
- **Palette:** near-neutral OKLCH surfaces and hairline rules. Green, amber, and red are reserved for
  strong, partial, and missing verdicts respectively; progress remains neutral.
- **Layout:** a 46px global bar above a fixed 240px document rail, fluid analysis canvas, and fixed
  360px chat dock. Center analysis and chat transcripts own their scrolling regions.
- **Signature:** the segmented requirement strip is the primary at-a-glance graphic. It exposes the
  verdict distribution without turning the dashboard into a decorative chart.
- **Shape and motion:** square controls, citations, and status badges maintain the instrument-like
  character. The interface does not use decorative animation; reduced-motion preferences are
  respected.

## Runtime integrity

The current runtime reads documents from the real documents API. Until the remaining backend
routes land, analysis, chat, interview preparation, and trace surfaces say precisely that their
service is unavailable. Handoff sample analysis is used only by component tests and is never
imported by production code or exposed through a fixture-mode URL.

## Responsive adaptation

Desktop fidelity is authoritative at 1440px. Below 1080px the rail and chat dock narrow, secondary
legend copy is removed, and the workspace permits overflow rather than collapsing the three-pane
information hierarchy into ambiguous stacked cards.
