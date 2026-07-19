# Null-Space Output-Norm Intervention in Modular-Addition Grokking: A Broken Experiment

## Abstract

This study proposed manipulating a reported total parameter norm through a class-common output component that is exactly invisible to centered logits, softmax probabilities, cross-entropy, predictions, and ordinary parameter updates. No experimental runs, per-seed observations, trajectories, audit records, software versions, executable code, `results.json`, compressed curves, or `result.png` were supplied. The proposed empirical comparison therefore was not executed and cannot support an empirical contribution.

More importantly, the original fork comparison is behaviorally identical by construction. Because the added component is externally scheduled, analytically removed before loss and prediction calculations, and excluded from parameter and optimizer updates, both forks must have identical trainable parameters, gradients, optimizer states, predictions, and grokking steps whenever deterministic replay and implementation audits pass. Threshold crossing cannot influence optimization. The defensible conclusion is consequently narrow: an externally tracked, functionally disconnected contribution to a conceptual norm is not sufficient to change grokking. This is an algebraic negative control against naive interpretations of every reported norm threshold as causal; it is not evidence that the norm of actual optimized parameters is causally irrelevant.

The expensive fork experiment should therefore be replaced by an equivalence proof, with limited numerical tests used only to validate the implementation. A genuinely causal follow-up would need to transform actual parameters in a function-preserving manner and then allow those parameters to participate in optimization, while separately controlling initial logits, optimizer moments, effective learning rates, and weight decay. The present study remains **broken as an empirical study** because no such redesigned experiment was executed and no empirical artifacts are available.

## Background

Grokking is delayed generalization after training performance has already saturated. Modular arithmetic supplies a finite setting in which all examples can be enumerated and training and test trajectories can be measured exactly. The supplied manuscript associated this setting with prior work on modular-arithmetic grokking [1], internal circuits and modular-polynomial tasks [2], weight decay and norm-based explanations [3], logit-scale mediation [4], first-passage prediction [5], abstraction and inductive bias [6][9], interactions between weight decay and optimization [7], and alternative explanations of optimizer trajectories [8].

Those numbered citations were supplied without authors, titles, publication venues, years, URLs, or any reference list. A complete bibliography therefore cannot be reconstructed without inventing bibliographic information. Accordingly, this revision does not claim verified novelty relative to the cited literature. In particular, the relationship of the proposed intervention to prior work on scale symmetries, softmax-null directions, weight decay, and grokking remains unsubstantiated until the missing citation metadata and a complete bibliography are provided.

The conceptual motivation was to distinguish parameter norm from quantities correlated with it, such as logits, confidence, gradients, and optimizer state. Adding the same scalar to every class logit leaves softmax probabilities unchanged. If \(z\in\mathbb R^K\) is a logit vector and \(\gamma\) is any scalar, then

\[
\operatorname{softmax}(z+\gamma\mathbf 1_K)
=
\operatorname{softmax}(z).
\]

That identity makes a class-common output component useful as an implementation negative control. It does not, however, supply an intervention on the causal optimization dynamics when the component is external to the trainable parameter state.

The original proposal treated crossing a fitted conceptual-norm threshold as though it could test a dynamical threshold hypothesis. The threshold had no mechanism to affect optimization: it neither changed the loss nor triggered a learning-rate, optimizer, parameter, or weight-decay update. Its crossing was therefore only a diagnostic event on an exogenous scalar trajectory. At most, the design can falsify the naive claim that any scalar called “total norm,” including a causally disconnected bookkeeping contribution, must change grokking when it crosses a threshold.

A stronger test requires modifying actual optimized parameters. For the ReLU network in this study, a positive rescaling of one hidden layer and the inverse rescaling of the next layer can preserve the initial network function while changing actual parameter norm. Once optimization resumes, different treatments of optimizer moments, effective learning rates, and weight decay can make competing causal hypotheses predict different trajectories. No such experiment was completed here.

## Hypothesis

The original prespecified hypothesis was:

