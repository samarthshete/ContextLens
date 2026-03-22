# gRPC versus REST for internal APIs

REST over JSON is ubiquitous, debuggable with curl, and easy to cache at HTTP layers. **gRPC** uses Protocol Buffers and typically runs over HTTP/2. For high-volume internal calls, **binary framing and HTTP/2 multiplexing can reduce per-call overhead** compared to repetitive JSON parsing and connection churn.

Tradeoffs: gRPC requires codegen and tooling alignment; browser support historically needed gateways. REST remains strong for public APIs and human inspection. Hybrid architectures often expose REST at the edge and gRPC inside the mesh.
