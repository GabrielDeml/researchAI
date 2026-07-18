# Literature survey: Genetic algorithms

Genetic algorithms (GAs) are population-based optimization methods that represent candidate solutions as genotypes and iteratively apply selection, crossover, mutation, and replacement. Fitness is typically a monotonic function of the optimization objective, with proportional, truncation, and tournament selection among the common alternatives [1]. Their appeal lies in the generality of this framework: adapting a GA to a problem primarily requires defining the representation, fitness function, and variation operators. Theoretical treatments include the Schemata Theorem, crossover properties, interpretations of GA behavior as local search, and almost-sure convergence under sufficiently general assumptions and unlimited runtime [1]. However, asymptotic convergence does not establish practical efficiency, making evaluation budgets, solution quality, and premature convergence central experimental concerns.

Algorithmic variants differ substantially in how they replace individuals and preserve elite solutions. Jenkins et al. compare generational, steady-state, steady-generational, and \((\mu+\mu)\) GAs on the Schaffer F6 function [2]. A generational GA replaces the entire parent population, whereas steady-state schemes introduce one or a few offspring at a time. The \((\mu+\mu)\) strategy selects the best individuals from the combined parent and offspring populations, explicitly preserving high-fitness candidates. The study also compares single-point, midpoint, and blend crossover under binary tournament selection, using the number of function evaluations over 30 runs as its main efficiency measure [2]. This illustrates a useful experimental principle: variants should be compared under a common evaluation budget rather than solely by generations, because replacement schemes evaluate different numbers of offspring per cycle.

Prior work also modifies GAs to control the exploration–exploitation tradeoff. Fuzzy genetic algorithms dynamically adjust standard GA control parameters using the best individual’s fitness and population-diversity measurements, with reported advantages over a standard GA in test-function and antenna-array optimization [7]. Social-interaction models instead perturb fitness through game-theoretic interactions among cooperators and defectors, motivated by the possibility that such perturbations delay convergence and help populations escape local optima [3]. Hybrid optimization combines GA exploration with an exploitation-oriented exchange-market algorithm, addressing the GA’s potentially high execution time [5]. Surrogate assistance offers another route to efficiency: an approximate fitness model learned from evaluated items can guide an interactive GA while reducing reliance on direct user evaluation, although benchmarking requires comparison against conventional GA and random-search baselines [10].

The applications represented here demonstrate breadth but do not provide a unified account of when GAs are preferable. They include CNN hyperparameter search on CIFAR-10 [6], digital logic synthesis from NAND gates [9], antenna-array design [7], and SU(2) lattice gauge simulation [8]. Evaluation is correspondingly domain-dependent: function evaluations and repeated-run statistics are appropriate for benchmark optimization [2], while scientific simulation may require agreement with established methods on observables such as action per plaquette and Wilson loops [8]. Across domains, experiments should therefore report objective quality, evaluation or runtime cost, variability across independent runs, convergence behavior, and population diversity where premature convergence is relevant.

## Gap

The retrieved literature is broad but thin on controlled, cross-method evidence. A useful new experiment would isolate how replacement strategy and adaptive diversity control interact under a fixed function-evaluation budget. Specifically, generational, steady-state, steady-generational, and \((\mu+\mu)\) GAs could be tested both with fixed parameters and with diversity-driven parameter adaptation. Repeated runs should compare final objective value, evaluations needed to reach a target, success rate, and diversity over time. This would test whether adaptive control provides consistent benefits across replacement schemes rather than only within a single application.

## References

[1] Anton V. Eremeev (2015). Evolutionary algorithms. http://arxiv.org/abs/1511.06987v5

[2] Alison Jenkins, Vinika Gupta, Alexis Myrick, Mary Lenoir (2019). Variations of Genetic Algorithms. http://arxiv.org/abs/1911.00490v1

[3] Rafeal Lahoz-Beltra, Gabriela Ochoa, Uwe Aickelin (2010). Cheating for Problem Solving: A Genetic Algorithm with Social Interactions. http://arxiv.org/abs/1001.1889v1

[5] A. Jafari, T. Khalili, E. Babaei, A. Bidram (2020). A Hybrid Optimization Technique Using Exchange Market and Genetic Algorithms. https://www.semanticscholar.org/paper/4a4663505ebab050d3b50d4b933a21efbbba7022

[6] Nurshazlyn M. Aszemi, P. Dominic (2019). Hyperparameter Optimization in Convolutional Neural Network using Genetic Algorithms. https://www.semanticscholar.org/paper/c02f877d81f487106cbd437f3f8d46b1496a897f

[7] Boufeldja Kadri, Miloud Boussahla, Fethi Tarik Bendimerad (2010). Phase-Only Planar Antenna Array Synthesis with Fuzzy Genetic Algorithms. http://arxiv.org/abs/1002.1176v1

[8] A. Yamaguchi (1998). Genetic Algorithm for SU(2) Gauge Theory on a 2-dimensional Lattice. http://arxiv.org/abs/hep-lat/9809068v1

[9] Christopher M. Frenz, Steve Peters, Wilson Julien (2009). Evolution of Digital Logic Functionality via a Genetic Algorithm. http://arxiv.org/abs/0907.4426v1

[10] Thomas Gabor, Philipp Altmann (2019). Benchmarking Surrogate-Assisted Genetic Recommender Systems. http://arxiv.org/abs/1908.02880v1
