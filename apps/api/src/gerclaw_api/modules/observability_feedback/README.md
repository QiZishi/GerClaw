# Observability feedback

`BadCaseSummary` is the operational feedback projection for the administrator
console. It receives only database-grouped source, severity, status and count
metadata, and returns queue totals such as open, high-priority and
negative-feedback counts.

`BadCaseTrend` adds a fixed seven-day series. PostgreSQL groups only calendar
day, source and count; missing days are emitted as zero. The administrator UI
therefore receives neither case IDs nor trace, feedback, snapshot or account
data when rendering the trend.

It never decrypts or exposes Bad Case snapshots, feedback text, image input,
trace input, document content or account identifiers. It does not replay real
cases or automatically promote them into Eval data.
