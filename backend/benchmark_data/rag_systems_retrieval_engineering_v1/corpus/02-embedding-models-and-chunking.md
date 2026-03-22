# Embedding Models and Chunking

Embedding models convert text into dense numerical vectors. The quality and domain fit of the embedding model significantly impact retrieval performance.

Chunking refers to splitting documents into smaller segments before embedding and indexing. The choice of chunk size and overlap affects what the retriever can surface to the generator.

Small chunks improve precision but risk losing context, while large chunks preserve context but may introduce irrelevant information.

If chunks are too small, the system may retrieve fragments that omit necessary surrounding context. If chunks are too large, retrieved segments may contain noise that dilutes relevance signals.
