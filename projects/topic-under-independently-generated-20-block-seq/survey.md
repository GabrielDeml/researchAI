# Literature survey: Null distribution of lag-1 sample autocorrelation in independently generated 20-block uplift and binary-decision sequences

The target statistic, `numpy.corrcoef(z[:-1], z[1:])[0, 1]`, is the Pearson correlation between two overlapping length-19 vectors formed from a 20-block sequence. Empirical work commonly uses first-order Pearson autocorrelation, including within rolling windows, and may supplement it with omnibus procedures such as the Ljung–Box test [2]. However, a sequence of only 20 observations places this problem firmly in the finite-sample regime. Because adjacent pairs share observations, the statistic’s null distribution should not be treated as the ordinary correlation distribution for two independently sampled vectors. The literature supplied here does not give that null distribution for independent, transformed uplift outputs or thresholded binary decisions.

Finite-sample distribution theory for autocorrelation is available in more specialized models. Abadir derives an exact density for the autocorrelation coefficient and its Studentized ratio in a first-order Gaussian autoregression [1]. This establishes that exact autocorrelation distributions can depend materially on sample size, model structure, and the precise statistic being computed. Nevertheless, those results concern Gaussian autoregressive observations and cannot automatically be transferred to independently generated block-level outputs, especially after uplift-based selection or binary thresholding. Robust-autocorrelation work likewise emphasizes that classical autocorrelation estimation can behave poorly under heavy tails or outliers and proposes alternative estimators [3], but it does not characterize the requested NumPy/Pearson statistic under the present null.

Binary threshold decisions introduce additional discreteness. Research on binary sequences studies attainable autocorrelation values and the existence of sequences with unusually small or constant off-peak autocorrelation [4]. That work demonstrates that binary-valued autocorrelation is constrained by combinatorial structure. Its setting, however, is periodic sequences encoded as \(\{-1,1\}\), with uncentered cyclic autocorrelation sums over all positions [4]. The target statistic instead uses centered Pearson correlation, excludes the wraparound pair, and can be undefined when either length-19 vector has zero variance. Thus, periodic binary-sequence results are conceptually relevant but do not provide the desired null distribution. For thresholded decisions, the distribution is also likely to depend on the marginal probability of crossing the threshold, which should therefore be controlled or recorded in an experiment.

The “selected uplift” component creates a separate inferential issue. Uplift modeling estimates changes in outcome probability caused by treatment and is used to target individuals or subgroups according to estimated treatment effects [5], with tree-based methods explicitly choosing partitions that maximize treatment–control outcome differences [6]. If an uplift rule, model, threshold, or reported sequence is selected using the same simulated outputs later tested for autocorrelation, the null distribution is conditional on that selection mechanism rather than merely on block independence. General post-selection work warns that conventional inference loses its guarantees after data-driven selection and motivates simultaneous or selection-adjusted inference [7]. More recent GLM work similarly uses simulation to evaluate corrections for naive inference after Lasso selection, including with non-Gaussian responses [8]. These sources do not solve the autocorrelation problem, but they support reproducing the complete uplift fitting, threshold choice, and selection pipeline within every null replicate.

## Gap

No retrieved source characterizes the finite-sample null distribution of this exact lag-1 NumPy statistic for \(n=20\) independently generated blocks, either for continuous selected-uplift values or thresholded binary decisions. A new experiment should therefore estimate the null distribution by Monte Carlo while preserving the full data-generating and selection procedure. Results should be stratified by uplift rule and binary threshold, report undefined-correlation frequency, and summarize the empirical mass or density, bias, quantiles, and tail probabilities. Comparisons with Gaussian continuous outputs and binary outputs at fixed event probabilities would help distinguish overlap-driven finite-sample behavior from effects caused by thresholding and selection.

## References

[1] K. Abadir (2026). *The Finite-Sample Density of the Sufficient Statistic and Related Tests in a Gaussian Autoregression*. https://www.semanticscholar.org/paper/d08dc5fbcd700edca1635385c0a5e0ce79bef585

[2] Eugene Tartakovsky, Ksenia Plesovskikh, Anastasiia Sarmakeeva, Alexander Bibik (2020). *Autocorrelation of returns in major cryptocurrency markets*. http://arxiv.org/abs/2003.13517v2

[3] Yunlu Jiang, Fudong Chen, Xiao Yan (2025). *Robust Adaptive Lasso via Robust Sample Autocorrelation Coefficient for the Autoregressive Models*. https://www.semanticscholar.org/paper/0d5a21bc51caa4a22d01a412bb8c97df0735cb1d

[4] X. Niu, H. Cao, K. Feng (2018). *Non-existence of perfect binary sequences*. http://arxiv.org/abs/1804.03808v1

[5] Théo Verhelst, Denis Mercier, Jeevan Shrestha, Gianluca Bontempi (2023). *A churn prediction dataset from the telecom sector: a new benchmark for uplift modeling*. http://arxiv.org/abs/2312.07206v1

[6] Fanglan Zheng, Menghan Wang, Kun Li, Jiang Tian et al. (2023). *Causal Inference Based Single-branch Ensemble Trees For Uplift Modeling*. http://arxiv.org/abs/2302.01563v1

[7] Richard Berk, Lawrence Brown, Andreas Buja, Kai Zhang et al. (2013). *Valid post-selection inference*. http://arxiv.org/abs/1306.1059v1

[8] Qinyan Shen, Karl Gregory, Xianzheng Huang (2026). *Post-selection inference in generalized linear models via parametric programming*. http://arxiv.org/abs/2603.24875v1
