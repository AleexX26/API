"""Local-only CLI. No outbound provider requests."""
import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from app.parsers.product_page import default_configuration
from app.services.importer import connect, import_matrix


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/catalog.sqlite3")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db")
    imp = commands.add_parser("import-matrix")
    imp.add_argument("matrix", type=Path)
    imp.add_argument("context", type=Path)
    page = commands.add_parser("import-page", help="import the default configuration of a saved product page")
    page.add_argument("html", type=Path)
    page.add_argument("--url", required=True, help="page URL the file was downloaded from")
    exp = commands.add_parser("export")
    exp.add_argument("output", type=Path)
    exp.add_argument("--format", choices=["json", "csv"], default="json")
    commands.add_parser("status")
    args = parser.parse_args()
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    db = connect(args.db)
    try:
        if args.command == "import-matrix":
            cid = import_matrix(db, args.matrix.read_text(encoding="utf-8"),
                                json.loads(args.context.read_text(encoding="utf-8")), source=str(args.matrix))
            print(json.dumps({"event": "import_success", "configuration_id": cid}))
        elif args.command == "import-page":
            observed = datetime.fromtimestamp(args.html.stat().st_mtime, timezone.utc)
            matrix, context = default_configuration(args.html.read_text(encoding="utf-8"), url=args.url, observed_at=observed)
            cid = import_matrix(db, matrix, context, source=args.url)
            print(json.dumps({"event": "import_success", "configuration_id": cid}))
        elif args.command == "export":
            cursor = db.execute("SELECT p.*, c.country,c.currency,c.account_scope,c.canonical_json, q.source_id AS source_quantity_id,q.value AS quantity_value,s.source_id AS delivery_type FROM prices p JOIN configurations c ON c.id=p.configuration_id JOIN quantities q ON q.id=p.quantity_id JOIN shipping_options s ON s.id=p.shipping_option_id")
            rows = [dict(r) for r in cursor]
            args.output.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation avoids accidentally replacing an existing export.
            with args.output.open("x", encoding="utf-8", newline="") as handle:
                if args.format == "json":
                    json.dump(rows, handle, ensure_ascii=False, indent=2)
                else:
                    writer = csv.DictWriter(handle, fieldnames=[c[0] for c in cursor.description])
                    writer.writeheader()
                    writer.writerows(rows)
        elif args.command == "status":
            counts = {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                      for t in ("products", "configurations", "prices", "price_history", "sync_errors")}
            counts["monthly_scheduler"] = "not_implemented"
            print(json.dumps(counts))
    finally:
        db.close()


if __name__ == "__main__":
    main()
