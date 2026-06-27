import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from parser.icons import extract_heroes

inbox = Path(r"E:\Claude stuff\OW screenshots")
stems = ["Overwatch_1R6DGlPdQ2", "Overwatch_4Zaakta4kE", "Overwatch_zRPTVNorq2"]

for stem in stems:
    r = extract_heroes(str(inbox / f"{stem}.png"))
    print(stem)
    for i, h in enumerate(r.get("my_heroes", [])):
        print(f"  MY-{i+1}  {h}")
    for i, h in enumerate(r.get("enemy_heroes", [])):
        print(f"  EN-{i+1}  {h}")
    print(f"  confidence: {r.get('confidence', 0):.2f}")
    if "warning" in r:
        print(f"  WARNING: {r['warning']}")
    print()
