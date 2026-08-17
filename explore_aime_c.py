"""Exploration/verification for AIME set C variants."""
from fractions import Fraction
from math import gcd, isqrt, comb
from itertools import permutations

def digitsum(n): return sum(int(d) for d in str(n))

# ---------- POS 1: 2019 AIME I P1 (sum of repdigit terms) ----------
def pos1(K):
    N = sum(10**k - 1 for k in range(1, K+1))
    return digitsum(N)
print("P1 real (321):", pos1(321), "expect 342")
print("P1 variant (331):", pos1(331))

# ---------- POS 2: 2017 AIME I P2 (same remainder triples) ----------
def solve_triple(a, b, c):
    # find all m such that a,b,c mod m are all equal to a positive r
    sols = []
    for m in range(1, max(a,b,c)+1):
        r = a % m
        if r > 0 and b % m == r and c % m == r:
            sols.append((m, r))
    return sols
print("P2 real:", solve_triple(702,787,855), solve_triple(412,722,815))
t1 = solve_triple(715, 791, 886)   # diffs 76,95 gcd 19
t2 = solve_triple(436, 746, 839)   # diffs 310,93 gcd 31
print("P2 variant:", t1, t2)
(m, r), = t1
(n, s), = t2
assert r != s
print("P2 answer:", m+n+r+s)

# ---------- POS 3: 1986 AIME P3 (tan sums) ----------
def pos3(s, c):
    # tanx+tany=s, cotx+coty=c -> tanx tany = s/c ; tan(x+y)=s/(1-s/c)
    p = Fraction(s, c)
    return Fraction(s, 1) / (1 - p)
print("P3 real:", pos3(25,30), "expect 150")
print("P3 variant:", pos3(35,42))

# ---------- POS 4: 2020 AIME I P4 (last four digits) ----------
def pos4(Y):
    divs = [k for k in range(1, Y+1) if Y % k == 0]
    return sum(digitsum(10000*k + Y) for k in divs)
print("P4 real (2020):", pos4(2020), "expect 93")
print("P4 variant (2024):", pos4(2024))

