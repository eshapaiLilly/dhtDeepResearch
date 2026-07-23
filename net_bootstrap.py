"""
net_bootstrap.py — make Python trust the corporate (Zscaler) TLS proxy.

IMPORT THIS FIRST, before anthropic / httpx / requests are used.

Carried over unchanged from the earlier dht_pipeline build — this is what
made Tavily/Anthropic gateway calls work through Lilly's Zscaler proxy.
See that build's FIXES_AND_RUN_GUIDE.md for the original diagnosis.

MERGED_CA_BUNDLE (new)
-----------------------
truststore.inject_into_ssl() patches Python to verify against the OS-native
trust store instead of certifi's bundled public-root list — the right
thing when Zscaler is TLS-inspecting a connection and re-signing it with
the corporate root CA (which IS in the OS store on a Lilly-managed
machine, via IT policy), but it depends on that patch actually taking
effect, and on the corporate root actually being present in the OS store
truststore reads from.

Symptom that means it ISN'T working: two UNRELATED public hosts (different
orgs, different public CAs — e.g. www.ebi.ac.uk and api.semanticscholar.org)
both fail SSL verification with the IDENTICAL error, on an OS-trust-store
attempt AND a separate explicit-certifi attempt. If truststore had actually
engaged, those two attempts would use genuinely different trust roots and
would not fail identically. Identical failure on both is the signature of
"both attempts silently ran through certifi" — i.e. truststore never
took effect, and any host Zscaler is inspecting (re-signing with a private
corporate root that's in neither trust list we've tried) will always fail
this way, no matter how many times we retry.

MERGED_CA_BUNDLE fixes this the deterministic way instead of hoping
truststore's OS-store detection works: if LILLY_CA_BUNDLE (or an
auto-discovered corporate root, see below) points to an actual PEM file,
we concatenate it with certifi's public root list into ONE bundle and
expose its path here. live_clients.py uses this (when available) as its
verify= target — trusting BOTH publicly-signed hosts (via certifi) AND
Zscaler-intercepted hosts (via the corporate root) in a single pass,
rather than sequential guessing between two trust stores.

This requires an actual corporate root CA file. If you don't have one:
ask your security/IT team for "the Zscaler root CA certificate, PEM/Base-64
X.509 format" — most Zscaler-managed orgs already distribute this for
configuring other tools (git, docker, pip, etc.) the same way. On a Windows
machine you can also self-export it: Start -> "Manage user certificates" ->
Trusted Root Certification Authorities -> find the Zscaler entry -> Export
as "Base-64 encoded X.509 (.CER)", then point LILLY_CA_BUNDLE at that file
(rename to .pem, contents are identical).
"""
import os
from pathlib import Path


_TRUSTSTORE_ERROR: str | None = None


def _autodiscover_corporate_ca() -> str | None:
    """If LILLY_CA_BUNDLE isn't set, look for a Zscaler/corporate root PEM
    sitting next to this module. This is deliberate ergonomics: after the
    Copilot walk-through, most people end up with a `zscaler-root.pem` or
    `zscaler_root.pem` or `ZscalerRoot.cer` next to their pipeline code —
    but then have to remember to `export LILLY_CA_BUNDLE=...` in every new
    shell, and lose an hour when they forget. This finds those files
    automatically. LILLY_CA_BUNDLE still wins if it's set explicitly.

    Only matches conservative, unambiguous names to avoid picking up a
    random unrelated .pem — extend the tuple if your file is named
    something else.
    """
    here = Path(__file__).parent
    candidates = (
        "zscaler-root.pem", "zscaler_root.pem",
        "zscaler-root.cer", "zscaler_root.cer",
        "ZscalerRoot.pem", "ZscalerRoot.cer",
        "lilly-root.pem", "corporate-root.pem",
    )
    for name in candidates:
        p = here / name
        if p.exists():
            return str(p)
    return None


def _resolve_corporate_ca() -> str | None:
    """LILLY_CA_BUNDLE > auto-discovered PEM next to this module > None."""
    ca = os.environ.get("LILLY_CA_BUNDLE")
    if ca and os.path.exists(ca):
        return ca
    return _autodiscover_corporate_ca()


def _build_merged_ca_bundle(corp_path: str) -> str | None:
    """Concatenate certifi's public roots with the corporate root at
    corp_path into one PEM file, written once per process to the temp dir.
    Returns the merged path on success, None on failure. Called at import
    time from enable_corporate_tls() — the merged bundle is the artifact
    that actually goes into SSL_CERT_FILE / REQUESTS_CA_BUNDLE, so that
    both Zscaler-intercepted hosts (via the corporate root) AND publicly-
    signed hosts we weren't intercepting (via certifi) verify from the
    same trust root, not sequentially guessed between two.
    """
    try:
        import certifi
        import tempfile
        merged_path = os.path.join(tempfile.gettempdir(), "lilly_merged_ca_bundle.pem")
        with open(certifi.where(), "r", encoding="utf-8") as f:
            public_roots = f.read()
        with open(corp_path, "r", encoding="utf-8") as f:
            corp_root = f.read()
        with open(merged_path, "w", encoding="utf-8") as out:
            out.write(public_roots)
            out.write("\n")
            out.write(corp_root)
        return merged_path
    except Exception:
        return None


