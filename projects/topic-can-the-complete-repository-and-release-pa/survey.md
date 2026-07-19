# Literature survey: Publishing a complete repository and release payload with cryptographic identifiers and file-level checksums

Research-artifact packaging literature establishes that reproducibility requires more than making a source repository publicly accessible. RO-Crate treats an artifact as a structured aggregation of the items contributing to a research outcome, together with machine-readable identifiers, provenance, relationships, and annotations [1]. This model can represent heterogeneous materials such as source code, data, documentation, and figures, including relationships such as a script consuming a CSV file or a workflow producing a figure. Research compendia pursue a similar goal by packaging a paper’s figures, data, and software so that readers can inspect and reproduce the work systematically [9]. These approaches support including the proposed source, schema, lock file, Makefile, README, outputs, raw results, logs, mutation specifications, and figure in one documented release. However, neither retrieved source establishes that a plain full-file inventory or a SHA-256 checksum table is a standard or sufficient implementation.

Archival and exact identification are distinct but complementary requirements. Di Cosmo separates software preservation into archival, reference, description, and citation, emphasizing that a reproducibility claim must identify the precise code used rather than merely link to a changing repository [2]. Software Heritage addresses archival and reference by preserving source and development history and assigning intrinsic persistent identifiers at multiple granularities [2]. Its archive represents files, directories, and commits in a Merkle directed acyclic graph, permitting content-sensitive identification independently of version-control or package format [5]. Archived artifacts can subsequently be accessed as files, trees, releases, branches, or commits through SwhFS, even if the original hosting location disappears [6]. A recorded commit identifier is therefore important, but a commit alone does not necessarily identify non-versioned release contents, generated outputs, raw results, or logs. A digest of the distributed archive and checksums for every included file would address that separate release-integrity boundary, although the supplied literature does not directly evaluate SHA-256 tables.

Provenance work further indicates that integrity metadata should be accompanied by an account of how the payload was produced. Releasy captures release provenance to support visualization and queries about software evolution, implemented features, and participating developers [3]. Workflow Run RO-Crate similarly records computational executions at multiple levels of granularity and bundles associated inputs, outputs, and code [4]. These methods suggest that the inventory should distinguish authored inputs from generated results and connect raw results, logs, and figures to the workflow or command that produced them. Docker-based artifact preparation adds environment capture, comprehensive documentation, data, and code as practical requirements for reproducible empirical-computing artifacts [7]. Lock files and dependency declarations are especially relevant because reproducibility can fail when package versions differ across systems; the `require` tool illustrates explicit checking of exact or minimum dependency versions and release dates [8].

The literature therefore converges on several evaluation dimensions: completeness of the aggregation, exact version identification, durable archival, machine-readable metadata, dependency specification, and provenance linking inputs to outputs [1]–[8]. It offers complementary methods rather than a direct disagreement: RO-Crate emphasizes description and aggregation, Software Heritage emphasizes preservation and intrinsic source identifiers, provenance systems emphasize release or execution history, and container-oriented methods emphasize runnable environments. The practical need remains significant: a mapping of software-engineering secondary studies found that only 31.5% included research artifacts, and only 30.4% used a permanent repository with a DOI [10]. Yet the retrieved work provides no standard metric for verifying that a repository snapshot and downloadable release payload are mutually identical and internally complete.

## Gap

The untested question is whether one release can provide a verifiable chain from a named commit to the exact distributed archive and every expected artifact file. A new experiment should test whether the repository and release payload can be published together with: (1) a commit identifier and durable archival reference; (2) a cryptographic digest of the archive as downloaded; (3) a complete, machine-readable inventory; and (4) a SHA-256 table covering source, schema, lock file, Makefile, README, outputs, raw results, logs, mutation specifications, and figure. Verification should check inventory coverage, checksum agreement after independent download, correspondence between committed files and release contents, explicit treatment of generated or excluded files, and provenance from inputs and commands to outputs. The supplied literature motivates these checks but does not report an empirical evaluation of this combined publication pattern.

## References

[1] Stian Soiland-Reyes, Peter Sefton, Mercè Crosas, Leyla Jael Castro et al. (2021). Packaging research artefacts with RO-Crate. http://arxiv.org/abs/2108.06503v2

[2] Roberto Di Cosmo (2020). Archiving and referencing source code with Software Heritage. http://arxiv.org/abs/2004.00514v1

[3] Felipe Curty, Troy Kohwalter, Vanessa Braganholo, Leonardo Murta (2018). An Infrastructure for Software Release Analysis through Provenance Graphs. http://arxiv.org/abs/1809.10265v1

[4] Simone Leo, Michael R. Crusoe, Laura Rodríguez-Navas, Raül Sirvent et al. (2023). Recording provenance of workflow runs with RO-Crate. http://arxiv.org/abs/2312.07852v2

[5] Roberto Di Cosmo, Stefano Zacchiroli (2023). The Software Heritage Open Science Ecosystem. http://arxiv.org/abs/2310.10295v1

[6] Thibault Allançon, Antoine Pietri, Stefano Zacchiroli (2021). The Software Heritage Filesystem (SwhFS): Integrating Source Code Archival with Development. http://arxiv.org/abs/2102.06390v1

[7] Michael Canesche, Roland Leissa, Fernando Magno Quintão Pereira (2023). Preparing Reproducible Scientific Artifacts using Docker. http://arxiv.org/abs/2308.14122v1

[8] Sergio Correia, Matthew P. Seay (2023). require: Package dependencies for reproducible research. http://arxiv.org/abs/2309.11058v2

[9] Daniel Nüst, Carl Boettiger, Ben Marwick (2018). How to Read a Research Compendium. http://arxiv.org/abs/1806.09525v1

[10] Aleksi Huotala, Miikka Kuutila, Mika Mäntylä (2025). Research Artifacts in Secondary Studies: A Systematic Mapping in Software Engineering. http://arxiv.org/abs/2504.12646v3
