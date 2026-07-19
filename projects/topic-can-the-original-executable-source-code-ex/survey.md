# Literature survey: Can the original executable source code, exact dependency versions, environment specification, and timestamped machine-readable outputs be archived under a persistent identifier?

Prior work supports archiving each major component of a computational experiment, but it does not yet demonstrate that all components can be preserved and referenced as one enduring, independently verifiable object. Software Heritage provides the strongest basis for preserving original source code. It archives publicly available source code and development history in a uniform Merkle directed acyclic graph, assigning intrinsic persistent identifiers at several granularities, including files, directories, commits, and releases [2]. These identifiers are content-derived rather than tied to a repository location, so they remain meaningful if the original hosting service disappears. The archive has broad coverage across public software-development projects [5], while SwhFS demonstrates that archived artifacts can be accessed through a POSIX filesystem and used with ordinary development tools [6]. Together, these works establish practical mechanisms for preserving and precisely referencing source code, although their scope is principally public source rather than private code, generated executables, or complete experimental bundles.

Exact software environments require more than a list of package names and nominal versions. Courtès et al. explain that GNU Guix captures the complete graph of package definitions, including source locations and cryptographic hashes, build configuration, and recursive dependencies [1]. The `guix time-machine` mechanism can use this specification to redeploy the same environment, potentially bit for bit, on another machine or at a later time [1]. Connecting Guix to Software Heritage addresses a critical failure mode: an environment specification is insufficient if any dependency source has disappeared. The study evaluates package-source archival coverage using observations collected over five years, providing a relevant archival metric [1]. This approach is stronger than conventional dependency manifests, whose maintenance choices can introduce incompatibilities, unnecessary installations, or reduced understandability [9]. However, the Guix work explicitly assumes free and open-source software, and source availability remains a necessary rather than sufficient condition for successful future execution.

RO-Crate supplies a complementary method for packaging heterogeneous research artifacts and describing their relationships. It represents data, software, methods, identifiers, provenance, and annotations using machine-readable Schema.org metadata in JSON-LD [3]. Workflow Run RO-Crate extends this model to describe computational executions at multiple levels of granularity and to bundle workflow plans, inputs, outputs, code, and run provenance [4]. It is therefore the closest prior work to the requested archival unit: a crate could relate a Software Heritage identifier for exact code, an environment specification, and timestamped machine-readable outputs. Research compendia similarly motivate packaging papers, software, and data together, though the literature characterizes this as an emerging practice rather than a fully standardized preservation solution [10]. Importantly, RO-Crate provides a packaging and metadata model; the retrieved material does not itself establish long-term storage or guarantee that an entire crate receives a persistent identifier.

Evaluation should distinguish archival completeness from computational reproducibility. Appropriate checks suggested by this literature include resolving source identifiers, verifying cryptographic hashes, measuring dependency-source archival coverage, reconstructing the environment, rerunning the computation, and comparing archived with regenerated outputs. Exact byte equality is the strongest output criterion, but it may be inappropriate for nondeterministic or environment-sensitive computations. Work on Jupyter notebooks identifies randomness, library changes, and environmental variation as causes of divergent reruns and proposes output-type-specific similarity scores between zero and one [8]. Thus, timestamped original outputs should be retained as evidence even when future reruns can only be assessed by semantic or similarity-based comparison.

## Gap

The specific untested question is whether a single deposited research object can bind together content-identified original source code, the complete transitive dependency graph, an executable environment specification, and timestamped machine-readable outputs under one persistent identifier—and whether every referenced component remains resolvable and sufficient for reconstruction over time. Existing work establishes most component technologies, but the supplied sources do not report an end-to-end experiment testing identifier persistence, archival completeness, environment reconstruction, and output agreement for such a unified object.

## References

[1] Ludovic Courtès, Timothy Sample, Simon Tournier, Stefano Zacchiroli (2024). Source Code Archiving to the Rescue of Reproducible Deployment. http://arxiv.org/abs/2405.15516v1

[2] Roberto Di Cosmo (2020). Archiving and referencing source code with Software Heritage. http://arxiv.org/abs/2004.00514v1

[3] Stian Soiland-Reyes, Peter Sefton, Mercè Crosas, Leyla Jael Castro et al. (2021). Packaging research artefacts with RO-Crate. http://arxiv.org/abs/2108.06503v2

[4] Simone Leo, Michael R. Crusoe, Laura Rodríguez-Navas, Raül Sirvent et al. (2023). Recording provenance of workflow runs with RO-Crate. http://arxiv.org/abs/2312.07852v2

[5] Roberto Di Cosmo, Stefano Zacchiroli (2023). The Software Heritage Open Science Ecosystem. http://arxiv.org/abs/2310.10295v1

[6] Thibault Allançon, Antoine Pietri, Stefano Zacchiroli (2021). The Software Heritage Filesystem (SwhFS): Integrating Source Code Archival with Development. http://arxiv.org/abs/2102.06390v1

[8] A S M Shahadat Hossain, Colin Brown, David Koop, Tanu Malik (2025). Similarity-Based Assessment of Computational Reproducibility in Jupyter Notebooks. http://arxiv.org/abs/2509.23645v1

[9] Abbas Javan Jafari, Diego Elias Costa, Rabe Abdalkareem, Emad Shihab et al. (2020). Dependency Smells in JavaScript Projects. http://arxiv.org/abs/2010.14573v2

[10] Daniel Nüst, Carl Boettiger, Ben Marwick (2018). How to Read a Research Compendium. http://arxiv.org/abs/1806.09525v1
