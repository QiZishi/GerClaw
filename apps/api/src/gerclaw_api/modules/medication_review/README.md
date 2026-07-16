# Medication review intake

This module defines only the server-owned, non-clinical information collection contract for the future medication-review workflow. Values are stored through the encrypted clinical-intake service. No DDI, Beers, dose, duplicate-drug, or clinical recommendation logic exists here.

The current contract deliberately does not accept uploaded documents. Five prescription intake has a distinct, owner/session-scoped MinerU document input path; reusing it for medication review would silently expand the evidence boundary before medical rules, patient authorization, and physician approval exist.
