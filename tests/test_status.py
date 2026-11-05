from app.collectors import offers, status


def test_status_reports_counts_and_pending(tmp_path, capsys):
    (tmp_path / "data/cache/printai").mkdir(parents=True)
    (tmp_path / "data/cache/printai/sitemap.xml").write_text(
        "<urlset><url><loc>https://www.printai.es/flyers/</loc></url><url><loc>https://www.printai.es/tarjetas/</loc></url>"
        "<url><loc>https://www.printai.es/fr/flyers/</loc></url></urlset>", encoding="utf-8")
    db = offers.connect(tmp_path / "data/catalog.sqlite3")
    db.executescript("CREATE TABLE product_pages (url TEXT, status TEXT);")
    offers.record_page(db, "printai", "https://www.printai.es/flyers/", "2026-10-27", "ok", 1, None)
    db.close()
    status.main(tmp_path)
    lines = {line.split()[0]: line.split()[1:] for line in capsys.readouterr().out.splitlines() if line and line.split()[0] in ("printai", "tuskamisetas")}
    assert lines["printai"] == ["1", "0", "1", "2"]  # 1 ok, 0 failed, 1 pending, 2 Spanish pages in the sitemap (the /fr/ one is ignored)
    assert lines["tuskamisetas"] == ["0", "0", "0", "0"]


def test_status_without_database(tmp_path, capsys):
    status.main(tmp_path)
    assert "No hay data/catalog.sqlite3" in capsys.readouterr().out


def test_status_also_shows_truyol_and_our_shop(tmp_path):
    from app.collectors import laimprentadeinternet as shop, truyol
    (tmp_path / "data").mkdir()
    db = offers.connect(tmp_path / "data/catalog.sqlite3")
    db.executescript("CREATE TABLE product_pages (url TEXT, status TEXT, fetched_at TEXT);")
    row = {"quantity": 100, "kind": "total", "price": "10", "currency": "EUR", "tax": "net", "shipping": "included", "scope": "t"}
    offers.replace_offers(db, "truyol", truyol.CARDS + "#a", "T", [row], "2026-11-04")
    offers.replace_offers(db, "laimprentadeinternet", shop.PAGES[0] + "#tarifa-x", "N", [row], "2026-11-05")
    offers.record_page(db, "laimprentadeinternet", "https://laimprentadeinternet.com/lonas/", "2026-11-05", "failed", 0, shop.LINK_NOTE)
    db.close()
    rows = {r["provider"]: r for r in status.table(tmp_path)}
    assert {"truyol", "laimprentadeinternet", "print24"} <= set(rows)
    ours = rows["laimprentadeinternet"]
    assert (ours["ok"], ours["failed"]) == (1, 1) and ours["pending"] == len(shop.PAGES) - 1  # the pages still to be read show as pending
    assert ours["last"] == "2026-11-05" and any("solo enlace" in reason for reason in ours["reasons"])
    assert (rows["truyol"]["ok"], rows["truyol"]["pending"]) == (1, 10)  # 11 planned pages (10 cards + flyers), 1 read