def enable_corporate_tls() -> tuple[str, str | None]:
    """Return (strategy, merged_bundle_path_or_None).

    strategy is one of:
      'truststore'       -> truststore.inject_into_ssl() succeeded; the OS
                            trust store is authoritative; merged bundle not
                            needed and not built.
      'ca-bundle:<path>' -> corporate root discovered (via LILLY_CA_BUNDLE
                            or auto-discovery); merged with certifi's roots
                            into one bundle, and SSL_CERT_FILE +
                            REQUESTS_CA_BUNDLE point at the MERGED bundle
                            (not the corporate root alone — pointing at
                            the corporate root alone would drop certifi's
                            public roots, breaking every non-intercepted host).
      'none'             -> neither path worked; see print_diagnostics().
    """
    global _TRUSTSTORE_ERROR
    try:
        import truststore
        truststore.inject_into_ssl()
        return "truststore", None
    except Exception as e:
        # Previously swallowed silently (`except Exception: pass`) — that
        # hid the actual reason truststore didn't activate (not installed?
        # raised on injection? something else?) from anyone debugging a
        # 'none' TLS_STRATEGY. Capture it instead so print_diagnostics()
        # can show it.
        _TRUSTSTORE_ERROR = f"{type(e).__name__}: {e}"

    corp_ca = _resolve_corporate_ca()
    if corp_ca:
        merged = _build_merged_ca_bundle(corp_ca)
        # Prefer the merged bundle for the env vars — that's what makes
        # BOTH intercepted and non-intercepted hosts verify in one pass.
        # Fall back to the corporate root alone only if the merge failed
        # (certifi missing, disk full, etc.); imperfect but strictly
        # better than reverting to certifi-only.
        chosen = merged or corp_ca
        # Unconditional assignment (not setdefault): on many managed systems
        # these env vars are pre-populated to the OS-wide CA file (e.g.
        # /etc/ssl/certs/ca-certificates.crt on Linux), and setdefault
        # would silently refuse to overwrite them — meaning our merged
        # bundle wouldn't actually take effect. The whole point of this
        # branch is to route BOTH httpx and requests through the merged
        # bundle we just built, so we assign.
        os.environ["SSL_CERT_FILE"] = chosen
        os.environ["REQUESTS_CA_BUNDLE"] = chosen
        return f"ca-bundle:{corp_ca}", merged

    return "none", None


TLS_STRATEGY, MERGED_CA_BUNDLE = enable_corporate_tls()


def print_diagnostics() -> None:
    """Run as `python -c "import net_bootstrap; net_bootstrap.print_diagnostics()"`
    to see, in one command, whether truststore actually activated and
    whether a corporate CA is available to merge. This is the fastest way
    to tell "truststore silently didn't engage" (TLS_STRATEGY == 'none' or
    unexpectedly 'truststore' but still failing on real Zscaler-intercepted
    hosts) apart from "I just don't have the corporate CA file yet"
    (MERGED_CA_BUNDLE is None)."""
    print(f"TLS_STRATEGY = {TLS_STRATEGY!r}")
    print(f"LILLY_CA_BUNDLE env var = {os.environ.get('LILLY_CA_BUNDLE')!r}")
    print(f"Auto-discovered corporate CA = {_autodiscover_corporate_ca()!r}")
    print(f"MERGED_CA_BUNDLE = {MERGED_CA_BUNDLE!r}")
    print(f"SSL_CERT_FILE = {os.environ.get('SSL_CERT_FILE')!r}")
    print(f"REQUESTS_CA_BUNDLE = {os.environ.get('REQUESTS_CA_BUNDLE')!r}")
    if TLS_STRATEGY == "none":
        if _TRUSTSTORE_ERROR is not None:
            print(f"\ntruststore did not activate — captured error: {_TRUSTSTORE_ERROR}")
            if "No module named" in _TRUSTSTORE_ERROR:
                print(
                    "-> the `truststore` package isn't installed in this "
                    "environment. Try: pip install truststore --break-system-packages "
                    "(or however this org's Python packages are normally installed), "
                    "then re-run this diagnostic."
                )
            else:
                print(
                    "-> `truststore` IS installed but raised on inject_into_ssl(). "
                    "This is worth investigating on its own, but either way the "
                    "LILLY_CA_BUNDLE path below works independently of truststore."
                )
        else:
            print("\n(no exception was captured — this shouldn't normally happen; "
                  "re-run and check for a stale .pyc/import issue)")
    if TLS_STRATEGY == "none" and MERGED_CA_BUNDLE is None:
        print(
            "\nNeither truststore nor a corporate CA bundle is active. "
            "Any host your Zscaler proxy TLS-inspects (re-signs with a "
            "private corporate root) will fail SSL verification no matter "
            "how many public CA bundles you retry with. Ask IT/security "
            "for the Zscaler root CA in PEM/Base-64 X.509 format, then set "
            "LILLY_CA_BUNDLE to that file's path and re-run."
        )