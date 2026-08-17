"""Build bank/amc10_C.json with 25 faithful variants, verifying each answer by computation."""
import json, math
from fractions import Fraction

V = []  # variants

def add(position, source, question, choices, answer, solution, computed):
    assert answer in choices, position
    # computed value must equal the choice text marked correct (checked manually per type)
    V.append({
        "position": position,
        "source": source,
        "question": question,
        "choices": choices,
        "answer": answer,
        "solution": solution,
        "_computed": str(computed),
    })

# ---- Pos 1: source 2016 AMC 10A P1: (11!-10!)/9! -> variant (13!-12!)/11!
c1 = (math.factorial(13) - math.factorial(12)) // math.factorial(11)
add(1, "2016 AMC 10A Problem 1",
    "What is the value of $$\\dfrac{13!-12!}{11!}?$$",
    {"A": "120", "B": "132", "C": "144", "D": "156", "E": "168"},
    "C",
    "$\\dfrac{13!-12!}{11!}=\\dfrac{12!(13-1)}{11!}=\\dfrac{12\\cdot 12!}{11!}=12\\cdot 12=144$.",
    c1)
assert c1 == 144

# ---- Pos 2: source 2016 AMC 10A P2: 10^x * 100^{2x} = 1000^5 -> variant
# solve 10^x * 100^x = 1000^4  => 10^{3x} = 10^{12}
c2 = Fraction(3 * 4, 3)
add(2, "2016 AMC 10A Problem 2",
    "For what value of $x$ does $10^{x}\\cdot 100^{x}=1000^{4}$?",
    {"A": "4", "B": "3", "C": "6", "D": "8", "E": "12"},
    "A",
    "$10^{x}\\cdot 100^{x}=10^x\\cdot 10^{2x}=10^{3x}$ and $1000^4=10^{12}$, so $3x=12$ and $x=4$.",
    c2)
assert c2 == 4

# ---- Pos 3: source 2005 AMC 10A P3 -> 5x+13=3 and bx-15=-3
x3 = Fraction(3 - 13, 5)
b3 = Fraction(-3 + 15, 1) / x3
add(3, "2005 AMC 10A Problem 3",
    "The equations $5x + 13 = 3$ and $bx - 15 = -3$ have the same solution $x$. What is the value of $b$?",
    {"A": "-3", "B": "-4", "C": "-5", "D": "-6", "E": "-8"},
    "D",
    "From $5x+13=3$ we get $x=-2$. Substituting into $bx-15=-3$ gives $-2b=12$, so $b=-6$.",
    b3)
assert b3 == -6

# ---- Pos 4: source 2004 AMC 10A P4: |x-1|=|x-2| -> |x-2|=|x-5|
c4 = Fraction(2 + 5, 2)
add(4, "2004 AMC 10A Problem 4",
    "What is the value of $x$ if $|x-2|=|x-5|$?",
    {"A": "3", "B": "\\frac{7}{2}", "C": "4", "D": "\\frac{9}{2}", "E": "5"},
    "B",
    "The equation says $x$ is equidistant from $2$ and $5$, so $x$ is their midpoint: $x=\\frac{2+5}{2}=\\frac{7}{2}$.",
    c4)
assert c4 == Fraction(7, 2)

# ---- Pos 5: source 2017 AMC 10A P5 -> sum is 7 times product
c5 = Fraction(7, 1)
add(5, "2017 AMC 10A Problem 5",
    "The sum of two nonzero real numbers is $7$ times their product. What is the sum of the reciprocals of the two numbers?",
    {"A": "\\frac{1}{7}", "B": "\\frac{2}{7}", "C": "\\frac{7}{2}", "D": "7", "E": "14"},
    "D",
    "If $x+y=7xy$, then $\\frac{1}{x}+\\frac{1}{y}=\\frac{x+y}{xy}=\\frac{7xy}{xy}=7$.",
    c5)

