# Observability feedback

`BadCaseSummary` is the operational feedback projection for the administrator
console. It receives only database-grouped source, severity, status and count
metadata, and returns queue totals such as open, high-priority and
negative-feedback counts.

It never decrypts or exposes Bad Case snapshots, feedback text, image input,
trace input, document content or account identifiers. It does not replay real
cases or automatically promote them into Eval data.
