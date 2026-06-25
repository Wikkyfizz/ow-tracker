r"""
One-off: pull OW2 hero square icons from the Overwatch Fandom wiki into
parser/hero_icons/{slug}.png, where slug matches parser.icons._hero_slug.

Run: .\venv\Scripts\python.exe fetch_icons.py
"""
import re
import sqlite3
import unicodedata
from pathlib import Path

import httpx

API = "https://overwatch.fandom.com/api.php"
HEADERS = {"User-Agent": "ow-tracker-icon-fetch/1.0 (personal stat tracker)"}
ICONS_DIR = Path(__file__).parent / "parser" / "hero_icons"


def hero_slug(name: str) -> str:
    # Mirror parser.icons._hero_slug exactly.
    return re.sub(r"[^a-z0-9]", "_", name.lower())


def norm_key(name: str) -> str:
    # Accent-insensitive, case-insensitive, alphanumeric-only match key.
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", stripped.lower())


def db_heroes() -> list[str]:
    con = sqlite3.connect(Path(__file__).parent / "ow_tracker.db")
    names = [r[0] for r in con.execute("SELECT name FROM heroes")]
    con.close()
    return names


def category_icon_files() -> list[str]:
    params = {
        "action": "query", "list": "categorymembers",
        "cmtitle": "Category:Overwatch_2_hero_icons",
        "cmlimit": "500", "cmtype": "file", "format": "json",
    }
    r = httpx.get(API, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    members = [m["title"] for m in r.json()["query"]["categorymembers"]]
    return [m for m in members if m.startswith("File:Icon-")]


def image_urls(titles: list[str]) -> dict[str, str]:
    """Map File:title -> direct image URL, batching <=50 titles per request."""
    out: dict[str, str] = {}
    for i in range(0, len(titles), 50):
        batch = titles[i:i + 50]
        params = {
            "action": "query", "titles": "|".join(batch),
            "prop": "imageinfo", "iiprop": "url", "format": "json",
        }
        r = httpx.get(API, params=params, headers=HEADERS, timeout=30)
        r.raise_for_status()
        for page in r.json()["query"]["pages"].values():
            info = page.get("imageinfo")
            if info:
                out[page["title"]] = info[0]["url"]
    return out


def main() -> None:
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    heroes = db_heroes()
    icon_files = category_icon_files()

    # key -> File:title for available icons
    icon_by_key = {norm_key(t[len("File:Icon-"):].removesuffix(".png")): t for t in icon_files}

    matched: dict[str, str] = {}  # File:title -> destination slug
    missing: list[str] = []
    for hero in heroes:
        title = icon_by_key.get(norm_key(hero))
        if title:
            matched[title] = hero_slug(hero)
        else:
            missing.append(hero)

    urls = image_urls(list(matched.keys()))

    saved = 0
    with httpx.Client(headers=HEADERS, timeout=60, follow_redirects=True) as client:
        for title, slug in matched.items():
            url = urls.get(title)
            if not url:
                print(f"  ! no URL for {title}")
                continue
            resp = client.get(url)
            resp.raise_for_status()
            (ICONS_DIR / f"{slug}.png").write_bytes(resp.content)
            saved += 1
            print(f"  ok  {slug}.png  <-  {title}  ({len(resp.content)} bytes)")

    used = set(matched.keys())
    extras = [t[len("File:Icon-"):].removesuffix(".png") for t in icon_files if t not in used]

    print(f"\nSaved {saved}/{len(heroes)} hero icons to {ICONS_DIR}")
    if missing:
        print(f"MISSING (no icon found): {', '.join(missing)}")
    if extras:
        print(f"Skipped non-roster icons: {', '.join(sorted(extras))}")


if __name__ == "__main__":
    main()