# ---- Pos 6: source 2015 AMC 10A P6 -> sum is 7 times difference
# x+y = 7(x-y) => 8y = 6x => x/y = 4/3
c6 = Fraction(7 + 1, 7 - 1)
add(6, "2015 AMC 10A Problem 6",
    "The sum of two positive numbers is $7$ times their difference. What is the ratio of the larger number to the smaller number?",
    {"A": "\\frac{4}{3}", "B": "\\frac{5}{4}", "C": "\\frac{6}{5}", "D": "\\frac{7}{6}", "E": "\\frac{8}{7}"},
    "A",
    "Let $x>y$. Then $x+y=7(x-y)$, so $8y=6x$ and $\\frac{x}{y}=\\frac{8}{6}=\\frac{4}{3}$.",
    c6)
assert c6 == Fraction(4, 3)

# ---- Pos 7: source 2015 AMC 10A P7 -> arithmetic sequence 11,15,...,83
c7 = len(list(range(11, 84, 4)))
add(7, "2015 AMC 10A Problem 7",
    "How many terms are in the arithmetic sequence $11$, $15$, $19$, $\\dotsc$, $79$, $83$?",
    {"A": "17", "B": "18", "C": "19", "D": "20", "E": "21"},
    "C",
    "The common difference is $4$, so the number of terms is $\\frac{83-11}{4}+1=18+1=19$.",
    c7)
assert c7 == 19

# ---- Pos 8: source 2012 AMC 10A P8 -> pair sums 14, 19, 21
s = (14 + 19 + 21) // 2
nums = sorted([s - 14, s - 19, s - 21])
c8 = nums[1]
add(8, "2012 AMC 10A Problem 8",
    "The sums of three whole numbers taken in pairs are $14$, $19$, and $21$. What is the middle number?",
    {"A": "5", "B": "6", "C": "7", "D": "8", "E": "9"},
    "D",
    "If the numbers are $a<b<c$, then $a+b=14$, $a+c=19$, $b+c=21$. Adding gives $a+b+c=27$, so $c=13$, $b=8$, $a=6$. The middle number is $8$.",
    c8)
assert nums == [6, 8, 13] and c8 == 8

# ---- Pos 9: source 2006 AMC 10A P9 -> consecutive positive integer sets summing to 45
def consec_sets(N):
    cnt = 0
    k = 2
    while k * (k + 1) // 2 <= N:
        # k(2a+k-1)/2 = N, a>=1
        if (2 * N) % k == 0:
            t = (2 * N) // k - k + 1
            if t > 0 and t % 2 == 0:
                cnt += 1
        k += 1
    return cnt
c9 = consec_sets(45)
add(9, "2006 AMC 10A Problem 9",
    "How many sets of two or more consecutive positive integers have a sum of $45$?",
    {"A": "4", "B": "5", "C": "6", "D": "7", "E": "8"},
    "B",
    "The sets are $22+23$, $14+15+16$, $7+8+9+10+11$, $5+6+7+8+9+10$, and $1+2+\\cdots+9$: five sets in all.",
    c9)
assert c9 == 5

# ---- Pos 10: source 2012 AMC 10B P10 -> M/8 = 8/N, so MN = 64
c10 = sum(1 for d in range(1, 65) if 64 % d == 0)
add(10, "2012 AMC 10B Problem 10",
    "How many ordered pairs of positive integers $(M,N)$ satisfy the equation $\\frac{M}{8}=\\frac{8}{N}$?",
    {"A": "3", "B": "4", "C": "5", "D": "6", "E": "7"},
    "E",
    "Cross-multiplying gives $MN=64$. Each positive divisor of $64$ gives a valid $M$ (with $N=64/M$), and $64=2^6$ has $7$ divisors.",
    c10)
assert c10 == 7

# ---- Pos 11: source 2013 AMC 10B P11 -> x^2+y^2 = 14x-4y-53
# (x-7)^2 + (y-2)^2 = 49+4-53 = 0
c11 = 7 + 2
add(11, "2013 AMC 10B Problem 11",
    "Real numbers $x$ and $y$ satisfy the equation $x^2+y^2=14x-4y-53$. What is $x+y$?",
    {"A": "9", "B": "10", "C": "11", "D": "12", "E": "13"},
    "A",
    "Completing the square: $(x-7)^2+(y-2)^2=49+4-53=0$, so $x=7$ and $y=2$, giving $x+y=9$.",
    c11)

