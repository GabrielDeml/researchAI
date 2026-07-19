# Literature survey: How often first-encountered tie-breaking changes identifiers, optimizer-family conclusions, or held-out performance

Model-selection pipelines commonly use cross-validation or a validation set to rank candidate configurations, but the retrieved literature provides little direct evidence about what happens when multiple candidates attain exactly the same recorded score. Cross-validation is fundamentally an out-of-sample model-comparison device, and its score depends on the partitioning and scoring rule used [1]. Fong and Holmes show a formal relationship between marginal likelihood and exhaustive leave-\(p\)-out cross-validation under log posterior-predictive scoring, while also emphasizing sensitivity to modeling choices such as the prior [1]. For the present topic, this establishes that a “tie” is meaningful only relative to a specified evaluation protocol and numerical precision. It does not establish that tied candidates are predictively equivalent on an independent test set.

The strongest relevant methodological warning concerns uncertainty in cross-validation estimates. Yousef analyzes the variance of cross-validation-based classifier-performance estimators and stresses that fold scores are dependent, making simple variance calculations potentially unjustified [2]. Repeated and Monte Carlo \(K\)-fold procedures can smooth over resampling variation, but uncertainty estimation remains difficult [2]. Thus, first-encountered tie-breaking should be studied across many split realizations rather than on a single split. The appropriate outcomes are hierarchical: whether changing encounter order selects a different internal configuration identifier; whether that configuration belongs to a different optimizer or model family; and whether the resulting refitted models differ in held-out performance. The last comparison should report both the paired difference in the held-out metric and its variability, rather than treating every identifier change as substantively important.

Hyperparameter-optimization research further indicates why encounter order may matter operationally even when validation scores tie. Candidate generation can follow online optimization [4], validation-gradient methods [5], stabilized bi-level optimization [6], or learned ranking surrogates [7]. These approaches traverse and prioritize configurations differently. Khazi, Pineda Arango, and Grabocka explicitly formulate surrogate optimization as preserving performance ranks rather than predicting exact response values [7], but rank-based selection still requires a convention when observed scores are equal. Because different configuration identifiers may encode nearly identical settings, an identifier-level change can exaggerate instability. Conversely, a switch between optimizer families may represent a qualitatively different modeling conclusion even if immediate validation scores are indistinguishable. Existing comparisons of model selection and model averaging also suggest that committing to one selected model is not the only response to selection ambiguity [3].

Applied work supports evaluating selection rules by genuinely out-of-sample consequences. Cross-validated tuning has improved out-of-sample portfolio performance in a high-dimensional setting [8], showing that tuning decisions can matter beyond their internal validation scores. However, none of the retrieved studies decomposes tie effects into identifier changes, optimizer-family changes, and held-out-performance changes. Dong and Li’s use of a principled threshold for ranking models when finite-sample comparisons are biased is conceptually relevant [9]: exact equality after rounding should be distinguished from differences too small to resolve reliably. A useful experiment should therefore predefine both exact and tolerance-based ties, randomize or reverse candidate encounter order, repeat the full procedure over the same collection of data splits, and report transition frequencies at all three levels.

## Gap

The specific untested question is how often first-encountered tie-breaking is merely representational, how often it changes the broader optimizer-family conclusion, and how often it produces a detectable difference on untouched held-out data. The supplied literature motivates repeated-split evaluation, uncertainty-aware comparisons, and explicit ranking rules, but reports no empirical frequency for this three-level decomposition. A new experiment should therefore separate pipeline nondeterminism from statistically meaningful model-selection instability and determine whether identifier or family changes predict any material held-out-performance change.

## References

[1] Edwin Fong, Chris Holmes (2019). On the marginal likelihood and cross-validation. http://arxiv.org/abs/1905.08737v2

[2] Waleed A. Yousef (2019). Estimating the standard error of cross-Validation-Based estimators of classifier performance. http://arxiv.org/abs/1908.00325v4

[3] Kirsten Schorning, Björn Bornkamp, Frank Bretz, Holger Dette (2015). Model Selection versus Model Averaging in Dose Finding Studies. http://arxiv.org/abs/1508.00281v1

[4] Hongyuan Zhan, Gabriel Gomes, Xiaoye S. Li, Kamesh Madduri et al. (2018). Efficient Online Hyperparameter Optimization for Kernel Ridge Regression with Applications to Traffic Time Series Prediction. http://arxiv.org/abs/1811.00620v1

[5] Luca Franceschi, Michele Donini, Paolo Frasconi, Massimiliano Pontil (2017). Forward and Reverse Gradient-Based Hyperparameter Optimization. http://arxiv.org/abs/1703.01785v3

[6] Sauptik Dhar, Unmesh Kurup, Mohak Shah (2020). Stabilizing Bi-Level Hyperparameter Optimization using Moreau-Yosida Regularization. http://arxiv.org/abs/2007.13322v1

[7] Abdus Salam Khazi, Sebastian Pineda Arango, Josif Grabocka (2023). Deep Ranking Ensembles for Hyperparameter Optimization. http://arxiv.org/abs/2303.15212v2

[8] Sven Husmann, Antoniya Shivarova, Rick Steinert (2019). Cross-validated covariance estimators for high-dimensional minimum-variance portfolios. http://arxiv.org/abs/1910.13960v5

[9] Qianyu Dong, Zehang Richard Li (2026). Design-Based Cross-Validation for Comparing Small Area Estimators. http://arxiv.org/abs/2604.23464v3
