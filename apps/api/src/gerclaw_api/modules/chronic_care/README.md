# Chronic Care

`chronic_care` is a real backend ledger for a user to record a self-reported
condition and timestamped measurements. The data is encrypted and bounded to
the authenticated tenant and actor. It can show the arithmetic direction
between the last two values of the same user-entered metric label.

The patient MVP exposes this ledger at **我的慢病记录** through the controlled
`/api/gerclaw` BFF: a user can create a self-reported label and append a
measurement, then read the owned ledger and arithmetic comparison. The UI
labels every condition as self-reported and never renders a clinical range,
target, diagnosis or treatment recommendation.

This is deliberately not a chronic-disease management conclusion. It has no
clinical thresholds, targets, alerts, medication assessment, reminder,
adherence inference, treatment suggestion, doctor queue or patient
authorisation workflow. Those capabilities require versioned medical evidence,
review and RBAC/HITL before they can consume this ledger.
