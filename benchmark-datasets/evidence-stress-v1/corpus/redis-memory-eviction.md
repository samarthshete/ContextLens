# Redis memory limits and eviction

When `maxmemory` is reached, Redis chooses how to free space using the `maxmemory-policy` setting.

## Policies

- **noeviction**: Returns errors on writes when memory is full; reads continue. Safer for strict durability expectations.
- **allkeys-lru**: Evicts least recently used keys from the entire keyspace.
- **volatile-lru**: Evicts LRU keys among those with an expire set only.
- **allkeys-lfu** / **volatile-lfu**: Frequency-based variants of the LRU policies.
- **volatile-ttl**: Evicts keys with shortest TTL first among volatile keys.

## Interaction with replicas

Replicas ignore `maxmemory` by default so they can accept the full stream from the primary. Operators often set replica `maxmemory` and policy explicitly when using partial sync or diskless replication constraints.
