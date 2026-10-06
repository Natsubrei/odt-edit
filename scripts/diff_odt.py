#!/usr/bin/env python3
"""Unified diff of two ODT bodies.
Usage: python3 diff_odt.py old.odt new.odt out.diff
"""
import sys, os, difflib
from paths import add_pylib, work
add_pylib()
from odt_text import extract

old, new, out = sys.argv[1], sys.argv[2], sys.argv[3]
tmp = work()
os.makedirs(tmp, exist_ok=True)
a_txt = os.path.join(tmp, "old.txt")
b_txt = os.path.join(tmp, "new.txt")
extract(old, a_txt)
extract(new, b_txt)

a = open(a_txt, encoding="utf-8").read().splitlines(keepends=True)
b = open(b_txt, encoding="utf-8").read().splitlines(keepends=True)
d = list(
    difflib.unified_diff(
        a,
        b,
        fromfile=f"{os.path.basename(old)} (body)",
        tofile=f"{os.path.basename(new)} (body)",
        n=2,
    )
)
parent = os.path.dirname(out)
if parent:
    os.makedirs(parent, exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    f.write("".join(d))
plus = sum(1 for l in d if l.startswith("+") and not l.startswith("+++"))
minus = sum(1 for l in d if l.startswith("-") and not l.startswith("---"))
hunks = sum(1 for l in d if l.startswith("@@"))
print(f"{out}: {hunks} hunks, +{plus}/-{minus} lines")
