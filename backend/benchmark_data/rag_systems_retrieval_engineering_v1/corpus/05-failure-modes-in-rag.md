# Failure Modes in RAG

RAG systems exhibit several interacting failure modes at retrieval, context assembly, and generation stages.

Retrieval miss occurs when relevant documents or chunks are not retrieved. Retrieval partial happens when only part of the required information is retrieved.

When the input exceeds the model's token limit, causing some retrieved content to be dropped.

Chunk fragmentation happens when relevant information is split across multiple chunks such that no single retrieved passage contains a complete answer.

Generation failures include hallucination, unsupported answers, and incomplete responses. These failures can occur even when retrieval surfaces correct source documents.

Retrieval miss, retrieval partial, context truncation, chunk fragmentation, hallucination, and incomplete answers.
