# TLS handshake overview

Transport Layer Security establishes a secure channel over TCP. The handshake authenticates the server (and optionally the client), agrees on algorithms, and derives keys. Early messages advertise supported protocol versions and extensions; the server selects parameters and sends its certificate chain.

Cipher suite negotiation and key exchange establish shared session keys before application data is encrypted. Modern stacks prefer ephemeral Diffie-Hellman for forward secrecy. After the handshake, records use authenticated encryption; reordering and tampering are detected. Session resumption (tickets or session IDs) reduces full handshakes for repeat connections.
