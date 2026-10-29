"""Where is the collection? Prints what is stored per provider and how much of each sitemap is still pending.

Read-only: `python -m app.collectors.status`
"""
import sqlite3
from pathlib import Path

from app.collectors import onlineprinters, printai, tuskamisetas

ROOT = Path(__file__).resolve().parents[2]


def pending(provider: str, urls: list[str], seen: set[str]) -> int:
    return sum(1 for url in urls if url not in seen)


REASONS = {"Selected quantity not found": "su tabla de precios no se puede leer (calculadora vetada por su robots.txt)",
           "No Product data in page": "la página no trae datos de producto"}


def reason_text(error: str | None) -> str:
    error = error or ""
    if error in REASONS:
        return REASONS[error]
    if "no longer available" in error:
        return "la página ya no existe"
    if "differs from page" in error or "does not match" in error:
        return "los precios de su tabla no coinciden con los de la página"
    if "Gross price inconsistent" in error:
        return "el precio con IVA no cuadra con el neto"
    if "No quantity/price tiles" in error:
        return "la página no muestra tabla de cantidades y precios"
    return error[:60] or "motivo no anotado"


def table(root: Path = ROOT) -> list[dict]:
    """Per provider: pages read, failed (with reasons), pending of its sitemap, total and the date of the last reading."""
    db_path = root / "data/catalog.sqlite3"
    if not db_path.exists():
        return []
    db = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    cache = root / "data/cache"
    plan = {
        "tuskamisetas": tuskamisetas.sitemap_urls(cache / "tuskamisetas/sitemap-modelo.xml") if (cache / "tuskamisetas/sitemap-modelo.xml").exists() else [],
        "onlineprinters": onlineprinters.sitemap_urls(cache / "onlineprinters/products_sitemap.xml") if (cache / "onlineprinters/products_sitemap.xml").exists() else [],
        "printai": printai.sitemap_urls(cache / "printai/sitemap.xml") if (cache / "printai/sitemap.xml").exists() else [],
    }
    out = []
    try:
        for provider, urls in plan.items():
            rows = dict(db.execute("SELECT status, count(*) FROM supplier_pages WHERE provider=? GROUP BY status", (provider,)).fetchall())
            seen = {r[0] for r in db.execute("SELECT url FROM supplier_pages WHERE provider=?", (provider,))}
            reasons = {}
            for error, count in db.execute("SELECT error, count(*) FROM supplier_pages WHERE provider=? AND status='failed' GROUP BY error", (provider,)):
                key = reason_text(error)
                reasons[key] = reasons.get(key, 0) + count
            last = db.execute("SELECT max(fetched_at) FROM supplier_pages WHERE provider=?", (provider,)).fetchone()[0]
            out.append({"provider": provider, "ok": rows.get("ok", 0), "failed": rows.get("failed", 0), "pending": pending(provider, urls, seen),
                        "total": len(urls), "last": last, "reasons": reasons})
        ok = db.execute("SELECT count(*) FROM product_pages WHERE status='ok'").fetchone()[0]
        bad = db.execute("SELECT count(*) FROM product_pages WHERE status<>'ok'").fetchone()[0]
        last = db.execute("SELECT max(fetched_at) FROM product_pages").fetchone()[0]
        out.append({"provider": "print24", "ok": ok, "failed": bad, "pending": 0, "total": ok + bad, "last": last, "reasons": {}})
    except sqlite3.OperationalError:
        pass
    finally:
        db.close()
    return out


def main(root: Path = ROOT) -> None:
    rows = table(root)
    if not rows:
        print("No hay data/catalog.sqlite3 todavia (o no tiene todas las tablas).")
        return
    print(f"{'Proveedor':16}{'bien':>8}{'fallidas':>10}{'pendientes':>12}{'total':>8}")
    for r in rows:
        print(f"{r['provider']:16}{r['ok']:>8}{r['failed']:>10}{r['pending']:>12}{r['total']:>8}")
    print("\n'fallidas' = paginas retiradas, sin tabla de precios o que no cuadran; es normal que haya muchas.")


if __name__ == "__main__":
    main()