> At a memorized cross-entropy checkpoint, adding a rank-one class-common component to the output matrix that doubles total squared parameter norm while leaving every softmax probability unchanged, then decaying only that component until total norm crosses the threshold fitted from ordinary AdamW runs, will change the sustained-95%-test-accuracy grokking step by less than 10% relative to an unmodified no-decay fork across four matched seeds.

That statement should not be interpreted as an open causal hypothesis. Under the specified implementation, equality of the two behavioral trajectories is an algebraic consequence of the intervention’s disconnection from the model and optimizer. The corrected, narrow claim is:

> An externally tracked class-common norm component that is excluded from the trainable parameter state, removed before loss and prediction calculations, and prevented from modifying optimizer state is insufficient to change grokking.

This claim is a negative control or diagnostic falsification of a naive norm-threshold interpretation. It does not imply that changing the norm of actual parameters has no causal effect, that task-relevant norm directions are irrelevant, or that weight decay acts only through total norm.

The original decision statistic was

\[
R_{\max}=\max_s
\frac{|G_{\mathrm{intervention},s}-G_{\mathrm{base},s}|}
{G_{\mathrm{base},s}}.
\]

Its denominator is not appropriate for measuring a post-checkpoint intervention. If an empirical fork study were conducted, the relevant latency for seed \(s\) would be

\[
L_{\mathrm{base},s}=G_{\mathrm{base},s}-C_s,
\qquad
L_{\mathrm{intervention},s}=G_{\mathrm{intervention},s}-C_s,
\]

and an observed relative effect could be defined as

\[
R^{\mathrm{latency}}_s
=
\frac{|L_{\mathrm{intervention},s}-L_{\mathrm{base},s}|}
{L_{\mathrm{base},s}}
=
\frac{|G_{\mathrm{intervention},s}-G_{\mathrm{base},s}|}
{G_{\mathrm{base},s}-C_s}.
\]

This denominator measures the remaining training time after the intervention rather than diluting the effect by all pre-checkpoint training. No values of this statistic can be reported because no checkpoint or grokking observations were supplied.

The originally proposed maximum over four seeds and fixed 10% cutoff cannot support a population-level conclusion. A redesigned empirical study would need a prespecified equivalence margin, a seed count justified by an equivalence or precision analysis, uncertainty intervals, and independent reference and evaluation seeds. Those design quantities cannot be retroactively selected from absent data.

## Method

The planned task and model are documented here for completeness, but they were not accompanied by executable code, software versions, logs, or machine-readable outputs.

For each seed \(s\in\{0,1,2,3\}\), the planned task was addition modulo \(23\). The complete dataset contained all \(23^2=529\) ordered pairs, with labels

\[
y=(a+b)\bmod 23.
\]

A class-stratified split generated with NumPy seed \(1000+s\) selected 9 examples from each of the 23 classes for training, yielding 207 training examples and 322 test examples per seed. Training was to be full-batch with a fixed example order.

The model contained separate \(23\times32\) embeddings for the operands. Their concatenated 64-dimensional representation passed through a biased \(64\to128\) affine layer, ReLU, and a biased \(128\to23\) output layer. Matrices were to be initialized from \(\mathcal N(0,1/\sqrt{\text{fan-in}})\) using Torch seed \(2000+s\), with zero biases. Losses and predictions were to use class-centered logits.

Metrics were to be evaluated every 10 optimization steps, including step 0. Memorization was defined as the first evaluation beginning 10 consecutive evaluations with training accuracy 1.0 and training cross-entropy at most 0.02. The grokking step \(G\) was the first evaluation beginning 20 consecutive evaluations with test accuracy at least 0.95.

An ordinary AdamW reference run was specified for each seed, with learning rate 0.001, betas \((0.9,0.98)\), epsilon \(10^{-8}\), and weight decay 0.1. Reference runs were capped at 25,000 steps. If all four runs grokked, the threshold \(T\) was to be the median total parameter norm at their grokking steps.

