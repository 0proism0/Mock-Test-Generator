# 难度标尺（1–5）——真实题目对照表

这是 `classifier/` 给每道题打 `difficulty.level` 用的标尺在**真实题目**上长什么样。
模型看的规则在 `classifier/prompts/classify.md`；算法与融合方案在 `SCHEMES.md`。

## 标尺五档

| 档 | 名字 | 判定标准 |
|---|---|---|
| 1 | 一步直取 | 套一个定义/公式就能出答案，不需要选择工具。 |
| 2 | 两步常规 | 两个标准步骤串起来，思路一眼可见，没有陷阱。 |
| 3 | 选对工具 / 2-3 步 | 需要想到该用哪个定理或做一个关键观察，然后常规推进。 |
| 4 | 多步综合 / 关键构造 | 需要非显然的关键一步（构造、配对、转化成熟悉模型），之后还有几步收尾。 |
| 5 | 压轴 / 非标准技巧 | 整个解法围绕一个非常规想法（Miquel、根轴共点、精妙不变量），且要求多块知识联动。 |

## 本次抽样分布

样本共 **63** 题：amc8 / amc10(v2) / amc12(v2) / aime 各若干，按原始卷题号定向取样。

| 档 | 题数 |
|---|---|
| 1 | 6 |
| 2 | 20 |
| 3 | 28 |
| 4 | 8 |
| 5 | 1 |

目标形状（SCHEMES.md 里的验收标准）是 1:2:3:3:1，即 L1/L5 各约 10%，L2/L3/L4 占主体。

---

## 每档的真实题目

### Level 1 — 一步直取（6 题）

**2024 AMC 8 Problem 1**  ·  score `1.14` · conf `0.74`

> What is the units digit of $$333{,}333-33{,}333-3{,}333-333-33-3?$$

- 主考点：`number_theory.remainders.modular_arithmetic`
- 附带标签：`number_theory.remainders.remainder_cycles`
- 模型理由：Only units digits matter: 3−3−3−3−3−3 = −12 ≡ 8 (mod 10), a single-step observation.

**2024 AMC 8 Problem 2**  ·  score `1.16` · conf `0.74`

> What is the value of this expression in decimal form? $$\frac{55}{11}+\frac{110}{55}+\frac{55}{1100}$$

- 主考点：`number_theory.divisibility.multiples_factors`
- 附带标签：`algebra.exponents.exponent_rules`
- 模型理由：Direct fraction simplification and decimal addition; one mechanical step per term.

**2016 AMC 8 Problem 1**  ·  score `1.14` · conf `0.76`

> The longest professional tennis match ever played lasted a total of $11$ hours and $5$ minutes. How many minutes was this?

- 主考点：`word_problems.calendar_time.date_counting`
- 模型理由：Single-step unit conversion: 11×60+5=665, no insight needed.

**2012 AMC 8 Problem 1**  ·  score `1.14` · conf `0.75`

> Rachelle uses 3 pounds of meat to make 8 hamburgers for her family. How many pounds of meat does she need to make 24 hamburgers for a neighbourhood picnic?

- 主考点：`word_problems.ratio_percent.ratio_allocation`
- 模型理由：Single-step proportion: 3 pounds per 8 burgers, so 24 burgers needs 3×3=9 pounds.


### Level 2 — 两步常规（20 题）

**2012 AMC 8 Problem 20**  ·  score `1.53` · conf `0.72`

> What is the correct ordering of the three numbers $\frac{5}{19}$, $\frac{7}{21}$, and $\frac{9}{23}$, in increasing order?

- 主考点：`algebra.equations.linear_quadratic`
- 附带标签：`number_theory.divisibility.multiples_factors`
- 模型理由：Direct fraction comparison via common denominator; one mechanical step.

**2023 AMC 8 Problem 6**  ·  score `1.89` · conf `0.67`

> The digits $2,0,2,$ and $3$ are placed in the expression below, one digit per box. What is the maximum possible value of the expression?

