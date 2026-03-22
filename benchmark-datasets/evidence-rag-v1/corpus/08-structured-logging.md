# Structured logging for operability

Plain text logs are easy to grep once, but aggregating across hosts and services breaks down at scale. **Structured logs** (JSON lines, key-value pairs) attach consistent fields: timestamp, level, service, trace_id, user_id (when safe), and error codes.

Operators filter and aggregate by service, trace_id, or error_code without parsing ad hoc when fields are indexed in the log backend. Sampling and cardinality limits prevent high-cardinality fields (raw URLs with IDs) from exploding index cost. Correlation IDs should propagate across RPC boundaries so a single user request traces through multiple services.
