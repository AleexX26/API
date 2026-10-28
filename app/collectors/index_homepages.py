"""One-time, bounded public navigation index. Never collects prices or accounts.

Run manually, not on user searches. Reuses the existing Print24 evidence.
"""
import json
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, unquote
from urllib.request import build_opener, Request

from app.collectors.discovery import NoRedirect, allowed
from app.services.workbench import PROVIDERS, normalize

ROOT = Path(__file__).resolve().parents[2]


def navigation_allowed(robots: str, url: str) -> bool:
    """Select applicable agent group; then use wildcard-aware rule matching."""
    groups = []
    agents, rules = [], []
    for line in robots.splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = [part.strip() for part in line.split(":", 1)]
        if key.lower() == "user-agent":
            if rules:
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(value.lower())
        elif key.lower() in ("allow", "disallow", "crawl-delay", "request-rate"):
            rules.append(f"{key}: {value}")
    if agents:
        groups.append((agents, rules))
    agent = "printworkbenchresearch"
    matched = [(max(len(a) for a in names if a != "*" and a in agent), rules)
               for names, rules in groups if any(a != "*" and a in agent for a in names)]
    if matched:
        longest = max(length for length, _ in matched)
        selected = [rules for length, rules in matched if length == longest]
    else:
        selected = [rules for names, rules in groups if "*" in names]
    return allowed("User-agent: *\n" + "\n".join(rule for rules in selected for rule in rules), url)


class Navigation(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base = base
        self.current = None
        self.text = []
        self.links = {}

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.current = dict(attrs).get("href")
            self.text = []

    def handle_data(self, data):
        if self.current is not None:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag != "a" or self.current is None:
            return
        p = urlsplit(urljoin(self.base, self.current))
        host = urlsplit(self.base).hostname.removeprefix("www.")
        if p.scheme == "https" and p.hostname and p.hostname.removeprefix("www.") == host and not p.query and not p.fragment and not p.username:
            url = urlunsplit((p.scheme, p.netloc, p.path, "", ""))
            title = " ".join(" ".join(self.text).split())
            if not title:
                title = unquote(p.path.rstrip("/").split("/")[-1]).replace("-", " ")
            if normalize(title) in ("a la oferta", "ver mas", "mostrar ahora", "pide ahora", "mas informacion"):
                title = unquote(p.path.rstrip("/").split("/")[-1]).replace("-", " ").capitalize()
            combined = normalize(url + " " + title)
            excluded = ("login", "logout", "password", "carrito", "shopping-cart", "inicia sesion", "registr", "privacy", "privacidad", "cookies", "contacto", "contactos", "terminos", "condiciones", "newsletter", "proteccion-de-datos", "account", "customercentre")
            if len(title) >= 3 and len(title) <= 160 and not any(word in combined for word in excluded):
                self.links.setdefault(url, title)
        self.current = None


def main(resume=False):
    dest = ROOT / "data/catalog_links.json"
    if dest.exists() and not resume:
        raise SystemExit("Index already exists; preserve evidence and review before refreshing")
    evidence = ROOT / "data/homepage-index"
    evidence.mkdir(exist_ok=resume)
    out = json.loads(dest.read_text(encoding="utf-8")) if resume else {"description": "Public navigation candidates, not a full product catalog", "providers": {}}
    opener = build_opener(NoRedirect())
    last_request = 0

    def get(url):
        nonlocal last_request
        time.sleep(max(0, 5 - (time.monotonic() - last_request)))
        last_request = time.monotonic()
        with opener.open(Request(url, headers={"User-Agent": "PrintWorkbenchResearch/0.1"}), timeout=20) as response:
            raw = response.read(8_000_001)
            if len(raw) > 8_000_000:
                raise ValueError("Response size limit")
            return raw.decode(response.headers.get_content_charset() or "utf-8")

    for provider in PROVIDERS:
        if resume and out["providers"].get(provider["id"], {}).get("status") == "indexed":
            continue
        record = {"source": provider["url"], "fetched_at": datetime.now(timezone.utc).isoformat(), "links": []}
        try:
            if provider["id"] == "print24":
                source = ROOT / "data/discovery-20261027-01"
                html = (source / "homepage.html").read_text(encoding="utf-8")
                record["fetched_at"] = json.loads((source / "manifest.json").read_text())["started_at"]
                record["evidence"] = str(source.relative_to(ROOT))
            else:
                p = urlsplit(provider["url"])
                robots_path = evidence / f'{provider["id"]}.robots.txt'
                robots = robots_path.read_text(encoding="utf-8") if resume and robots_path.exists() else get(f"{p.scheme}://{p.netloc}/robots.txt")
                if not robots_path.exists():
                    robots_path.write_text(robots, encoding="utf-8")
                if not navigation_allowed(robots, provider["url"]):
                    raise ValueError("Robots restriction; no homepage requested")
                html_path = evidence / f'{provider["id"]}.html'
                html = html_path.read_text(encoding="utf-8") if resume and html_path.exists() else get(provider["url"])
                if not html_path.exists():
                    html_path.write_text(html, encoding="utf-8")
                if any(marker in html.lower() for marker in ("cf-chl-", "verify you are human", "<title>captcha", "<title>just a moment")):
                    raise ValueError("Potential access challenge: no indexing")
            parser = Navigation(provider["url"])
            parser.feed(html)
            record.update(status="indexed", links=[{"title": title, "url": url} for url, title in sorted(parser.links.items())][:500])
        except Exception as exc:
            record.update(status="unavailable", error=str(exc))
        out["providers"][provider["id"]] = record
        dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f'{provider["name"]}: {record["status"]}, {len(record["links"])} links; {record.get("error", "")}', flush=True)


if __name__ == "__main__":
    import argparse
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--resume", action="store_true", help="Resume unavailable providers, reusing existing evidence")
    main(cli.parse_args().resume)
