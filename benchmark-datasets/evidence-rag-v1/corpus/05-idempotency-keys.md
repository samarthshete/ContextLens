# Idempotency keys in payment and order APIs

Networks retry POST requests; users double-click submit. Without safeguards, retries can create duplicate charges or shipments. Clients send a stable **idempotency key** (often in a header) that the server stores with the outcome of the first successful attempt.

This design prevents **duplicate submissions of the same logical payment intent** when the client or infrastructure retries after timeouts. Keys should be unique per logical operation, not per HTTP attempt. Servers typically expire key records after a bounded window and reject keys reused for different request bodies.
