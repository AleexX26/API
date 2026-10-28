"""Bounded public discovery: robots, advertised Spanish sitemap, homepage.

No authentication, cookies, redirects, retries, API calls or recursive crawling.
"""
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.etree import ElementTree

ORIGIN = "https://print24.com"
AGENT = "Print24CatalogResearch/0.1"
LIMIT = 8_000_000


def spanish_url(value: str) -> bool:
    p = urlsplit(value)
    return (p.scheme == "https" and p.netloc == "print24.com"
            and (p.path == "/es" or p.path.startswith("/es/"))
            and not p.query and not p.fragment)


def allowed(robots: str, url: str) -> bool:
    """Evaluate wildcard group using longest match, including * and $.

    Stop on agent-specific groups or rate directives: requires policy review.
    """
    rules = []
    active = False
    path = urlsplit(url).path
    for line in robots.splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (s.strip() for s in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if value != "*":
                raise ValueError("Agent-specific robots policy requires review")
            active = True
        elif key in ("crawl-delay", "request-rate"):
            raise ValueError("Provider rate directive requires review")
        elif active and key in ("allow", "disallow") and value:
            end = value.endswith("$")
            pattern = value[:-1] if end else value
            expression = "^" + ".*".join(re.escape(x) for x in pattern.split("*")) + ("$" if end else "")
            if re.search(expression, path):
                rules.append((len(pattern.replace("*", "")), key == "allow"))
    if not active:
        raise ValueError("No wildcard robots group; review required")
    return max(rules)[1] if rules else True


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls: set[str] = set()

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                url = urljoin(ORIGIN + "/es", href)
                if spanish_url(url):
                    self.urls.add(url)


def sitemap_links(raw: bytes) -> tuple[str, list[str]]:
    root = ElementTree.fromstring(raw)
    kind = root.tag.rsplit("}", 1)[-1]
    if kind not in ("sitemapindex", "urlset"):
        raise ValueError("Unexpected sitemap document")
    urls = sorted({e.text.strip() for e in root.iter()
                   if e.tag.rsplit("}", 1)[-1] == "loc" and e.text and spanish_url(e.text.strip())})
    return kind, urls


class Redirected(ValueError):
    """A redirect that was not followed; callers decide whether it is fatal."""

    def __init__(self, code: int, location: str):
        super().__init__(f"Redirect {code}: stop for review")
        self.code, self.location = code, location


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Redirected(code, newurl)


def probe(output: Path) -> dict:
    # Fresh evidence directory prevents silent replacement of a previous run.
    output.mkdir(parents=True, exist_ok=False)
    manifest = {"started_at": datetime.now(timezone.utc).isoformat(),
                "authorization": "User confirmed authorization in chat on 2026-10-27",
                "status": "running", "requests": []}
    opener = build_opener(NoRedirect())

    def fetch(url: str, filename: str, expected: str) -> bytes:
        if manifest["requests"]:
            time.sleep(5)  # Conservative local setting, NOT a claimed provider limit.
        record = {"url": url, "file": filename}
        manifest["requests"].append(record)
        with opener.open(Request(url, headers={"User-Agent": AGENT}), timeout=25) as response:
            record["status"] = response.status
            content_type = response.headers.get("Content-Type", "")
            record["content_type"] = content_type
            raw = response.read(LIMIT + 1)
            if len(raw) > LIMIT:
                raise ValueError("Response exceeds evidence size limit")
            (output / filename).write_bytes(raw)
            record["sha256"] = hashlib.sha256(raw).hexdigest()
            if expected not in content_type.lower():
                raise ValueError("Unexpected content type; stop for review")
            return raw

    try:
        robots = fetch(ORIGIN + "/robots.txt", "robots.txt", "text/plain").decode("utf-8-sig")
        advertised = [line.split(":", 1)[1].strip() for line in robots.splitlines()
                      if line.lower().startswith("sitemap:")]
        spanish = [url for url in advertised if spanish_url(url)]
        if len(spanish) != 1:
            raise ValueError("Expected one advertised Spanish sitemap")
        sitemap = spanish[0]
        home = ORIGIN + "/es"
        if not allowed(robots, sitemap) or not allowed(robots, home):
            raise ValueError("robots.txt does not permit the probe")
        kind, urls = sitemap_links(fetch(sitemap, "sitemap.xml", "xml"))
        html = fetch(home, "homepage.html", "text/html").decode("utf-8")
        if any(marker in html.lower() for marker in ("cf-chl-", "verify you are human", "captcha")):
            raise ValueError("Possible access challenge; stop for manual review")
        parser = Links()
        parser.feed(html)
        manifest.update(status="success", sitemap_kind=kind, sitemap_links=urls,
                        homepage_links=sorted(parser.urls),
                        warning="Discovered URLs are candidates, not verified products or configurations")
    except Exception as exc:
        manifest.update(status="failed", error=str(exc))
        raise
    finally:
        (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    import argparse
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    result = probe(args.output)
    print(json.dumps({"status": result["status"], "sitemap_kind": result["sitemap_kind"],
                      "sitemap_links": len(result["sitemap_links"]),
                      "homepage_links": len(result["homepage_links"])}))
