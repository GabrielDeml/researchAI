# Literature survey: Tuning ties under a prespecified stochastic data-generating process

Multiple optimal or near-optimal solutions are theoretically plausible, but the supplied literature does not establish how frequently they arise spontaneously in repeated samples from a fixed stochastic data-generating process (DGP). Rubinstein and Simma study empirical risk minimization over finite hypothesis spaces and show a sharp stability distinction between unique and multiple population-risk minimizers: stability can improve exponentially with sample size under a unique minimizer, whereas multiple minimizers preclude comparably fast CV-stability rates [1]. This establishes that genuine multiplicity can materially affect sample-to-sample selection behavior. However, it starts from the premise that the risk-minimizer set is multiple; it does not estimate the probability that finite-sample tuning produces exact ties, nor distinguish ties caused by equal population risks from accidental equality of noisy validation scores.

The Rashomon-set literature broadens multiplicity from exact minimizers to models with near-identical empirical performance. Work on rule sets treats exhaustive enumeration as computationally expensive and proposes representative exploration or set-size estimation [4]. Related methods generate diverse, similarly accurate concept-based models [5] and approximate decision-tree Rashomon sets efficiently [6]. This work supplies a useful operational concept for a “practically indistinguishable” tie: membership in a performance band around the empirical optimum, rather than literal equality. It also emphasizes that tied or near-tied models may differ substantially in structure or decision logic [4–6]. Clinical and federated-learning work similarly frames multiplicity as consequential for robustness, transparency, and selection under downstream constraints [3,7]. Nevertheless, these studies primarily seek, construct, or explore collections of near-optimal models. They therefore do not answer how often such collections emerge without deliberately encouraging diversity, setting their size, or otherwise conditioning on multiplicity.

For tuning experiments, the central measurement problem is that cross-validation scores vary with both the data partition and stochastic learner behavior. Merola argues that ordinary repeated cross-validation can select different settings because comparisons are contaminated by varying partitions and random seeds [2]. Blocked cross-validation addresses this by evaluating settings under matched CV partitions and learner-randomness conditions, producing more precise estimates of hyperparameter effects with fewer runs [2]. This is directly relevant to tie detection: common random conditions reduce comparison noise and help separate genuine score proximity from artifacts of unmatched resampling. A suitable study should report both exact equality under the chosen scoring implementation and practical ties defined by a prespecified tolerance, while preserving the same tolerance, candidate grid, partitioning strategy, and randomness protocol across DGP replications. Because CV targets can depend on the scoring and resampling scheme, those choices must be explicit. Fong and Holmes show, in a Bayesian setting, that marginal likelihood corresponds to exhaustive leave-\(p\)-out CV averaged over all holdout sizes and sets when log posterior predictive probability is used [8], illustrating that the validation functional itself determines what “equal performance” means.

Optimization methods add another possible source of apparent multiplicity. Moreau–Yosida regularization is proposed to stabilize bi-level hyperparameter optimization [9], while dynamic-accuracy derivative-free optimization allows inexact lower-level evaluations with convergence guarantees [10]. These methods address convergence and computational accuracy, not the natural incidence or composition of ties. Consequently, optimizer output should not be treated as direct evidence that the underlying tuning objective has one or several optima: the experiment must distinguish score ties among fully evaluated candidates from repeated optimizer returns caused by approximation, stopping rules, or search behavior.

## Gap

No supplied source measures, under a fully prespecified stochastic DGP and tuning pipeline, the repeated-sampling frequency of exact or tolerance-based tuning ties while leaving tie count, optimizer composition, and post-selection test-performance ordering unconstrained. A new experiment should repeatedly generate independent datasets, apply an unchanged candidate set and blocked validation protocol, record the complete empirical minimizer or near-minimizer set, and then evaluate all tied candidates on independent data. This would estimate not only tie incidence and multiplicity, but also whether validation-indistinguishable candidates have stable or reversible out-of-sample orderings—an angle not tested by the retrieved work.

## References

[1] Benjamin I. P. Rubinstein, Aleksandr Simma (2010). On the Stability of Empirical Risk Minimization in the Presence of Multiple Risk Minimizers. http://arxiv.org/abs/1002.2044v1

[2] Giovanni Maria Merola (2023). Blocked Cross-Validation: A Precise and Efficient Method for Hyperparameter Tuning. http://arxiv.org/abs/2306.06591v2

[3] Yuwen Zhang, Viet Tran, Paul Weng (2025). Intervention Efficiency and Perturbation Validation Framework: Capacity-Aware and Robust Clinical Model Selection under the Rashomon Effect. http://arxiv.org/abs/2511.14317v7

[4] Martino Ciaperoni, Han Xiao, Aristides Gionis (2024). Efficient Exploration of the Rashomon Set of Rule Set Models. http://arxiv.org/abs/2406.03059v1

[5] Shihan Feng, Cheng Zhang, Michael Xi, Ethan Hsu et al. (2025). Exploring the Rashomon Set for Concept-Based Models. http://arxiv.org/abs/2511.19636v2

[6] Zakk Heile, Hayden McTavish, Varun Babbar, Margo Seltzer et al. (2026). From Rashomon Theory to PRAXIS: Efficient Decision Tree Rashomon Sets. http://arxiv.org/abs/2606.00202v1

[7] Xenia Heilmann, Luca Corbucci, Mattia Cerrato (2026). Rashomon Sets and Model Multiplicity in Federated Learning. http://arxiv.org/abs/2602.09520v3

[8] Edwin Fong, Chris Holmes (2019). On the marginal likelihood and cross-validation. http://arxiv.org/abs/1905.08737v2

[9] Sauptik Dhar, Unmesh Kurup, Mohak Shah (2020). Stabilizing Bi-Level Hyperparameter Optimization using Moreau-Yosida Regularization. http://arxiv.org/abs/2007.13322v1

[10] Matthias J. Ehrhardt, Lindon Roberts (2020). Efficient Hyperparameter Tuning with Dynamic Accuracy Derivative-Free Optimization. http://arxiv.org/abs/2011.03151v1