- 主考点：`algebra.exponents.exponent_rules`
- 附带标签：`methods.case_analysis.position_cases`
- 模型理由：Recognize a^0=1 and test a few digit placements to maximize the product; straightforward case check.

**2016 AMC 8 Problem 13**  ·  score `2.04` · conf `0.72`

> Two different numbers are randomly selected from the set $\{ -3, -1, 0, 2, 4\}$ and multiplied together. What is the probability that the product is $0$?

- 主考点：`probability.classical_probability`
- 附带标签：`combinatorics.permutations_combinations`
- 模型理由：Two routine steps: count total pairs via C(5,2), then count pairs containing 0; standard classical probability.

**2003 AMC 10B Problem 3**  ·  score `2.12` · conf `0.74`

> The sum of $5$ consecutive even integers is $4$ less than the sum of the first $8$ consecutive odd counting numbers. What is the smallest of the even integers?

- 主考点：`algebra.sequences.arithmetic_sequence`
- 附带标签：`algebra.equations.linear_quadratic`
- 模型理由：Apply sum-of-first-n-odds = n², then solve a one-variable linear equation; two routine steps.


### Level 3 — 选对工具 / 2-3 步（28 题）

**2014 AIME I Problem 9**  ·  score `3.41` · conf `0.64`

> Let $x_1<x_2<x_3$ be the three real roots of the equation $\sqrt{2024}\,x^3-4049x^2+2=0$. Find $x_2(x_1+x_3)$.

- 主考点：`algebra.identities.factoring`
- 附带标签：`algebra.equations.roots_and_coefficients`
- 模型理由：Key step is spotting the linear factor √n·x−1 to factor the cubic; once factored, reading off roots is immediate.

**2010 AIME I Problem 2**  ·  score `2.58` · conf `0.67`

