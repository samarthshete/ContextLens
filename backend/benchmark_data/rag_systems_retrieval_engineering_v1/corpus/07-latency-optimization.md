# Latency Optimization

Latency in RAG systems typically comes from retrieval, context assembly, generation, and optional evaluation or reranking stages.

Retrieval latency depends on index structure, dataset size, hardware, and query parameters such as top_k. Generation latency is influenced by model size, decoding strategy, and output length.

By reducing top_k, optimizing retrieval structures, caching, batching, and choosing smaller models.

Caching frequent queries or retrieved contexts and batching requests can amortize overhead. Smaller models reduce per-token cost and often reduce end-to-end latency at the expense of capability.
