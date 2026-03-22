# RAG Architecture

Retrieval-Augmented Generation (RAG) combines document retrieval with language model generation. The system retrieves relevant chunks from an index and conditions the model on that context to produce an answer.

RAG systems can fail when retrieval is incomplete, when chunks are poorly aligned with the question, or when the model misuses the provided context. Even when retrieval returns plausible documents, the final answer may still be incomplete or unsupported.

Because the model may omit information, misinterpret context, or relevant information may be split across chunks.

Effective RAG design balances retriever quality, chunking, prompt structure, and model choice.