For each seed, a checkpoint \(C_s\) was to be selected after memorization and at least 200 steps before reference grokking. It also had to have test accuracy below 0.95 and checkpoint norm \(N_s\) satisfying

\[
N_s<T<\sqrt{2}N_s.
\]

The trajectory was then to be replayed deterministically to \(C_s\), requiring loss, accuracy, and norm agreement within \(10^{-10}\).

This plan used the same four seeds to fit the threshold, determine checkpoint eligibility, and evaluate the intervention. That does not provide an out-of-sample threshold test. It also silently conditions the analysis on every reference run grokking and possessing a checkpoint that meets all timing and norm-bracketing requirements. A valid empirical protocol would first conduct and report a feasibility phase, including every attempted seed, the frequency of grokking by the cap, the frequency of memorization, and the frequency of eligible checkpoints. Reference seeds used to fit and freeze \(T\) would then have to be disjoint from intervention seeds.

At \(C_s\), the original protocol proposed copying the model and AdamW state into two forks and disabling weight decay in both. The intervention fork additionally received an externally represented class-common output component. Let \(K=23\), let \(W\in\mathbb R^{K\times128}\) be the ordinary output matrix, and let

\[
\mu=\frac{1}{K}\mathbf 1_K^\top W
\]

be its mean row. A deterministic unit vector \(q\) orthogonal to \(\mu\) was to be constructed. If \(S_s\) denoted the total checkpoint squared parameter norm, the component was initialized as

\[
a_0=q\sqrt{\frac{S_s}{K}},
\]

and the conceptual intervention matrix was

\[
W_{\mathrm{int}}=W+\mathbf 1_Ka^\top.
\]

The component was scheduled to decay linearly over 200 post-checkpoint steps, stopping at the first absolute step \(X_s\) at which the conceptual total norm was no greater than \(T\). Both forks were otherwise to receive the same no-decay Adam updates for at most 8,000 post-checkpoint steps.

### Formal equivalence of the original forks

Let the ordinary model parameters be \(\theta\), including \(W\), and let \(h_\theta(x)\) be the final hidden representation. The ordinary logits are

\[
z_\theta(x)=Wh_\theta(x)+b.
\]

The conceptual intervention logits are

\[
\begin{aligned}
z_{\theta,a}(x)
&=
\left(W+\mathbf 1_Ka^\top\right)h_\theta(x)+b\\
&=
z_\theta(x)+\mathbf 1_K\left(a^\top h_\theta(x)\right).
\end{aligned}
\]

Define the centering projection

\[
P=I_K-\frac{1}{K}\mathbf 1_K\mathbf 1_K^\top.
\]

Because \(P\mathbf 1_K=0\),

\[
Pz_{\theta,a}(x)=Pz_\theta(x).
\]

It follows that the centered logits are invariant. Softmax probabilities are also invariant:

\[
\operatorname{softmax}(z_{\theta,a}(x))
=
\operatorname{softmax}(z_\theta(x)).
\]

Consequently, for every example and label,

\[
\ell(z_{\theta,a}(x),y)=\ell(z_\theta(x),y),
\]

and the predicted class is unchanged. Since \(a\) is not part of the ordinary trainable parameter state and the same loss is differentiated with respect to \(\theta\),

\[
\nabla_\theta \ell_{\mathrm{intervention}}
=
\nabla_\theta \ell_{\mathrm{base}}.
\]

Suppose the forks begin with identical ordinary parameters and optimizer state,

\[
\theta^{\mathrm{int}}_{C_s}=\theta^{\mathrm{base}}_{C_s},
\qquad
o^{\mathrm{int}}_{C_s}=o^{\mathrm{base}}_{C_s}.
\]

For a deterministic optimizer update map \(F\), both forks then satisfy

\[
(\theta_{t+1},o_{t+1})
=
F(\theta_t,o_t,\nabla_\theta\ell_t).
\]

Equality of the current parameters, optimizer states, and gradients implies equality after the update. By induction,

