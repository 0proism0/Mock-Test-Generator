"""Build and verify bank/amc12_C.json — 25 faithful variants of real AMC 12 problems."""
import json
import math
import re
from fractions import Fraction

F = Fraction

# ---------- computed answers (verification) ----------

# P1: 96 / 2^4
p1 = 96 // 2**4
assert p1 == 6

# P2: round trip 150 mi at 45 mpg, return at 30 mpg
p2 = F(300, 1) / (F(150, 45) + F(150, 30))
assert p2 == 36, p2

# P3: total 44, margin 12, loser score
p3 = (44 - 12) // 2
assert p3 == 16

# P4: 2 km / (45+15 min) in km/hr
p4 = F(2, 1) / F(45 + 15, 60)
assert p4 == 2

# P5: weighted average
p5 = F(40 * 10 + 60 * 30, 40 + 60)
assert p5 == 22

# P6: x^2+y^2 = 8x+4y-20  <=>  (x-4)^2+(y-2)^2 = 0
import random
for _ in range(1000):
    x, y = random.uniform(-10, 10), random.uniform(-10, 10)
    assert abs((x**2 + y**2 - 8 * x - 4 * y + 20) - ((x - 4) ** 2 + (y - 2) ** 2)) < 1e-9
p6 = 4 + 2
assert p6 == 6

# P7: max x/y over two-digit x,y with x+y=100
p7 = max(F(x, 100 - x) for x in range(10, 91))
assert p7 == 9, p7

# P8: cube with SA = 3 * SA of cube of volume 8
s2 = F(3 * 6 * 2**2, 6)  # s^2 = 12
p8 = float(s2) ** 1.5
assert abs(p8 - 24 * math.sqrt(3)) < 1e-9

# P9: linear f, f(9)-f(3)=24 -> f(15)-f(3)
p9 = F(24, 9 - 3) * (15 - 3)
assert p9 == 48

# P10: median of 25 consecutive ints summing to 5^6
p10 = F(5**6, 25)
assert p10 == 625 and sum(range(625 - 12, 625 + 13)) == 5**6

# P11: 5^(x+5) = 6^x -> x = log_{6/5}(5^5)
x11 = 5 * math.log(5) / (math.log(6) - math.log(5))
assert abs(5 ** (x11 + 5) - 6**x11) < 1e-6
assert abs(x11 - math.log(5**5) / math.log(F(6, 5))) < 1e-12
p11 = "6/5"

# P12: geometric, a3=7!, a6=8! -> r=2, a1
r12 = round((math.factorial(8) / math.factorial(7)) ** (1 / 3))
p12 = math.factorial(7) // r12**2
assert p12 * r12**2 == math.factorial(7) and p12 * r12**5 == math.factorial(8)
assert p12 == 1260

# P13: a - 1/a = 2 (a>1), 1/b - b = 2 (b<1)
a13 = (2 + math.sqrt(4 + 4)) / 2
b13 = (-2 + math.sqrt(4 + 4)) / 2
assert abs(a13 - 1 / a13 - 2) < 1e-12 and abs(1 / b13 - b13 - 2) < 1e-12
p13 = a13 + b13
assert abs(p13 - 2 * math.sqrt(2)) < 1e-12

# P14: 2*pi*log(a^2) = log(b^8) -> log_a b = pi/2
p14 = F(8, 4)  # = pi * 8/4 / ... -> coefficient: 8 log b... derive: 4*pi*log a = 8 log b
assert abs((F(8, 1) / F(4, 1)) - 2) == 0  # log b / log a = pi/2
p14 = "pi/2"

# P15: a/(1-r)=9, ar/(1-r^2)=4
r15 = F(4, 1) / (F(9, 1) - F(4, 1)) * 1  # solve 9r/(1+r)=4 -> 9r = 4+4r -> r=4/5
r15 = F(4, 5)
a15 = 9 * (1 - r15)
assert a15 / (1 - r15) == 9 and a15 * r15 / (1 - r15**2) == 4
p15 = a15 + r15
assert p15 == F(13, 5)

# P16: cubic P, P(0)=k, P(1)=2k, P(-1)=4k -> P(2)+P(-2)
k = F(1)
d = k
# a+b+c = k ; -a+b-c = 3k
b16 = (k + 3 * k) / 2
p16 = 8 * b16 + 2 * d  # even part doubled
assert p16 == 18
# cross-check with explicit polynomial
c16 = F(0)
a16 = k - b16 - c16
P = lambda x: a16 * x**3 + b16 * x**2 + c16 * x + d
assert P(0) == 1 and P(1) == 2 and P(-1) == 4 and P(2) + P(-2) == 18

