"""Where is the collection? Prints what is stored per provider and how much of each sitemap is still pending.

Read-only: `python -m app.collectors.status`
"""
import sqlite3
from pathlib import Path

from app.collectors import onlineprinters, printai, tuskamisetas

ROOT = Path(__file__).resolve().parents[2]


def pending(provider: str, urls: list[str], seen: set[str]) -> int:
    return sum(1 for url in urls if url not in seen)


def main(root: Path = ROOT) -> None:
    db_path = root / "data/catalog.sqlite3"
    if not db_path.exists():
        print("No hay data/catalog.sqlite3 todavia.")
        return
    db = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    cache = root / "data/cache"
    plan = {
        "tuskamisetas": tuskamisetas.sitemap_urls(cache / "tuskamisetas/sitemap-modelo.xml") if (cache / "tuskamisetas/sitemap-modelo.xml").exists() else [],
        "onlineprinters": onlineprinters.sitemap_urls(cache / "onlineprinters/products_sitemap.xml") if (cache / "onlineprinters/products_sitemap.xml").exists() else [],
        "printai": printai.sitemap_urls(cache / "printai/sitemap.xml") if (cache / "printai/sitemap.xml").exists() else [],
    }
    print(f"{'Proveedor':16}{'bien':>8}{'fallidas':>10}{'pendientes':>12}{'total':>8}")
    try:
        for provider, urls in plan.items():
            rows = dict(db.execute("SELECT status, count(*) FROM supplier_pages WHERE provider=? GROUP BY status", (provider,)).fetchall())
            seen = {r[0] for r in db.execute("SELECT url FROM supplier_pages WHERE provider=?", (provider,))}
            print(f"{provider:16}{rows.get('ok', 0):>8}{rows.get('failed', 0):>10}{pending(provider, urls, seen):>12}{len(urls):>8}")
        ok = db.execute("SELECT count(*) FROM product_pages WHERE status='ok'").fetchone()[0]
        bad = db.execute("SELECT count(*) FROM product_pages WHERE status<>'ok'").fetchone()[0]
        print(f"{'print24':16}{ok:>8}{bad:>10}{0:>12}{ok + bad:>8}")
    except sqlite3.OperationalError as exc:
        print("La base de datos aun no tiene todas las tablas:", exc)
    print("\n'fallidas' = paginas retiradas, sin tabla de precios o que no cuadran; es normal que haya muchas.")


if __name__ == "__main__":
    main()
