# Formal evidence marker audit

The audit found two stale records where `formal_success_marker` is `true` only because an empty marker dictionary makes Python `all(...)` vacuously true. Both records have `returncode=null`, `timed_out=true`, and no proof markers:

- `SmallControl.Family / RegCache`
- `StoreQueueData / SQDataModule`

The records are already `STRICT_PENDING` and were not counted as strict passes. The shared rail was left unchanged because its digest is locked into existing evidence. A future coordinated producer migration must require a nonempty marker set, a successful return code, and a complete proof summary, then rerun every affected family before updating canonical evidence.
