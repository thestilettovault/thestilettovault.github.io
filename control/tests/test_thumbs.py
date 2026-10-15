# -*- coding: utf-8 -*-
import socket

import pytest

from control import thumbs


@pytest.mark.parametrize("slug", ["../secret", "a/../../b", "/abs", "a//b", "a\b", "..", "x?y"])
def test_bad_slugs(slug):
    assert not thumbs.valid_slug(slug)


def test_good_slug():
    assert thumbs.valid_slug("2026-10-01/some shoe-1")


def test_local_image_blocks_symlink_style_escape(tmp_path, monkeypatch):
    g = tmp_path / "GELEM"
    (g / "ok").mkdir(parents=True)
    (g / "ok" / "post_image.png").write_bytes(b"x")
    monkeypatch.setattr(thumbs, "GELEM", g)
    assert thumbs.local_image("ok") is not None
    assert thumbs.local_image("../GELEM/ok") is None


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/x", "http://localhost/x", "http://169.254.169.254/latest",
    "http://10.0.0.5/", "http://192.168.1.1/", "file:///etc/passwd", "ftp://example.com/", "javascript:alert(1)",
])
def test_private_or_non_http_urls_blocked(url):
    assert not thumbs.is_public_http_url(url)


def test_public_url_allowed(monkeypatch):
    monkeypatch.setattr(thumbs.socket, "getaddrinfo",
                        lambda *a, **k: [(socket.AF_INET, 1, 6, "", ("93.184.216.34", 443))])
    assert thumbs.is_public_http_url("https://example.com/p")


def test_og_image_never_fetches_private(monkeypatch):
    import requests
    called = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: called.append(a) or None)
    assert thumbs._og_image("http://127.0.0.1:8787/api/shutdown") is None
    assert not called