# ---- Pos 12: source 2016 AMC 10B P12 -> set {1,...,6}
from math import comb
c12 = Fraction(1, 1) - Fraction(comb(3, 2), comb(6, 2))
add(12, "2016 AMC 10B Problem 12",
    "Two different numbers are selected at random from $\\{1, 2, 3, 4, 5, 6\\}$ and multiplied together. What is the probability that the product is even?",
    {"A": "\\frac{2}{3}", "B": "\\frac{11}{15}", "C": "\\frac{4}{5}", "D": "\\frac{13}{15}", "E": "\\frac{14}{15}"},
    "C",
    "The product is odd only when both numbers are odd. There are $\\binom{3}{2}=3$ odd-odd pairs out of $\\binom{6}{2}=15$ pairs, so the probability of an even product is $1-\\frac{3}{15}=\\frac{4}{5}$.",
    c12)
assert c12 == Fraction(4, 5)

# ---- Pos 13: source 2004 AMC 10A P13 -> 15 men, 4 women each; each woman 3 men
c13 = Fraction(15 * 4, 3)
add(13, "2004 AMC 10A Problem 13",
    "At a party, each man danced with exactly four women and each woman danced with exactly three men. Fifteen men attended the party. How many women attended the party?",
    {"A": "12", "B": "15", "C": "18", "D": "20", "E": "24"},
    "D",
    "Counting dance pairs two ways: $15\\cdot 4 = 3w$, so $w=\\frac{60}{3}=20$ women.",
    c13)
assert c13 == 20

# ---- Pos 14: source 2002 AMC 10A P14 -> x^2 - 68x + k = 0, prime roots
def is_prime(n):
    if n < 2: return False
    for i in range(2, int(n ** 0.5) + 1):
        if n % i == 0: return False
    return True
ks = set()
for p in range(2, 68):
    q = 68 - p
    if is_prime(p) and is_prime(q):
        ks.add(p * q)
c14 = len(ks)
add(14, "2002 AMC 10A Problem 14",
    "Both roots of the quadratic equation $x^2 - 68x + k = 0$ are prime numbers. The number of possible values of $k$ is",
    {"A": "1", "B": "2", "C": "3", "D": "4", "E": "more than 4"},
    "B",
    "The roots are primes $p$ and $q$ with $p+q=68$. Checking even/odd: one prime could be $2$ (giving $66$, not prime), so both are odd. The prime pairs summing to $68$ are $(7,61)$ and $(31,37)$, giving $k=427$ or $k=1147$: two values.",
    c14)
assert c14 == 2

# ---- Pos 15: source 2003 AMC 10A P15 -> set {1..90}, divisible by 2 not 3
cnt15 = sum(1 for n in range(1, 91) if n % 2 == 0 and n % 3 != 0)
c15 = Fraction(cnt15, 90)
add(15, "2003 AMC 10A Problem 15",
    "What is the probability that an integer in the set $\\{1,2,3,\\ldots,90\\}$ is divisible by $2$ and not divisible by $3$?",
    {"A": "\\frac{1}{6}", "B": "\\frac{2}{9}", "C": "\\frac{4}{15}", "D": "\\frac{3}{10}", "E": "\\frac{1}{3}"},
    "E",
    "There are $45$ even numbers in the set, and $\\frac{90}{6}=15$ multiples of $6$ to exclude, leaving $30$. The probability is $\\frac{30}{90}=\\frac{1}{3}$.",
    c15)
assert c15 == Fraction(1, 3)

# ---- Pos 16: source 2003 AMC 10A P16 -> units digit of 19^2019
c16 = pow(19, 2019, 10)
add(16, "2003 AMC 10A Problem 16",
    "What is the units digit of $19^{2019}$?",
    {"A": "9", "B": "1", "C": "3", "D": "5", "E": "7"},
    "A",
    "The units digit of powers of $19$ alternates $9,1,9,1,\\ldots$ Since $2019$ is odd, the units digit is $9$.",
    c16)
