# Chronic Care

`chronic_care` is a real backend ledger for a user to record a self-reported
condition and timestamped measurements. The data is encrypted and bounded to
the authenticated tenant and actor. It can show the arithmetic direction
between the last two values of the same user-entered metric label.

This is deliberately not a chronic-disease management conclusion. It has no
clinical thresholds, targets, alerts, medication assessment, reminder,
adherence inference, treatment suggestion, doctor queue or patient
authorisation workflow. Those capabilities require versioned medical evidence,
review and RBAC/HITL before they can consume this ledger.