> Find the remainder when $9 \times 99 \times 999 \times \cdots \times \underbrace{99\cdots9}_{\text{999 9's}}$ is divided by $1000$.

- 主考点：`number_theory.remainders.modular_arithmetic`
- 附带标签：`number_theory.remainders.remainder_cycles`, `methods.enumeration_patterns.small_case_testing`
- 模型理由：Recognize all 3+-nine numbers are ≡ -1 mod 1000, count them, multiply; standard modular pattern.

**2007 AMC 10B Problem 7**  ·  score `2.86` · conf `0.67`

> All sides of the convex pentagon $ABCDE$ are of equal length, and $\angle A= \angle B = 90^\circ.$ What is the degree measure of $\angle E?$

- 主考点：`plane_geometry.quadrilaterals`
- 附带标签：`plane_geometry.triangle_basics`, `methods.construction`
- 模型理由：Key insight is recognizing the pentagon decomposes into a square plus an equilateral triangle; two-step geometric identification.

**2012 AMC 12B Problem 11**  ·  score `3.13` · conf `0.67`

> In the equation below, $A$ and $B$ are consecutive positive integers, and $A$ , $B$ , and $A+B$ represent number bases: \[132_A+43_B=69_{A+B}.\] What is $A+B$ ?

- 主考点：`number_theory.bases.base_conversion`
- 附带标签：`algebra.equations.linear_quadratic`, `number_theory.parity.consecutive_integers`
- 模型理由：Converting variable-base numbers to base 10 and solving the resulting quadratic with a case split on consecutive integers.


### Level 4 — 多步综合 / 关键构造（8 题）

**2021 AMC 12B Problem 21**  ·  score `4.01` · conf `0.64`

> Let $S$ be the sum of all positive real numbers $x$ for which \[x^{2^{\sqrt2}}=\sqrt2^{2^x}.\] Which of the following statements is true?

- 主考点：`algebra.exponents.exponential_equations`
- 附带标签：`algebra.functions.function_intersections`, `methods.enumeration_patterns.small_case_testing`
- 模型理由：Key insight is the double-log transformation revealing a concave-vs-line intersection, then bounding the second root by testing x=2 and x=4.

**2020 AMC 12A Problem 19**  ·  score `3.96` · conf `0.66`

> There exists a unique strictly increasing sequence of nonnegative integers $a_1 < a_2 < … < a_k$ such that$$ \frac{2^{289}+1}{2^{17}+1} = 2^{a_1} + 2^{a_2} + … + 2^{a_k}. $$What is $k?$

- 主考点：`number_theory.bases.binary`
- 附带标签：`algebra.identities.factoring`, `methods.enumeration_patterns.pattern_induction`
- 模型理由：Key insight: factor x^17+1, then recognize each pair 2^a−2^b yields a block of 17 ones in binary, giving 8×17+1=137 ones.

**2003 AIME I Problem 13**  ·  score `4.16` · conf `0.66`

> Let $N$ be the number of positive integers that are less than or equal to $2003$ and whose base-$2$ representation has more $1$'s than $0$'s. Find the remainder when $N$ is divided by $1000$.

- 主考点：`number_theory.bases.binary`
- 附带标签：`combinatorics.permutations_combinations.combinations`, `methods.symmetry.permutation_symmetry`
- 模型理由：Requires binomial coefficient counting via Pascal's triangle symmetry plus a non-obvious boundary correction for 2003 < 2047.

**2025 AMC 12B Problem 21**  ·  score `4.01` · conf `0.67`

> Two non-congruent triangles have the same area. Each triangle has sides of length $8$ and $9$, and the third side of each triangle has integer length. What is the sum of the lengths of the third sides?

- 主考点：`plane_geometry.trigonometry.law_of_cosines`
- 附带标签：`plane_geometry.triangle_area`, `number_theory.squares.perfect_square_test`
- 模型理由：Key observation that equal area with fixed sides implies supplementary angles, then Law of Cosines and integer solving chain together.


### Level 5 — 压轴 / 非标准技巧（1 题）

**2016 AIME I Problem 15**  ·  score `4.86` · conf `0.72`

> Circles $\omega_1$ and $\omega_2$ intersect at points $X$ and $Y$. Line $\ell$ is tangent to $\omega_1$ and $\omega_2$ at $A$ and $B$, respectively, with line $AB$ closer to point $X$ than to $Y$. Circle $\omega$ passes through $A$ and $B$ intersecting $\omega_1$ again at $D \neq A$ and intersecting $\omega_2$ again at $C \neq B$. The three points $C$, $Y$, $D$ are collinear, $XC = 67$, $XY = 47$, and $XD = 37$. Find $AB^2$.

- 主考点：`plane_geometry.circle_metrics.power_of_a_point`
- 附带标签：`plane_geometry.circles_and_angles.inscribed_angle`, `plane_geometry.similarity.similar_triangles`
- 模型理由：Requires radical axis concurrency, Miquel's theorem, and similar-triangle setup—AIME finale-level synthesis.


---

## 怎么用这张表给我反馈

觉得某题定错档了，直接一句话点名即可，例如：

```
2012 AMC 8 P20 应该是 1，不是 2
2024 AIME I P5 应该是 4
```

我会把这些改写成 `prompts/classify.md` 里的 few-shot 锚点（每档 2–3 题），
再重跑一遍这批题验证档位是否对齐。锚点比改文字描述有效得多——模型对例子的响应远比对形容词敏感。

## 已知偏差（需要你判断）

- **L2 偏胖、L5 偏瘦**：AIME 前 6 题大多落在 L3，AMC8 后段题落在 L2。可能是标尺“一步/两步”的刻画对 AMC8 偏宽、对 AIME 偏紧。
- **L5 只有 AIME 压轴**：AMC10/12 的最后一题目前最多到 L4。如果认为 AMC12 P25 也该有 L5 的题，需要放宽 L5 的定义。
- **L4 偏少（8 题）**：介于“关键观察”和“非常规技巧”之间的题，模型倾向判 L3。

