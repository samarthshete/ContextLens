# Evaluation of RAG Systems

Evaluating RAG systems involves measuring both retrieval quality and generation quality. Teams often track relevance of retrieved passages, overlap with ground truth, and downstream answer quality.

Faithfulness measures whether the answer is supported by evidence, while completeness measures whether the answer fully covers the query.

Evaluation can be heuristic (rule- or embedding-based, faster, cheaper) or model-based (e.g., LLM-as-judge, deeper signal, higher cost and variance).

Consistent definitions for faithfulness and completeness help compare configs and regressions over time.
