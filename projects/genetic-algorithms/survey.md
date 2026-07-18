# Literature survey: Genetic algorithms

Genetic algorithms (GAs) are stochastic, population-based optimization methods inspired by natural selection and genetic information transfer. Their principal appeal is that they do not require gradient information, making them applicable to nonlinear, discrete, and combinatorial problems [2]. A conventional GA repeatedly selects candidate solutions, applies crossover and mutation, evaluates fitness, and replaces some or all of the population. However, “the GA” is not a single algorithm: replacement policy, representation, variation operators, selection pressure, and parameter settings can substantially change its behavior. Jenkins et al. compare generational, steady-state \((\mu+1)\), steady-generational \((\mu,\mu)\), and \((\mu+\mu)\) variants on the Schaffer F6 function [1]. Their designs illustrate a central trade-off: full generational replacement creates many offspring per cycle, whereas steady-state methods require fewer evaluations per update; elitist \((\mu+\mu)\) replacement preserves the fittest candidates but evaluates a full offspring population.

Operator and parameter design are therefore major research concerns. The comparison in [1] uses binary tournament selection and evaluates single-point, midpoint, and blend crossover, with performance measured primarily by the number of function evaluations across 30 runs. It also uses ANOVA and Student’s t-tests to group statistically equivalent configurations, providing a useful experimental pattern for comparing stochastic optimizers. More adaptive variants attempt to regulate search behavior online. In antenna-array synthesis, a fuzzy controller adjusts standard GA parameters using the best fitness and population-diversity measurements; the reported examples indicate advantages over the standard GA formulation [8]. Another proposed extension modifies fitness through game-theoretic social interactions among cooperators and defectors, motivated by the possibility that such interactions could delay premature convergence or help populations escape local optima [5]. These studies agree that maintaining useful diversity is important, although the retrieved material does not establish a generally superior adaptation mechanism.

Benchmarking commonly emphasizes solution quality, fitness evaluations, robustness across repeated runs, and comparisons against other metaheuristics. Joshi et al. position benchmark functions as a common baseline for comparing GA, particle swarm optimization, and simulated annealing, particularly on nonlinear problems [2]. Runtime analysis provides a complementary theoretical perspective. On jump functions, the \((1+(\lambda,\lambda))\) GA can escape a local optimum efficiently under a parameter setting dependent on jump size; Antipov and Doerr study heavy-tailed random parameter choices intended to remove that dependence [4]. Together, these sources suggest that experiments should report evaluation budgets and distributions over repeated runs rather than only generation counts or a single best result. Where possible, empirical comparisons should also be paired with analysis of sensitivity to population size, mutation, crossover, and replacement policy.

Applications demonstrate the breadth of GA representations and fitness functions. GAs have evolved NAND-gate interconnections implementing AND, OR, XOR, NOR, and XNOR logic [6], reproduced observables for two-dimensional SU(2) lattice gauge theory with faster thermalization than a simple Metropolis method [7], and optimized antenna matching networks [9]. At larger computational scales, GA-based perturbed-substructure optimization searches enormous graph-topology spaces. The GAPA framework restructures genetic operations for distributed acceleration and reports an average fourfold acceleration over Evox across 10 algorithms, 18 datasets, and four graph-mining tasks [3]. Thus, scalability and implementation architecture are increasingly important alongside search quality.

## Gap

The literature provided does not offer a controlled study linking replacement strategy, diversity preservation, adaptive parameters, and parallel execution under a common evaluation budget. A useful experiment would compare generational, steady-state, and elitist GAs with fixed versus diversity-aware parameter control on the same benchmark suite, reporting fitness evaluations, wall-clock time, success rate, final solution quality, and population diversity across repeated runs. This would test whether adaptive diversity control improves search reliably or merely adds computational overhead, and whether conclusions remain stable when implementations are parallelized.

## References

[1] Alison Jenkins, Vinika Gupta, Alexis Myrick, Mary Lenoir (2019). Variations of Genetic Algorithms. http://arxiv.org/abs/1911.00490v1

[2] Mayank Joshi, M. Gyanchandani, Dr. Rajesh Wadhvani (2021). Analysis Of Genetic Algorithm, Particle Swarm Optimization and Simulated Annealing On Benchmark Functions. https://www.semanticscholar.org/paper/d9f9bedcd97912bafd5c541a200c3f6319cf7e2b

[3] Shanqing Yu, Meng Zhou, Jintao Zhou, Minghao Zhao et al. (2024). Efficient Parallel Genetic Algorithm for Perturbed Substructure Optimization in Complex Network. http://arxiv.org/abs/2412.20980v1

[4] D. Antipov, Benjamin Doerr (2020). Runtime Analysis of a Heavy-Tailed (1+(λ, λ)) Genetic Algorithm on Jump Functions. https://www.semanticscholar.org/paper/c80656f5021823d90738417269e06e2c2fae3d43

[5] Rafeal Lahoz-Beltra, Gabriela Ochoa, Uwe Aickelin (2010). Cheating for Problem Solving: A Genetic Algorithm with Social Interactions. http://arxiv.org/abs/1001.1889v1

[6] Christopher M. Frenz, Steve Peters, Wilson Julien (2009). Evolution of Digital Logic Functionality via a Genetic Algorithm. http://arxiv.org/abs/0907.4426v1

[7] A. Yamaguchi (1998). Genetic Algorithm for SU(2) Gauge Theory on a 2-dimensional Lattice. http://arxiv.org/abs/hep-lat/9809068v1

[8] Boufeldja Kadri, Miloud Boussahla, Fethi Tarik Bendimerad (2010). Phase-Only Planar Antenna Array Synthesis with Fuzzy Genetic Algorithms. http://arxiv.org/abs/1002.1176v1

[9] Jalil Rasekhi, Jalil Rashed Mohasel (2015). Optimization of the Matching Network for using Genetic Algorithm. http://arxiv.org/abs/1509.00949v1
