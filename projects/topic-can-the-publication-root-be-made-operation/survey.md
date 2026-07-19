# Literature survey: Can the publication root be made operationally trustworthy?

Publishing an inventory’s Merkle root is not sufficient by itself: a verifier must also authenticate the root, determine which release and inventory definition it represents, and reject stale or equivocated values. The retrieved literature does not directly specify such an end-to-end protocol, but two systems provide relevant authenticated-publication models. TUF distributes signed metadata through multiple signing roles rather than relying on one signature, supports threshold-style configurations with multiple keys per role, and uses root metadata to endorse replacement keys during rollover [1]. Its state-machine treatment also highlights operational costs that matter for root publication: signature count, signature size, client validation effort, and key-rollover frequency [1]. AMP follows a complementary pattern: a publisher signs a provenance manifest, stores it for lookup, and registers it in a permissioned ledger that signs registrations and makes operations auditable [2]. Together, these works suggest that an inventory root should appear inside signed, versioned metadata and may additionally be registered through a transparency or ledger service.

Merkle-tree research establishes what the published root can authenticate once obtained. Merkle structures permit efficient auditing through hash-based authentication paths, while formally verified implementations can reduce the risk that implementation errors invalidate this guarantee [3]. Deterministic structure is especially important: the Cartesian Merkle Tree explicitly combines deterministic construction with membership and non-membership proofs [6]. Dynamic Merkle B-trees target smaller proof sizes and efficient operations by reducing tree height [5], while asynchronous Merkle trees address the cost of rebuilding large trees and the need for parallel processing [4]. These designs differ in update and proof trade-offs, but agree that a root is meaningful only relative to precisely specified tree construction, element ordering, hashing, and proof-validation rules. For a literal inventory, canonical record encoding and deterministic ordering therefore need to be part of the authenticated release specification, not left as implementation details.

Provenance work adds the semantic layer required to interpret a root. AMP binds signed manifests to publishers and media instances, illustrating how authenticated metadata can identify the asserted object and its source [2]. DataHub’s proposed unified querying over versions and provenance indicates that verifiers may need to navigate both release history and derivation relationships [7]. Evaluations of provenance serialization show that representation and query systems affect storage and retrieval efficiency at large scale [8]. Thus, a root-bearing release should identify at least the inventory version, creation time, publisher, hash and signature algorithms, canonicalization rules, tree type, record count or scope, predecessor release, and the location from which proofs or records can be obtained.

A suitable experiment should evaluate the complete verifier path rather than only recomputing a Merkle root. Standard measurements suggested by the prior work include signature and metadata size, number and cost of signature validations [1], authentication-proof size and verification time [5][6], tree construction or update time [4], and lookup or provenance-query performance [8]. Security tests should cover altered manifests, substituted roots, stale releases, invalid membership and non-membership proofs, key rollover, and inconsistent roots presented to different verifiers. Comparing a signed release alone with ledger-registered publication, as exemplified by AMP [2], would isolate the additional value and cost of globally auditable registration.

## Gap

The evidence is thin on the central operational question. None of the retrieved sources defines and experimentally tests a protocol in which a literal inventory root is published, discovered, authenticated, freshness-checked, semantically interpreted, and then used to verify raw records. The open question is whether a concrete verifier procedure—starting from configured trust anchors, retrieving signed release metadata, validating signatures and key rotation, checking version and freshness, optionally confirming ledger inclusion and consistency, and finally recomputing or proving against the root—remains secure and usable under realistic failure and equivocation scenarios. A new experiment should implement this procedure and compare authenticated channels on verification success, equivocation detection, latency, bandwidth, proof cost, and recovery from key rollover or unavailable publication services.

## References

[1] Brian Romansky, Thomas Mazzuchi, Shahram Sarkani (2025). State Machine Model for The Update Framework (TUF). http://arxiv.org/abs/2502.18092v1

[2] Paul England, Henrique S. Malvar, Eric Horvitz, Jack W. Stokes et al. (2020). AMP: Authentication of Media via Provenance. http://arxiv.org/abs/2001.07886v3

[3] Sota Sato, Ryotaro Banno, Jun Furuse, Kohei Suenaga et al. (2021). Verification of a Merkle Patricia Tree Library Using F*. http://arxiv.org/abs/2106.04826v1

[4] Anoushk Kharangate (2023). Asynchronous Merkle Trees. http://arxiv.org/abs/2311.17441v1

[5] Chase Smith, Alex Rusnak (2020). Dynamic Merkle B-tree with Efficient Proofs. http://arxiv.org/abs/2006.01994v3

[6] Artem Chystiakov, Oleh Komendant, Kyrylo Riabov (2025). Cartesian Merkle Tree. http://arxiv.org/abs/2504.10944v1

[7] Amit Chavan, Silu Huang, Amol Deshpande, Aaron Elmore et al. (2015). Towards a unified query language for provenance and versioning. http://arxiv.org/abs/1506.04815v1

[8] Michael A. C. Johnson, Marcus Paradies, Hans-Rainer Klöckner, Albina Muzafarova et al. (2024). Evaluation of Provenance Serialisations for Astronomical Provenance. http://arxiv.org/abs/2407.14290v1