# ---------- POS 5: 2016 AIME I P5 (reading book) ----------
def pos5(P, T):
    sols = []
    for d in range(2, P+1):
        if (2*P) % d == 0 and (2*T) % d == 0:
            n2 = 2*P//d - d + 1
            t2 = 2*T//d - d + 1
            if n2 > 0 and t2 > 0 and n2 % 2 == 0 and t2 % 2 == 0:
                sols.append((d, n2//2, t2//2))
    return sols
print("P5 real:", pos5(374,319), "expect n+t=53")
print("P5 variant:", pos5(481,416))

# ---------- POS 6: 2014 AIME I P6 (two parabolas) ----------
def pos6_solve(A, B):
    """y=3(x-h)^2+j y-int A, integer x-ints; y=2(x-h)^2+k y-int B. find all h."""
    cands = set()
    # A = 3(h^2 - p^2) -> h^2 - p^2 = A/3
    if A % 3: return None
    T = A // 3
    for d1 in range(1, isqrt(T)+1):
        if T % d1 == 0:
            d2 = T // d1
            if (d1+d2) % 2 == 0:
                h = (d1+d2)//2; p = (d2-d1)//2
                if p >= 1 and h-p >= 1:  # positive x-intercepts
                    cands.add(h)
    if B % 2: return None
    good = []
    U = B // 2
    for h in cands:
        q2 = h*h - U
        if q2 >= 1:
            q = isqrt(q2)
            if q*q == q2 and h-q >= 1:
                good.append(h)
    return good
print("P6 real:", pos6_solve(2013, 2014), "expect [36]")
found6 = []
for h in range(28, 46):
    for p in range(1, h-1):
        A = 3*(h*h - p*p)
        if not (1900 <= A <= 3200): continue
        for q in range(1, h-1):
            B = 2*(h*h - q*q)
            if not (1900 <= B <= 3200): continue
            if A == B: continue
            sol = pos6_solve(A, B)
            if sol == [h]:
                found6.append((A, B, h, p, q))
print("P6 variant candidates:", found6[:8])

# ---------- POS 7: 2019 AIME I P7 (log gcd/lcm system) ----------
def pos7(A, B):
    # per-prime exponent equations: u+2min(u,v)=A, v+2max(u,v)=B
    sols = []
    for u in range(0, 1000):
        for v in range(0, 1000):
            if u + 2*min(u,v) == A and v + 2*max(u,v) == B:
                sols.append((u,v))
    return sols
print("P7 real:", pos7(60,570), "expect [(20,190)] -> 3*40+2*380=880")
u, v = pos7(63, 600)[0]
print("P7 variant exponents:", (u,v), "answer:", 3*(2*u) + 2*(2*v))

# ---------- POS 8: 2019 AIME I P8 (sin^10+cos^10) ----------
def s10(u): return 1 - 5*u + 5*u*u
def s12(u): return 1 - 6*u + 9*u*u - 2*u*u*u
u8 = Fraction(2,9)
val10 = s10(u8); val12 = s12(u8)
print("P8 variant: sin^10+cos^10 =", val10, "; sin^12+cos^12 =", val12, "answer:", val12.numerator + val12.denominator)
# sanity real: u=1/6
print("P8 real check:", s10(Fraction(1,6)), s12(Fraction(1,6)), "(expect 11/36, 13/54 -> 67)")
# direct numeric check with actual x
import math
a2 = (1 + math.sqrt(1-4*2/9))/2  # sin^2 x
x = math.asin(math.sqrt(a2))
print("P8 numeric:", math.sin(x)**10 + math.cos(x)**10, math.sin(x)**12 + math.cos(x)**12)

# ---------- POS 9: 2016 AIME II P9 (arith+geom) ----------
def pos9_solutions(C1, C2, rmax=50, kmax=30, dmax=2000):
    sols = []
    for r in range(2, rmax):
        for k in range(3, kmax):
            if r**(k-2) > 10**9: break
            # (k-2)d = C1-1 - r^(k-2); kd = C2-1 - r^k
            num1 = C1 - 1 - r**(k-2)
            num2 = C2 - 1 - r**k
            if num1 <= 0 or num2 <= 0: continue
            if num1 % (k-2) == 0 and num2 % k == 0:
                d1 = num1//(k-2); d2 = num2//k
                if d1 == d2:
                    ck = 1 + (k-1)*d1 + r**(k-1)
                    sols.append((r,k,d1,ck))
    return sols
print("P9 real:", pos9_solutions(100,1000), "expect c_k=262")
# search variants: choose r,k,d, derive C1,C2 near (100,1000), check uniqueness
for (r,k,d) in [(3,6,45),(2,7,15),(3,5,150),(4,4,140),(2,8,7),(5,4,60),(2,6,30),(3,6,44)]:
    C1 = 1 + (k-2)*d + r**(k-2)
    C2 = 1 + k*d + r**k
    if C2 > 1200 or C1 >= C2: continue
    sols = pos9_solutions(C1, C2)
    if len(sols) == 1:
        print("P9 variant candidate: C1=%d C2=%d -> unique sol r=%d k=%d d=%d c_k=%d" % (C1,C2,r,k,d,sols[0][3]))
    else:
        print("P9 candidate C1=%d C2=%d NOT unique:" % (C1,C2), sols)

# ---------- POS 10: 2016 AIME I P10 (geom/arith alternating) ----------
def pos10(a13):
    # a13 = c*(7+t)^2 with c squarefree; find all (c,t), compute a1 = c*(t+1)^2
    sols = []
    for s in range(8, isqrt(a13)+1):
        if a13 % (s*s) == 0:
            c = a13 // (s*s)
            # c squarefree?
            sf = all(c % (q*q) != 0 for q in range(2, isqrt(c)+1))
            if sf:
                t = s - 7
                sols.append((c, t, c*(t+1)**2))
    return sols
print("P10 real (2016):", pos10(2016), "expect a1=504")
print("P10 variant (2160):", pos10(2160))
# build sequence and verify conditions
def pos10_verify(c, t, terms=13):
    o = [c*(k+t)**2 for k in range(1, 9)]  # odd terms o_1..o_8
    a = [None]*15
    for k in range(1, 8):
        a[2*k-1] = o[k-1]
        a[2*k] = isqrt(o[k-1]*o[k])
    assert all(a[i] is not None and a[i] < a[i+1] for i in range(1, 13))
    for k in range(1, 7):
        assert a[2*k]**2 == a[2*k-1]*a[2*k+1]           # geometric
        assert 2*a[2*k+1] == a[2*k] + a[2*k+2]           # arithmetic
    return a[1], a[13]
print("P10 verify:", pos10_verify(15, 5))

# ---------- POS 11: 2017 AIME I P11 (3x3 medians) ----------
def pos11(target):
    cnt = 0
    for perm in permutations(range(1,10)):
        meds = sorted([sorted(perm[0:3])[1], sorted(perm[3:6])[1], sorted(perm[6:9])[1]])[1]
        if meds == target:
            cnt += 1
    return cnt
print("P11 real (m=5):", pos11(5), "expect ...360 (Q mod 1000 = 360)")
print("P11 variant (m=6):", pos11(6) % 1000)

# ---------- POS 12: 2014 AIME I P12 (disjoint ranges) ----------
def pos12(n):
    from itertools import product
    funcs = list(product(range(n), repeat=n))
    from collections import Counter
    rangecount = Counter()
    for f in funcs:
        mask = 0
        for v in set(f): mask |= 1 << v
        rangecount[mask] += 1
    tot = 0
    for m1, c1 in rangecount.items():
        for m2, c2 in rangecount.items():
            if m1 & m2 == 0:
                tot += c1*c2
    p = Fraction(tot, n**(2*n))
    return tot, p
tot4, p4 = pos12(4)
print("P12 real n=4:", tot4, p4, "expect m=453")
tot5, p5 = pos12(5)
print("P12 variant n=5:", tot5, p5, "m =", p5.numerator, "m+n =", p5.numerator + p5.denominator)

# ---------- POS 13: 2017 AIME II P13 (isosceles in n-gon) ----------
def f_iso(n):
    f = n * ((n-1)//2)
    if n % 3 == 0: f -= 2*(n//3)
    return f
# sanity check formula by direct count for small n
def f_iso_brute(n):
    from itertools import combinations
    cnt = 0
    for tri in combinations(range(n), 3):
        d = [(tri[(i+1)%3]-tri[i]) % n for i in range(3)]
        arcs = tuple(sorted([min(x, n-x) for x in [(tri[1]-tri[0])%n, (tri[2]-tri[1])%n, (tri[0]-tri[2])%n]]))
        # chord lengths equal iff min-arc equal
        if len(set(arcs)) <= 2:
            cnt += 1
    return cnt
for n in range(3, 15):
    assert f_iso(n) == f_iso_brute(n), (n, f_iso(n), f_iso_brute(n))
print("P13 formula verified by brute force n=3..14")
def pos13(D, nmax=4000):
    sols = [n for n in range(3, nmax) if f_iso(n+1) - f_iso(n) == D]
    return sols, sum(sols)
print("P13 real D=78:", pos13(78), "expect sum 245")
for D in [64, 80, 84, 90, 96, 60, 70, 72]:
    sols, s = pos13(D)
    if 0 < s <= 999:
        print("P13 variant D=%d:" % D, sols, "sum", s)

# ---------- POS 14: 2019 AIME I P14 (least odd prime factor of b^8+1) ----------
def pos14(b, plimit=100000):
    # sieve primes
    sieve = [True]*(plimit+1)
    for i in range(2, isqrt(plimit)+1):
        if sieve[i]:
            for j in range(i*i, plimit+1, i): sieve[j] = False
    for p in range(3, plimit+1):
        if sieve[p] and pow(b, 8, p) == p-1:
            return p
    return None
print("P14 real b=2019:", pos14(2019), "expect 97")
for b in [2021, 2023, 2025, 2027, 2017]:
    print("P14 b=%d:" % b, pos14(b))

# ---------- POS 15: 2021 AIME II P15 (f/g ratio) ----------
def f15(n):
    s = isqrt(n)
    if s*s < n: s += 1
    return (s*s - n) + s
def g15(n):
    r = isqrt(n)
    if r*r < n: r += 1
    while (r*r - n) % 2 != 0:
        r += 1
    return (r*r - n) + r
def pos15(a, b, nmax=3000):
    for n in range(1, nmax):
        if Fraction(f15(n), g15(n)) == Fraction(a, b):
            return n
    return None
print("P15 real 4/7:", pos15(4,7), "expect 258")
for (a,b) in [(5,8),(3,5),(5,7),(4,9),(2,3),(3,7),(5,9),(2,5)]:
    print("P15 ratio %d/%d:" % (a,b), pos15(a,b))