assert c16 == 9

# ---- Pos 17: source 2007 AMC 10A P17 -> 48m = n^3, minimize m+n
best = None
for n in range(1, 100):
    if (n ** 3) % 48 == 0:
        m = n ** 3 // 48
        if best is None or m + n < best[0]:
            best = (m + n, m, n)
c17 = best[0]
add(17, "2007 AMC 10A Problem 17",
    "Suppose that $m$ and $n$ are positive integers such that $48m = n^{3}$. What is the minimum possible value of $m + n$?",
    {"A": "24", "B": "36", "C": "48", "D": "60", "E": "72"},
    "C",
    "Since $48=2^4\\cdot 3$, for $n^3$ to be a multiple of $48$ the smallest $n$ is $2^2\\cdot 3=12$. Then $m=\\frac{12^3}{48}=36$, and $m+n=48$.",
    c17)
assert best == (48, 36, 12)

# ---- Pos 18: source 2008 AMC 10A P18 -> perimeter 30, area 30
sol18 = None
for a in range(1, 30):
    for b in range(a, 30):
        c2v = a * a + b * b
        cv = math.isqrt(c2v)
        if cv * cv == c2v and a + b + cv == 30 and a * b == 60:
            sol18 = (a, b, cv)
c18 = sol18[2]
add(18, "2008 AMC 10A Problem 18",
    "A right triangle has perimeter $30$ and area $30$. What is the length of its hypotenuse?",
    {"A": "5", "B": "10", "C": "12", "D": "12.5", "E": "13"},
    "E",
    "With legs $a,b$ and hypotenuse $c$: $ab=60$ and $a+b=30-c$. Squaring, $a^2+2ab+b^2=(30-c)^2$, so $c^2+120=900-60c+c^2$, giving $c=13$ (the $5$-$12$-$13$ triangle).",
    c18)
assert sol18 == (5, 12, 13)

# ---- Pos 19: source 2002 AMC 10B P19 -> first 100 sum 300, next 100 sum 500
c19 = Fraction(500 - 300, 100 * 100)
add(19, "2002 AMC 10B Problem 19",
    "Suppose that $\\{a_n\\}$ is an arithmetic sequence with $$a_1+a_2+\\cdots+a_{100}=300 \\text{ and } a_{101}+a_{102}+\\cdots+a_{200}=500.$$ What is the value of $a_2 - a_1$?",
    {"A": "\\frac{1}{100}", "B": "\\frac{1}{50}", "C": "\\frac{1}{25}", "D": "\\frac{1}{10}", "E": "2"},
    "B",
    "Each term of the second block is $100d$ more than the corresponding term of the first block, where $d=a_2-a_1$. Thus $500-300=100\\cdot(100d)$, so $d=\\frac{200}{10000}=\\frac{1}{50}$.",
    c19)
assert c19 == Fraction(1, 50)

# ---- Pos 20: source 2007 AMC 10A P20 -> a + a^-1 = 5, find a^4 + a^-4
c20 = (5 ** 2 - 2) ** 2 - 2
add(20, "2007 AMC 10A Problem 20",
    "Suppose that the number $a$ satisfies the equation $5 = a + a^{-1}$. What is the value of $a^{4} + a^{-4}$?",
    {"A": "123", "B": "323", "C": "523", "D": "525", "E": "527"},
    "E",
    "Squaring: $a^2+a^{-2}=25-2=23$. Squaring again: $a^4+a^{-4}=23^2-2=529-2=527$.",
    c20)
assert c20 == 527

# ---- Pos 21: source 2006 AMC 10A P21 -> four-digit integers with at least one digit 7
c21 = sum(1 for n in range(1000, 10000) if '7' in str(n))
add(21, "2006 AMC 10A Problem 21",
    "How many four-digit positive integers have at least one digit that is a $7$?",
    {"A": "3168", "B": "3240", "C": "3402", "D": "4131", "E": "5832"},
    "A",
    "Complementary counting: there are $9000$ four-digit integers. Those with no digit $7$ number $8\\cdot 9\\cdot 9\\cdot 9=5832$. So the answer is $9000-5832=3168$.",
    c21)
