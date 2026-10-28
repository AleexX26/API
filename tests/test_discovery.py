import pytest
from app.collectors.discovery import Links, allowed, sitemap_links, spanish_url


def test_scope_and_deduplication():
    parser = Links()
    parser.feed('<a href="/es/productos">A</a><a href="/es/productos">B</a><a href="https://evil.test/es">X</a>')
    assert parser.urls == {"https://print24.com/es/productos"}
    for url in ("https://print24.com/es-x", "https://print24.com/es?session=1", "https://print24.com/es#x", "http://print24.com/es"):
        assert not spanish_url(url)


def test_robots_longest_wildcards_and_review():
    policy = 'User-agent: *\nAllow: /es\nDisallow: /es-\nDisallow: */freedesign/*'
    assert allowed(policy, "https://print24.com/es/product")
    assert not allowed(policy, "https://print24.com/es-other")
    assert not allowed(policy, "https://print24.com/es/freedesign/product")
    with pytest.raises(ValueError):
        allowed(policy + '\nCrawl-delay: 20', "https://print24.com/es")


def test_sitemap_types():
    kind, urls = sitemap_links(b'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://print24.com/es/a.xml</loc></sitemap></sitemapindex>')
    assert kind == "sitemapindex"
    assert urls == ["https://print24.com/es/a.xml"]
    with pytest.raises(ValueError):
        sitemap_links(b'<html/>')