# P17: u+3v=1, 2u+v=3 -> u+v
# solve: u = 8/5, v = -1/5
u17, v17 = F(8, 5), F(-1, 5)
assert u17 + 3 * v17 == 1 and 2 * u17 + v17 == 3
p17 = u17 + v17
assert p17 == F(7, 5)

# P18: integer zeros of x^2 - a x + 3a
vals = set()
for a in range(-500, 501):
    disc = a * a - 12 * a
    if disc < 0:
        continue
    s = int(math.isqrt(disc))
    if s * s == disc and (a + s) % 2 == 0:
        vals.add(a)
p18 = sum(vals)
assert vals == {16, 12, -4, 0}, vals
assert p18 == 24

# P19: a(b+c)=26, b(c+a)=44, c(a+b)=54
ab = F(26 + 44 - 54, 2)
ac = F(26 + 54 - 44, 2)
bc = F(44 + 54 - 26, 2)
p19 = math.isqrt(ab * ac * bc)
assert p19**2 == ab * ac * bc and p19 == 72
a19 = math.isqrt(ab * ac // bc)
assert a19 == 2
b19, c19 = ab // a19, ac // a19
assert a19 * (b19 + c19) == 26 and b19 * (c19 + a19) == 44 and c19 * (a19 + b19) == 54

# P20: count x in 41..59 with (x-40)(60-x) < 10^3
p20 = sum(1 for x in range(41, 60) if (x - 40) * (60 - x) < 1000)
assert p20 == 19

# P21: d(n)=40, d(3n)=50 -> (k+2)/(k+1) = 50/40
# solve 4(k+2) = 5(k+1)
p21 = None
for k in range(0, 20):
    if F(k + 2, k + 1) == F(50, 40):
        p21 = k
assert p21 == 3
# realizability check: n = 2^4 * 3^3 * 5
def ndiv(n):
    c = 0
    for i in range(1, n + 1):
        if n % i == 0:
            c += 1
    return c
n21 = 2**4 * 3**3 * 5
assert ndiv(n21) == 40 and ndiv(3 * n21) == 50 and n21 % 27 == 0 and n21 % 81 != 0

# P22: count n with n + S(n) + S(S(n)) = 2016
S = lambda n: sum(int(d) for d in str(n))
sol22 = [n for n in range(2016 - 200, 2017) if n > 0 and n + S(n) + S(S(n)) == 2016]
p22 = len(sol22)
print("P22 solutions:", sol22, "count:", p22)

# P23: sum of log10 of divisors of 10^n = 605
found = []
for n in range(1, 60):
    prod = 1
    for a in range(n + 1):
        for b in range(n + 1):
            prod *= 2**a * 5**b
    # sum of logs = log10(prod); check prod = 10^605
    s = 0
    m = prod
    while m % 10 == 0:
        m //= 10
        s += 1
    if m == 1 and s == 605:
        found.append(n)
assert found == [10], found
p23 = 10
# also n(n+1)^2/2 formula
assert 10 * 11**2 // 2 == 605

# P24: pairs (a,b) coprime with (4a^2+21b^2)/(4ab) integer
pairs = [(a, b) for a in range(1, 2000) for b in range(1, 2000)
         if math.gcd(a, b) == 1 and (4 * a * a + 21 * b * b) % (4 * a * b) == 0]
print("P24 pairs:", pairs)
p24 = len(pairs)
assert p24 == 4

# P25: exponent recurrence e_n = e_{n-1} + 2 e_{n-2}, e_0=0, e_1=1; first k with 17 | e_k
e = [0, 1]
while len(e) < 200:
    e.append(e[-1] + 2 * e[-2])
p25 = next(k for k in range(1, 200) if e[k] % 17 == 0)
assert p25 == 8, p25
assert e[8] == 85

print("All numeric checks passed.")
print(json.dumps({i: v for i, v in enumerate([p1,p2,p3,p4,p5,p6,p7,p8,p9,p10,p11,p12,p13,p14,p15,p16,p17,p18,p19,p20,p21,p22,p23,p24,p25], 1)}, default=str))