\[
\theta^{\mathrm{int}}_t=\theta^{\mathrm{base}}_t,
\qquad
o^{\mathrm{int}}_t=o^{\mathrm{base}}_t
\]

at every subsequent step, subject only to implementation correctness and deterministic numerical execution. Therefore their losses, probabilities, predictions, accuracy trajectories, and grokking steps must also be identical.

The conceptual norm need not be identical. Its output-matrix contribution is

\[
\begin{aligned}
\left\|W+\mathbf 1_Ka^\top\right\|_F^2
&=
\|W\|_F^2
+2\left\langle W,\mathbf 1_Ka^\top\right\rangle
+\left\|\mathbf 1_Ka^\top\right\|_F^2\\
&=
\|W\|_F^2+2K\mu^\top a+K\|a\|_2^2.
\end{aligned}
\]

At the checkpoint, \(\mu^\top a_0=0\) and \(K\|a_0\|_2^2=S_s\), so adding the conceptual component increases the squared norm by \(S_s\). Because \(S_s\) is the original total squared parameter norm, the initial conceptual total squared norm is doubled. This norm change does not enter the loss or optimizer update.

After training resumes, \(\mu^\top a_t\) is not guaranteed to remain zero unless that property is separately established. Thus the full conceptual norm trajectory and exact threshold crossing would still need numerical calculation. That fact does not weaken the behavioral equivalence proof: whatever conceptual norm is reported, neither its value nor its threshold crossing can affect \(\theta_t\), optimizer state, logits, or predictions under the specified implementation.

The planned probability, centered-logit, cross-entropy, prediction, class-common-residual, parameter-drift, optimizer-drift, replay, and initial norm-doubling audits are therefore implementation checks rather than tests of a scientific causal alternative. Experiments could validate that these differences remain within the specified tolerances, but a successful audit would confirm the equivalence construction rather than discover a null causal effect.

### Required redesign for an empirical causal study

A non-predetermined intervention can use the positive homogeneity of ReLU to alter actual parameter norms while preserving the function at the checkpoint. Write the post-embedding network as

\[
f_\theta(x)=B\,\operatorname{ReLU}(Ax+b)+d.
\]

For any \(c>0\), define

\[
A'=cA,\qquad b'=cb,\qquad B'=\frac{1}{c}B,\qquad d'=d.
\]

Because ReLU is positively homogeneous,

\[
\operatorname{ReLU}(c(Ax+b))
=
c\,\operatorname{ReLU}(Ax+b),
\]

and therefore

\[
B'\operatorname{ReLU}(A'x+b')+d'
=
B\operatorname{ReLU}(Ax+b)+d.
\]

The initial logits, probabilities, loss, and predictions are exactly preserved, but the actual parameter norm changes:

\[
\|\theta'\|_2^2
=
c^2\bigl(\|A\|_F^2+\|b\|_2^2\bigr)
+
c^{-2}\|B\|_F^2
+
\|d\|_2^2
\]

plus the unchanged embedding norms. Unlike the external null component, all transformed parameters subsequently participate in optimization.

The initial gradients transform differently across layers. Away from ReLU boundary ambiguities,

