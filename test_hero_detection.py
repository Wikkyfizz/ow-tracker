"""
Quick accuracy test for extract_heroes() against known ground truth.
Run: venv/Scripts/python.exe test_hero_detection.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from parser.icons import extract_heroes

INBOX = Path(r"E:\Claude stuff\OW screenshots")

GROUND_TRUTH = {
    "Overwatch_06W2CnsgI0": {
        "my":    ["Zarya", "Cassidy", "Tracer", "Kiriko", "Mizuki"],
        "enemy": ["Sigma", "Sierra", "Cassidy", "Mizuki", "Kiriko"],
    },
    "Overwatch_bMzBrYEn8M": {
        "my":    ["Zarya", "Sojourn", "Shion", "Kiriko", "Wuyang"],
        "enemy": ["Zarya", "Tracer", "Cassidy", "Wuyang", "Kiriko"],
    },
    "Overwatch_glEGeuSkaU": {
        "my":    ["Sigma", "Ashe", "Widowmaker", "Kiriko", "Ana"],
        "enemy": ["Sigma", "Shion", "Mei", "Kiriko", "Wuyang"],
    },
}

def _slug(name):
    import re
    return re.sub(r"[^a-z0-9]", "_", name.lower()).strip("_")

total, correct = 0, 0

for stem, truth in GROUND_TRUTH.items():
    img_path = str(INBOX / f"{stem}.png")
    result = extract_heroes(img_path)

    print(f"\n{'='*60}")
    print(f"  {stem}")
    print(f"{'='*60}")

    for team, label in (("my_heroes", "MY"), ("enemy_heroes", "EN")):
        team_key = "my" if team == "my_heroes" else "enemy"
        detected = result.get(team, []) if team == "my_heroes" else result.get("enemy_heroes", [])
        expected = truth[team_key]

        print(f"\n  {label} team:")
        for i, (det, exp) in enumerate(zip(detected, expected)):
            match = _slug(det) == _slug(exp)
            status = "OK" if match else "XX"
            score_info = ""
            if not match:
                score_info = f"  (expected {exp})"
            print(f"    {label}-{i+1}  {status}  {det or '(none)'}{score_info}")
            total += 1
            if match:
                correct += 1

    conf = result.get("confidence", 0)
    print(f"\n  Overall confidence: {conf:.2f}")
    if "warning" in result:
        print(f"  WARNING: {result['warning']}")

print(f"\n{'='*60}")
print(f"  TOTAL: {correct}/{total} correct  ({100*correct/total:.0f}%)")
print(f"{'='*60}")
