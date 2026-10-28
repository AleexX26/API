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
