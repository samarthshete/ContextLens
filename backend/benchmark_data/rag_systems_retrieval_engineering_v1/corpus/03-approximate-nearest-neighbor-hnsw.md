# Approximate Nearest Neighbor (HNSW)

Hierarchical Navigable Small World (HNSW) is a graph-based approximate nearest-neighbor algorithm. It organizes vectors in multiple layers to support efficient greedy search from coarse to fine levels.

HNSW significantly improves search latency compared to naive linear scans while maintaining high recall in practice. It does not guarantee that every query returns the mathematically exact top-k neighbors.

HNSW improves speed and latency but sacrifices exact accuracy, while brute-force guarantees exact results but is computationally expensive.

Tuning parameters such as graph connectivity affects recall, memory footprint, and indexing time.
