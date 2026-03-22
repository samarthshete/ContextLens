# PostgreSQL WAL and checkpoints

PostgreSQL uses a **write-ahead log (WAL)** so committed transactions survive process crashes. Changes are appended to WAL segments before dirty data pages are flushed to heap files. On restart, the system achieves **durability across crashes by replaying committed records from the log** up to the last consistent checkpoint.

**Checkpoints** bound recovery time by forcing dirty pages to disk and advancing the redo horizon. Frequent checkpoints reduce crash-recovery work but increase I/O; rare checkpoints lengthen recovery. Autovacuum and background writer interact with this schedule. Operators tune `checkpoint_timeout` and `max_wal_size` to balance steady-state write amplification against worst-case startup time.
