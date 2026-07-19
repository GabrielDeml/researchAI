# Literature survey: Distributions of rule-selection outcomes across prospectively defined 48-seed blocks

Rule-based heterogeneous treatment-effect (HTE) analysis typically separates candidate discovery, rule selection, and subsequent rule analysis. Causal rule learning, for example, generates subgroup rules with estimated average treatment effects, selects a subset that helps represent individual-level effects, and then analyzes promising rules for validation [1]. This workflow supports interpretable subgroup discovery but also creates multiple stochastic outputs: which rule is selected, its estimated uplift, and how many observations satisfy it. These outputs may vary substantially with data realization, especially when rules overlap, candidate effects are similar, or eligible subgroups are small. Prior uplift research likewise emphasizes that treatment effects are fundamentally counterfactual and therefore cannot be evaluated using ordinary supervised-learning labels [10]. Unbiased policy-value or expected-response estimators are consequently more appropriate than predictive accuracy for held-out evaluation [10].

Selecting the rule with the largest estimated uplift raises a direct winner’s-curse problem. The maximum among noisy candidate estimates is systematically optimistic, particularly when many candidates have similar underlying effects [2]. Thus, the distribution of selected-rule uplift across repeated, independently generated blocks should not be interpreted as the sampling distribution of a fixed, prespecified rule. It combines estimation noise with selection-induced optimism and possible changes in selected-rule identity. Zrnic and Fithian propose simultaneous-inference-based correction for the selected winner and explicitly distinguish inference about the selected candidate’s value from inference about the identity of the population winner [2]. Berman, Zhang, and Zhao similarly distinguish bias relative to the true best candidate from bias relative to the selected candidate’s own mean, and argue that bias, mean squared error, coverage, and deployment regret are different evaluation targets [3]. This distinction makes held-out retention—how much of the discovery-block uplift remains in independent evaluation data—especially informative, although the supplied literature does not establish a standard retention formula.

Sample splitting and cross-fitting provide the clearest methodological precedent for separating selection from evaluation. Guo and Gao use two-way sample splitting to decouple nuisance estimation from candidate weighting when selecting among HTE estimators, with error control framed as a multiple-testing problem [4]. For the proposed experiment, prospectively defining each 48-seed block and holding evaluation data apart from rule selection serves a related purpose: it prevents favorable seeds or rules from being chosen after outcomes are observed. Across blocks, reporting the full distribution—not only the mean—of selected uplift and held-out retention would reveal optimism, dispersion, skewness, and failure rates. Reporting selected-rule identity frequencies would additionally show whether apparent performance comes from a stable rule or from many interchangeable winners.

The remaining outcomes are operational but decision-relevant. Eligible sample size determines how much information supports a selected subgroup estimate and may explain unstable uplift or identity switching; CRL reports better performance with sufficient sample sizes, underscoring this dependence [1]. Threshold-decision rate measures how often the selected rule clears a prospectively specified action criterion. This should be kept distinct from effect-estimation quality because better HTE estimation does not necessarily produce a better treatment rule [5]. Policy-learning work similarly treats treatment assignment as optimization under application-specific constraints rather than as estimation alone [6]. Feature-selection research also warns that excessive candidate complexity can increase overfitting and reduce interpretability in uplift models [9].

## Gap

None of the retrieved sources studies prospectively defined **48-seed blocks** or jointly reports the distributions of selected-rule uplift, held-out retention, rule identity, eligible sample size, and threshold decisions. The open empirical question is therefore whether repeated selection produces a reproducible, adequately supported rule whose apparent uplift persists out of sample—or instead yields unstable identities, small eligible groups, winner’s-curse attenuation, and highly variable decision rates. A new experiment should prespecify block construction, candidate rules, selection and tie-breaking procedures, the retention statistic, eligibility requirements, and the decision threshold, then report both marginal distributions and relationships among these five outcomes.

## References

[1] Wu, Liu, Ren, Ma et al. (2023). A New Causal Rule Learning Approach to Interpretable Estimation of Heterogeneous Treatment Effect. http://arxiv.org/abs/2310.06746v3

[2] Zrnic and Fithian (2024). A Flexible Defense Against the Winner's Curse. http://arxiv.org/abs/2411.18569v1

[3] Berman, Zhang, and Zhao (2026). Valuing Winners: When and How to Correct for Selection Bias in Randomized Experiments. http://arxiv.org/abs/2605.18887v1

[4] Guo and Gao (2025). Reliable Selection of Heterogeneous Treatment Effect Estimators. http://arxiv.org/abs/2511.18464v1

[5] Chen and Xie (2022). Estimating heterogeneous treatment effects versus building individualized treatment rules: Connection and disconnection. http://arxiv.org/abs/2210.01342v1

[6] Athey and Wager (2017). Policy Learning with Observational Data. http://arxiv.org/abs/1702.02896v6

[9] Zhao, Zhang, Harinen, and Yung (2020). Feature Selection Methods for Uplift Modeling and Heterogeneous Treatment Effect. http://arxiv.org/abs/2005.03447v2

[10] Zhao, Fang, and Simchi-Levi (2017). Uplift Modeling with Multiple Treatments and General Response Types. http://arxiv.org/abs/1705.08492v1
