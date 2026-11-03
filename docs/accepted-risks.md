# Accepted risks

Decisions by Martin on 2026-11-03 for the bedroom pre-warm v1.3.0 work (goal bedroom-prewarm-v130). Reviewers must not re-raise these.

- Stalled service call or forecast fetch: bedroom_precool.yaml runs with mode: restart on a one-minute trigger. A stalled climate call or forecast fetch before the fan step can delay the fan safety cut or the wake shutdown. This is the existing v1.2.1 pattern and cannot be tested without an HA runtime. Accepted.
- Off-season heat correction pauses on recovery: outside the heating season a unit reporting heat is corrected to cool only while a bedroom is overheated or all bedroom sensors have failed. If the room or sensors recover while the unit still reports heat, no command is sent until the warmest room is over the threshold again. A person's manual heat in the off season is left alone by design. Accepted; a stateless blueprint cannot do better without a new helper.
