"""Run status values for the trace pipeline.

Statuses are stored in ``runs.status``. Only latencies measured during real execution
should be written to ``*_latency_ms`` columns.
"""

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_RETRIEVAL_COMPLETED = "retrieval_completed"
STATUS_GENERATION_COMPLETED = "generation_completed"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
