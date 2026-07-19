# Literature survey: Can a complete artifact package be released containing executable source code, the four CSV files, the heatmap source matrix, a schema-versioned manifest, an environment lock file, and a documented one-command reproduction procedure?

Prior work strongly supports releasing research artifacts as integrated packages of code, data, documentation, and execution environments. Canesche, Leissa, and Pereira define reproducible artifacts as comprehensive documentation, data, and code that permit independent replication and validation [1]. Their Docker-based methodology treats an artifact as a collection of scripts, tools, libraries, and data capable of regenerating published tables and figures. Research compendia follow the same general model: they package the paper’s data and software alongside its textual and visual results [7]. Krijthe and Loog further show that executable code can support not only reproduction of reported analyses but also alternative analyses, making the artifact useful for validation and extension [2]. These sources therefore support including executable source, the four CSV files, and the heatmap’s underlying matrix rather than releasing only rendered results.

Environment capture is a separate requirement from preserving source and data. Docker bundles software with its execution dependencies and is presented as a practical way to simplify artifact construction and evaluation [1]. Guix addresses the related problem that software may be upgraded, removed, or rebuilt over time, preventing later reproduction even on the original HPC system; its functional package-management approach is intended to make environments reproducible and shareable [4]. Lockfiles offer a lighter-weight mechanism by recording resolved direct and indirect dependency versions, supporting reproducibility across environments and time [3]. However, lockfile designs differ substantially among package managers and can be difficult to maintain or interpret [3]. Where supported, integrity metadata is also valuable: Maven-Lockfile captures transitive dependencies and checksums and was evaluated for rebuilding historical revisions and detecting altered artifacts [8]. Thus, an environment lock file is well motivated, but it should identify its package manager and platform assumptions; it may complement rather than replace a container or other environment specification.

The proposed schema-versioned manifest would provide a machine-readable inventory and contract connecting files to their roles, although the retrieved literature offers only indirect precedent for this exact mechanism. Nüst, Boettiger, and Marwick emphasize conventions and shared structure as aids to navigating research compendia [7]. Kasselman’s executable proof similarly links implementations to an output contract, implementation graph, traceability file, readiness gate, and evidence matrix [10]. Together, these works suggest that explicit declarations of expected inputs, outputs, and evidence improve inspectability. Nevertheless, none of the supplied sources evaluates manifest schema versioning specifically, so its benefits should be treated as a design hypothesis rather than an established standard.

A documented one-command procedure is consistent with the movement from merely available artifacts toward independently executable reproduction. Artisan frames reproduction as generating a script that can be run independently and assessed at a fine-grained level [5]. Evaluation should therefore test the command from a clean environment, verify successful termination, and compare generated files with the released reference outputs. Exact byte-level comparison may be appropriate for deterministic CSV or matrix files, while numerical tolerances or similarity measures may be necessary when randomness, library versions, or environment differences affect outputs. The Similarity-based Reproducibility Index illustrates output-specific similarity scoring on a zero-to-one scale for notebook reruns [9], although it does not establish a universal metric for CSV tables or heatmaps.

## Gap

The retrieved work supports each major principle—shipping code and data, capturing dependencies, documenting execution, and checking outputs—but does not test the proposed package as a whole. The open question is whether one clean checkout can use the locked or containerized environment and a single documented command to regenerate all four CSV files and the heatmap source matrix, with the schema-versioned manifest correctly enumerating inputs, outputs, versions, checksums, and validation rules. A new experiment should evaluate completeness, clean-environment executability, output agreement, and failure diagnostics.

## References

[1] Michael Canesche, Roland Leissa, Fernando Magno Quintão Pereira (2023). Preparing Reproducible Scientific Artifacts using Docker. http://arxiv.org/abs/2308.14122v1

[2] Jesse H. Krijthe, Marco Loog (2016). Reproducible Pattern Recognition Research: The Case of Optimistic SSL. http://arxiv.org/abs/1612.08650v1

[3] Yogya Gamage, Deepika Tiwari, Martin Monperrus, Benoit Baudry (2025). The Design Space of Lockfiles Across Package Managers. http://arxiv.org/abs/2505.04834v3

[4] Ludovic Courtès, Ricardo Wurmus (2015). Reproducible and User-Controlled Software Environments in HPC with Guix. http://arxiv.org/abs/1506.02822v2

[5] Doehyun Baek, Michael Pradel (2026). Artisan: Agentic Artifact Evaluation. http://arxiv.org/abs/2602.10046v1

[7] Daniel Nüst, Carl Boettiger, Ben Marwick (2018). How to Read a Research Compendium. http://arxiv.org/abs/1806.09525v1

[8] Larissa Schmid, Elias Lundell, Yogya Gamage, Benoit Baudry et al. (2025). Maven-Lockfile: High Integrity Rebuild of Past Java Releases. http://arxiv.org/abs/2510.00730v2

[9] A S M Shahadat Hossain, Colin Brown, David Koop, Tanu Malik (2025). Similarity-Based Assessment of Computational Reproducibility in Jupyter Notebooks. http://arxiv.org/abs/2509.23645v1

[10] Werner Kasselman (2026). A Minimal Executable Proof for Multi-Language Contract Traceability. http://arxiv.org/abs/2605.28546v1
