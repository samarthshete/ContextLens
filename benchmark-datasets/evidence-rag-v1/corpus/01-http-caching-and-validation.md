# HTTP caching and validation

HTTP caches—browser caches, CDNs, and reverse proxies—reduce latency and origin load by storing responses keyed by URL and selected request headers. A **shared cache** must respect `Cache-Control` directives from the origin. When responses include **validators**, intermediaries can avoid serving stale representations indefinitely.

Caches should **revalidate the cached entry with the origin when a validator such as ETag or Last-Modified is present** and the freshness model expires or a client sends `no-cache`. Conditional requests (`If-None-Match`, `If-Modified-Since`) let the origin return `304 Not Modified` when the representation is unchanged, saving bandwidth while confirming correctness.

Misconfigured caching for personalized or authenticated content can leak data across users; `Vary` and `private` directives exist to narrow cacheability. For API responses, explicit `Cache-Control` policies are preferable to implicit browser heuristics.
