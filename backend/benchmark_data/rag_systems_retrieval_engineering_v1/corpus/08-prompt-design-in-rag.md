# Prompt Design in RAG

Prompt design plays a critical role in RAG performance. Clear instructions help the model ground answers in retrieved passages and refuse when context is insufficient.

Poor prompts can lead to hallucination or incomplete answers. Including too much context may approach or exceed context limits; too little context starves the model of evidence.

Because the model may misinterpret the context or generate unsupported content despite correct retrieval.

Effective prompts balance instruction clarity, citation or quoting requirements, and the amount of retrieved text passed to the model.