assert c21 == 3168

# ---- Pos 22: source 2005 AMC 10A P22 -> 1500 smallest multiples of 4 and of 6
S = {4 * i for i in range(1, 1501)}
T = {6 * i for i in range(1, 1501)}
c22 = len(S & T)
add(22, "2005 AMC 10A Problem 22",
    "Let $S$ be the set of the $1500$ smallest positive multiples of $4$, and let $T$ be the set of the $1500$ smallest positive multiples of $6$. How many elements are common to $S$ and $T$?",
    {"A": "250", "B": "375", "C": "500", "D": "750", "E": "1000"},
    "C",
    "The common elements are the multiples of $\\text{lcm}(4,6)=12$ up to $4\\cdot 1500=6000$ (the largest element of $S$). There are $\\frac{6000}{12}=500$ of them.",
    c22)
assert c22 == 500

# ---- Pos 23: source 2007 AMC 10A P23 -> squares differ by 192
pairs = [(m, n) for m in range(1, 200) for n in range(1, m + 1) if m * m - n * n == 192]
c23 = len(pairs)
add(23, "2007 AMC 10A Problem 23",
    "How many ordered pairs $(m,n)$ of positive integers, with $m \\ge n$, have the property that their squares differ by $192$?",
    {"A": "2", "B": "3", "C": "4", "D": "5", "E": "6"},
    "D",
    "We need $(m-n)(m+n)=192$ with both factors even. The even factor pairs of $192$ are $(2,96),(4,48),(6,32),(8,24),(12,16)$, each giving positive integers $m,n$: five pairs.",
    c23)
assert c23 == 5

# ---- Pos 24: source 2004 AMC 10A P24 -> f(1)=1, f(2n)=n f(n); f(2^50)
f = {1: 1}
for k in range(1, 51):
    f[2 ** k] = 2 ** (k - 1) * f[2 ** (k - 1)]
c24 = f[2 ** 50]
add(24, "2004 AMC 10A Problem 24",
    "Let $f$ be a function with the following properties: (i) $f(1) = 1$, and (ii) $f(2n) = n \\cdot f(n)$ for any positive integer $n$. What is the value of $f(2^{50})$?",
    {"A": "2^{50}", "B": "2^{1225}", "C": "2^{1250}", "D": "2^{1275}", "E": "2^{2500}"},
    "B",
    "$f(2^{50})=2^{49}\\cdot 2^{48}\\cdots 2^0\\cdot f(1)=2^{0+1+\\cdots+49}=2^{1225}$.",
    f"2^{c24.bit_length()-1}" if c24 & (c24 - 1) == 0 else c24)
assert c24 == 2 ** 1225

# ---- Pos 25: source 2001 AMC 10 P25 -> <=2004, multiples of 3 or 4 but not 5
c25 = sum(1 for n in range(1, 2005) if (n % 3 == 0 or n % 4 == 0) and n % 5 != 0)
add(25, "2001 AMC 10 Problem 25",
    "How many positive integers not exceeding $2004$ are multiples of $3$ or $4$ but not $5$?",
    {"A": "768", "B": "782", "C": "792", "D": "800", "E": "802"},
    "E",
    "Multiples of $3$ or $4$: $668+501-167=1002$. Among these, the multiples of $5$ are the multiples of $15$ or $20$: $133+100-33=200$. The answer is $1002-200=802$.",
    c25)
assert c25 == 802

# ---- Assemble ----
variants = [{k: v for k, v in v.items() if k != "_computed"} for v in V]
doc = {"competition": "AMC 10", "set": "C", "variants": variants}
with open("bank/amc10_C.json", "w") as fh:
    json.dump(doc, fh, indent=2)

from collections import Counter
print("letters:", Counter(v["answer"] for v in variants))
print("entries:", len(variants))
for v in V:
    print(v["position"], v["source"], v["answer"], "computed:", v["_computed"])
print("WROTE bank/amc10_C.json")
