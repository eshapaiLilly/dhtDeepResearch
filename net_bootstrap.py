"""
net_bootstrap.py — make Python trust the corporate (Zscaler) TLS proxy.

IMPORT THIS FIRST, before anthropic / httpx / requests are used.

Carried over unchanged from the earlier dht_pipeline build — this is what
made Tavily/Anthropic gateway calls work through Lilly's Zscaler proxy.
See that build's FIXES_AND_RUN_GUIDE.md for the original diagnosis.
"""
import os


def enable_corporate_tls() -> str:
    """Return which strategy was used: 'truststore', 'ca-bundle:<path>', or 'none'."""
    try:
        import truststore
        truststore.inject_into_ssl()
        return "truststore"
    except Exception:
        pass

    ca = os.environ.get("LILLY_CA_BUNDLE")
    if ca and os.path.exists(ca):
        os.environ.setdefault("SSL_CERT_FILE", ca)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", ca)
        return f"ca-bundle:{ca}"

    return "none"


TLS_STRATEGY = enable_corporate_tls()