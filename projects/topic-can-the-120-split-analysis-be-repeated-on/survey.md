# Literature survey: Can the 120-split analysis be repeated on a genuinely untouched replication set under a time-stamped protocol?

The strongest methodological precedent is preregistered replication on previously unexamined data. Lei, Gelman, and Ghitza distinguish reproducing results with the original data and code from a “true replication” using new data and a prespecified processing and analysis plan [1]. Their staged design—duplication, replication on already-analyzed data, and preregistered analysis of surveys they had not inspected—shows why the untouched status of the replication set matters. Reusing familiar data does not eliminate researcher degrees of freedom or the “forking paths” created by outcome-dependent choices. They also demonstrate that preregistration remains useful when data already exist and the analysis is not reducible to a single significance test [1]. For the proposed experiment, the replication set should therefore be access-controlled or otherwise demonstrably unseen, and the protocol should be time-stamped before labels, scores, or outcome summaries are accessed.

DOME provides a complementary framework for specifying the computational workflow under four headings: data, optimization, model, and evaluation [2]. Applied here, the protocol should identify the replication population and exclusions; fix the number and construction of the 120 splits; define the optimization grid; and state all model-fitting and evaluation procedures. Fixing tie-breaking is especially important because equally scored configurations can otherwise permit an undocumented, outcome-dependent choice. The same applies to the proposed regime check, robustness interval, and secondary analyses: each needs an operational definition, execution order, and decision rule. DOME does not prescribe particular solutions, but its checklist orientation supports recording software, preprocessing, optimization, and evaluation details sufficiently precisely that an independent analyst could execute the analysis without discretionary intervention [2].

The validation literature clarifies why optimization and evaluation must be separated or, at minimum, explicitly characterized. Wainer and Cawley describe nested cross-validation as using inner folds for hyperparameter selection and outer folds for an unbiased estimate of the performance of the tuning procedure; they contrast this with flat cross-validation, which uses the same cross-validation process for selection and estimation and is consequently biased as an estimator, though it may still be used for algorithm selection [3]. May, Hartmann, and Klawonn take a stronger position for high-dimensional, very-small-sample settings, where they argue that nested cross-validation is necessary to avoid biased performance estimation, while also noting that tiny validation sets can produce high variance and make pruning decisions unreliable [4]. Thus, whether each of the 120 splits contains an internal tuning layer, and whether the fixed grid is searched using replication outcomes, must be settled in advance. Learning-curve methods can accelerate model or hyperparameter selection [6], but introducing such adaptive early stopping would create additional decision points unless its rule were also preregistered.

Bootstrap inference likewise cannot be treated as automatically valid. Das and Lahiri show, for regression M-estimators, that even studentization details can determine whether a perturbation bootstrap attains second-order correctness [8]. Lin and Han provide a sharper warning: the standard bootstrap can be inconsistent for a statistic that is nevertheless asymptotically normal [9]. Conversely, Kloodt and Neumeyer establish multiplier-bootstrap validity for particular semiparametric tests [10]. Collectively, these sources support prespecifying the resampling unit, resample count, statistic, confidence-interval construction, and treatment of dependence across splits—and justifying that bootstrap for the exact target statistic. Any “robustness interval” should also be distinguished from a conventional confidence interval; related work shows that finite-sample comparison bias can sometimes be bounded and used as a ranking threshold, but only under a specifically derived design-based framework [7].

## Gap

None of the retrieved sources reports the original 120-split analysis or establishes that its exact grid, tie-breaking rule, regime check, bootstrap, robustness interval, and secondary analyses have been repeated on untouched data. The open question is therefore procedural and empirical: whether the original optimization comparison survives when every consequential choice is frozen in a time-stamped, executable protocol and applied once to a genuinely uninspected replication set. The experiment should treat deviations, failed regime checks, ties, and inconclusive intervals as prespecified outcomes rather than opportunities for post hoc revision.

## References

[1] Rayleigh Lei, Andrew Gelman, Yair Ghitza (2016). The 2008 election: A preregistered replication analysis. http://arxiv.org/abs/1607.04157v1

[2] Ian Walsh, Dmytro Fishman, Dario Garcia-Gasulla, Tiina Titma et al. (2020). DOME: Recommendations for supervised machine learning validation in biology. http://arxiv.org/abs/2006.16189v4

[3] Jacques Wainer, Gavin Cawley (2018). Nested cross-validation when selecting classifiers is overzealous for most practical applications. http://arxiv.org/abs/1809.09446v1

[4] Sigrun May, Sven Hartmann, Frank Klawonn (2022). Combined Pruning for Nested Cross-Validation to Accelerate Automated Hyperparameter Optimization for Embedded Feature Selection in High-Dimensional Data with Very Small Sample Sizes. http://arxiv.org/abs/2202.00598v2

[6] Felix Mohr, Jan N. van Rijn (2022). Learning Curves for Decision Making in Supervised Machine Learning: A Survey. http://arxiv.org/abs/2201.12150v2

[7] Qianyu Dong, Zehang Richard Li (2026). Design-Based Cross-Validation for Comparing Small Area Estimators. http://arxiv.org/abs/2604.23464v3

[8] Debraj Das, Soumendra Nath Lahiri (2016). Second Order Correctness of Perturbation Bootstrap M-Estimator of Multiple Linear Regression Parameter. http://arxiv.org/abs/1605.01440v2

[9] Zhexiao Lin, Fang Han (2023). On the failure of the bootstrap for Chatterjee's rank correlation. http://arxiv.org/abs/2303.14088v2

[10] Nick Kloodt, Natalie Neumeyer (2017). Specification tests in semiparametric transformation models - a multiplier bootstrap approach. http://arxiv.org/abs/1709.06855v2
