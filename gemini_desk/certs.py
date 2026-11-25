"""CA bundle for the tool subprocesses.

Many Windows PCs have antivirus or corporate proxies that re-sign HTTPS traffic with their own root certificate
(AVG, Avast, Kaspersky, Zscaler...). Windows trusts that root, but Python libraries that use the certifi bundle
(requests, curl_cffi, yfinance) do not, so every download fails with CERTIFICATE_VERIFY_FAILED.
This builds one bundle = certifi + the roots the operating system already trusts, and hands it to the tools.
It adds no trust the OS does not already have.
"""
import os
import ssl
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / ".tools" / "ca-bundle.pem"


def _certifi_pem():
    try:
        import certifi
        return Path(certifi.where()).read_text(encoding="ascii", errors="ignore")
    except ImportError:
        return ""


def bundle_path():
    """Path of a PEM bundle with certifi + OS roots (Windows), or None where it is not needed."""
    if os.name != "nt" or not hasattr(ssl, "enum_certificates"):
        return None
    if BUNDLE.exists() and BUNDLE.stat().st_size > 10_000:
        return str(BUNDLE)
    pems = [_certifi_pem()]
    seen = set()
    for store in ("ROOT", "CA"):
        try:
            for der, enc, trust in ssl.enum_certificates(store):
                if enc != "x509_asn" or der in seen:
                    continue
                if trust is not True and "1.3.6.1.5.5.7.3.1" not in (trust or ()):  # server-auth roots only
                    continue
                seen.add(der)
                pems.append(ssl.DER_cert_to_PEM_cert(der))
        except OSError:
            continue
    BUNDLE.parent.mkdir(parents=True, exist_ok=True)
    BUNDLE.write_text("\n".join(p for p in pems if p), encoding="ascii")
    return str(BUNDLE)


def env():
    p = bundle_path()
    return {"REQUESTS_CA_BUNDLE": p, "SSL_CERT_FILE": p, "CURL_CA_BUNDLE": p} if p else {}