\[
\nabla_{A'}\ell=\frac{1}{c}\nabla_A\ell,
\qquad
\nabla_{b'}\ell=\frac{1}{c}\nabla_b\ell,
\qquad
\nabla_{B'}\ell=c\nabla_B\ell.
\]

Consequently, a common optimizer configuration need not preserve the scale-equivalent relationship after the next update. Adam moments, epsilon, decoupled weight decay, and layerwise effective step sizes can each contribute to divergence. A redesigned study should therefore compare prespecified arms that separately address:

1. transformed actual parameters with exactly matched checkpoint logits;
2. transformed versus untransformed optimizer moments;
3. blockwise learning-rate adjustments intended to match or deliberately vary effective functional update sizes;
4. matched versus varied decoupled weight decay;
5. direct measurements of centered logits, margins, gradients, parameter displacement, and effective learning rates.

This design permits competing causal explanations to predict different outcomes. It was not executed, so no arm definitions, seed counts, equivalence margins, or results are reported as though they had been completed.

Any future threshold analysis must use separate reference seeds to fit and freeze \(T\), followed by independent intervention seeds. The number of seeds should be determined by a prespecified precision or equivalence analysis rather than retaining the original four-seed maximum rule.

Censoring must also be handled as partial information rather than assigning an effect of exactly 1.0. If a latency is observed, it is \(L=G-C\). If grokking has not occurred by the post-checkpoint horizon \(H\), then the observation is right-censored and supplies only

\[
L>H-C.
\]

If one fork is observed and the other is censored, this inequality may bound the latency contrast but does not produce a point estimate. Equivalence cannot be declared unless the entire contrast interval implied by censoring lies inside the prespecified equivalence region. If the interval extends outside that region, the outcome is inconclusive; if its entire feasible range lies outside, non-equivalence may be established. If both forks are censored, no finite latency contrast is identified without additional modeling assumptions. A survival-style analysis or explicitly interval-censored equivalence procedure should be prespecified before execution.

The planned runtime environment was CPU-only PyTorch using `float64`, one Torch thread, deterministic algorithms, and disabled CUDA and MPS backends. Workspace use was to remain below 1.8 GB, with a cleanup target of 1.5 GB. Exact Python, PyTorch, NumPy, operating-system, and dependency versions were not supplied. No code or environment lock file was supplied, so the claimed execution conditions cannot be reproduced or audited.

## Results

No empirical results were supplied. In particular, there are no complete per-seed records for the four planned seeds and no records from independent reference or evaluation seeds.

No `results.json` was produced. The following required quantities are unavailable:

- reference memorization and grokking outcomes for every attempted seed;
- reference grokking steps \(G_{\mathrm{ref},s}\);
- reference norm trajectories and norms at grokking;
- the fitted threshold \(T\);
- checkpoint eligibility outcomes, including seeds for which no checkpoint existed;
- selected checkpoint steps \(C_s\);
- checkpoint losses, accuracies, and norms;
- deterministic replay discrepancies;
- initial conceptual norm values and norm-doubling errors;
- intervention crossing steps \(X_s\);
- baseline and intervention training and test trajectories;
- baseline and intervention grokking steps;
- post-checkpoint grokking latencies;
- censoring times and censoring indicators;
- seed-level latency contrasts or bounded contrast intervals;
- uncertainty intervals or equivalence-analysis results;
- invariance, replay, crossing, grokking, reference, feasibility, and disk audit outcomes;
- software and dependency versions;
- code revision identifiers;
- maximum workspace measurements.

No compressed machine-readable curves or audit logs were supplied. No source code, package lock file, configuration file, checkpoint manifest, or reproduction instructions were supplied.

No figures were produced. The specified two-panel `result.png` is absent, so there are no accuracy or norm trajectories to inspect or interpret.

The original condition

\[
R_{\max}<0.10
\]

cannot be evaluated, and the corrected post-checkpoint latency effects cannot be evaluated either. No result can be reported as supported, refuted, equivalent, non-equivalent, or censored because the underlying observations do not exist in the supplied material.

The only available result is analytic rather than empirical: under the stated fork construction, the ordinary trainable parameters, gradients, optimizer states, logits, predictions, and grokking steps are invariant between forks. The externally scheduled conceptual norm and its threshold crossing may differ, but neither can influence optimization. Numerical runs would be useful only to confirm that the implementation satisfies this proof within floating-point tolerances.

Accordingly, the verdict remains **broken as an empirical study**. The work supplies neither empirical evidence for the stronger claim that actual parameter norm is causally irrelevant nor an executed test of the redesigned causal intervention. It supplies only a formal explanation of why the originally proposed fork experiment was predetermined.

## Limitations

The overriding limitation is the absence of empirical observations and reproducibility artifacts. No reference run, fork run, audit, trajectory, checkpoint, threshold, censoring record, codebase, environment specification, or machine-readable output can be verified. The failure point cannot be localized.

The original intervention altered only an externally tracked conceptual norm. It did not modify the ordinary parameter state used by the model, the gradients used by the optimizer, or the optimizer state. Its threshold crossing had no mechanism to affect training. The resulting equivalence therefore cannot be generalized to actual parameter-norm interventions.

The formal proof assumes that both forks execute the same deterministic operations on identical ordinary parameters and optimizer states. Numerical implementation errors, nondeterministic kernels, unintended aliasing, or accidentally including the external component in an update could violate those conditions. Such possibilities motivate implementation audits, but no audit records were supplied.

The original four-seed design was inadequate for a robust population-level conclusion. It included no uncertainty interval, equivalence test, or seed-level population model, and it based the aggregate decision on the maximum observed relative difference. Moreover, the same seeds were to be used to fit the threshold and test the intervention. Because no data are available, this cannot be repaired retrospectively. A future study must use disjoint reference and intervention seeds and justify its sample size prospectively.

Protocol feasibility was not established. There is no evidence concerning how often reference runs grok by 25,000 steps, how often memorization occurs, or how often checkpoints satisfy the test-accuracy, timing, and norm-bracketing constraints. A future feasibility phase must report every attempted seed, including failed runs and seeds without eligible checkpoints, rather than silently excluding them.

The original effect-size denominator used absolute grokking step rather than post-checkpoint latency. This could make a large change in remaining training time appear small when \(C_s\) is late. The revised latency definition addresses the conceptual problem, but no values can be calculated.

The original rule assigning \(R_s=1.0\) when exactly one fork was censored was arbitrary. Right censoring provides an inequality, not a measured effect. The revised interval or survival-style treatment cannot be applied because censoring times and outcomes were not supplied.

Even an executed redesign would remain specific to addition modulo \(23\), the stated training split, one multilayer-perceptron architecture, and the selected AdamW configuration unless replicated more broadly. No cross-modulus, cross-architecture, or cross-optimizer evidence is available.

Exact software versions are unknown. “PyTorch,” “NumPy,” CPU execution, and `float64` do not uniquely specify a reproducible environment. No code was supplied, and no machine-readable artifacts exist.

Finally, a complete bibliography was not included in the source material. The numbered citations [1]–[9] cannot be verified or expanded without inventing missing metadata. Consequently, novelty relative to prior work on scale symmetries, softmax-null directions, weight decay, optimizer dynamics, and grokking cannot be established from the supplied report.

## Follow-up questions

- Can the original null-space construction be retained strictly as an implementation negative control, with the behavioral equivalence established analytically and only a small numerical validation used to test the code?
- Can a feasibility study report every attempted reference seed, including non-grokking runs and runs without eligible checkpoints, before defining the main intervention sample?
- Can a norm threshold be fitted on dedicated reference seeds, frozen before analysis, and evaluated on disjoint intervention seeds?
- What seed count and equivalence margin are justified by a prospective precision or equivalence analysis using post-checkpoint grokking latency?
- How do function-preserving transformations of actual ReLU-network parameters affect grokking when initial logits are identical but the transformed parameters subsequently participate in optimization?
- Which outcomes are attributable to parameter norm itself, and which are attributable to transformed Adam moments, epsilon, blockwise effective learning rates, or decoupled weight decay?
- Can the redesigned study include separate arms that match checkpoint logits, transform or reset optimizer moments, and match or vary effective functional update sizes?
- Can censoring be analyzed using prespecified latency intervals or survival methods rather than replacing censored outcomes with arbitrary point values?
- Can complete per-seed trajectories, audit records, checkpoint and threshold values, censoring indicators, software versions, executable code, a flat `results.json`, compressed curves, and the two-panel `result.png` be released together?
- Can the missing bibliographic metadata for [1]–[9] be supplied so that the novelty claim can be evaluated against prior work on scale symmetries, softmax-null directions, weight decay, and grokking?
