# Vector Databases Overview

Vector databases store high-dimensional embeddings and enable similarity search. Unlike traditional relational databases, they are optimized for nearest-neighbor queries using distance metrics such as cosine similarity or Euclidean distance.

A key advantage of vector databases is their ability to retrieve semantically similar content even when the query does not match exact keywords. This makes them a natural fit for semantic search, recommendation systems, and retrieval-augmented generation (RAG).

Vector search introduces trade-offs between speed and accuracy. Exact nearest-neighbor search can guarantee correctness for a given metric but is computationally expensive at scale. Approximate methods improve latency and throughput but may return slightly suboptimal neighbors compared to an exhaustive scan.
