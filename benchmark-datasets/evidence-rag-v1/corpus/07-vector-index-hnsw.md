# HNSW for approximate nearest neighbor search

Hierarchical Navigable Small World (HNSW) builds a layered graph over vectors. Search starts from a coarse layer and greedily descends toward the query, trading exact recall for speed. Many retrieval systems use HNSW or IVF variants on top of pgvector or dedicated vector databases.

The main tradeoff is that an HNSW graph index makes build-time memory and insertion cost for faster query latency at high recall: large corpora pay upfront graph construction and RAM, while query paths stay short. Tuning `ef_construction` and `M` affects index quality versus build time; `ef_search` trades latency for recall at query time.
