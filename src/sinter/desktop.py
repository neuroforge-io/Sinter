"""Packaged entry point with an interpreter and a browser-based local interface.

--self-test exercises the installed application without external requests.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import os
import platform
import ssl
import struct
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from . import __version__, casebooks, workbench
from .server import make_server


def account_runtime_test() -> dict:
    """Verify frozen RS256 signing, JWKS parsing and rejection entirely offline."""
    available = (
        importlib.util.find_spec("jwt") is not None
        and importlib.util.find_spec("cryptography") is not None
    )
    if not available:
        return {"account_auth_bundled": False}
    import cffi
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    from .accounts import AUTHORITY, AccountError, AccountManager

    ffi = cffi.FFI()
    ffi.cdef("typedef unsigned char sinter_account_byte;")
    if ffi.sizeof("sinter_account_byte") != 1:
        raise RuntimeError("Bundled account verification dependencies are incomplete.")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = jwt.PyJWK.from_json(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    claims = {
        "iss": AUTHORITY,
        "aud": "sinter-package-test",
        "sub": "offline-package-fixture",
        "exp": int(time.time()) + 120,
        "nonce": "offline-package-nonce",
    }
    token = jwt.encode(
        claims, key, algorithm="RS256", headers={"kid": "offline-package-key"}
    )
    verified = jwt.decode(
        token,
        public.key,
        algorithms=["RS256"],
        issuer=claims["iss"],
        audience=claims["aud"],
    )
    if verified != claims:
        raise RuntimeError(
            "Bundled account identity verification returned wrong claims."
        )
    with tempfile.TemporaryDirectory(prefix="sinter-auth-runtime-") as directory:
        manager = AccountManager(directory)
        try:
            jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
            jwk.update({"kid": "offline-package-key", "use": "sig", "alg": "RS256"})
            manager._jwks = {"keys": [jwk]}
            manager._jwks_at = time.monotonic()
            if (
                manager._verify_identity(token, claims["aud"], nonce=claims["nonce"])
                != claims
            ):
                raise RuntimeError("Bundled Sinter identity verification failed.")
            wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            forged = jwt.encode(
                claims,
                wrong_key,
                algorithm="RS256",
                headers={"kid": "offline-package-key"},
            )
            try:
                manager._verify_identity(forged, claims["aud"], nonce=claims["nonce"])
            except AccountError:
                pass
            else:
                raise RuntimeError(
                    "Bundled account verification accepted an invalid signature."
                )
        finally:
            manager.close()
    return {
        "account_auth_bundled": True,
        "account_auth_dependencies": {
            name: importlib.metadata.version(name)
            for name in ("PyJWT", "cryptography", "cffi", "pycparser")
            + (("typing_extensions",) if sys.version_info < (3, 11) else ())
        },
    }


def self_test(destination: str) -> int:
    receipt = {
        "schema": "sinter-native-test/v1",
        "version": __version__,
        "system": platform.system(),
        "machine": platform.machine(),
        "pointer_bits": struct.calcsize("P") * 8,
        "python": platform.python_version(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "checks": [],
        "account_auth_bundled": False,
    }
    try:
        if getattr(sys, "frozen", False):
            import certifi

            assert (
                len(ssl.create_default_context(cafile=certifi.where()).get_ca_certs())
                > 50
            )
            receipt["checks"].append("bundled TLS certificate roots")
            receipt.update(account_runtime_test())
            if receipt["account_auth_bundled"]:
                receipt["checks"].append("bundled ChatGPT identity verification")
            else:
                receipt["checks"].append("ChatGPT sign-in unavailable in this build")
        with tempfile.TemporaryDirectory(prefix="sinter-native-test-") as directory:
            server = make_server(port=0, directory=directory)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                base = f"http://127.0.0.1:{server.server_port}"
                with opener.open(base + "/api/session", timeout=10) as response:
                    assert json.load(response)["version"] == __version__
                for route in (
                    "/",
                    "/static/app.js",
                    "/static/style.css",
                    "/static/settings.js",
                    "/static/atlas.js",
                    "/api/settings",
                ):
                    with opener.open(base + route, timeout=10) as response:
                        assert response.status == 200 and response.read()
                receipt["checks"].append("packaged static assets and loopback HTTP")
                for kind in ("brief", "grants", "meeting"):
                    result = workbench.run(workbench.example(kind))
                    assert result["workflow"] == kind
                receipt["checks"].append("three deterministic example workflows")
                example = {
                    "title": "Native package community check",
                    "questions": "Is the hall confirmed?",
                    "documents": [
                        {
                            "title": "Fictional note",
                            "content": "The hall is not confirmed.",
                        }
                    ],
                }
                saved = server.app.casebooks.save(example)
                report = casebooks.build(saved["document"])
                assert (
                    report["coverage"]["documents_supplied"] == 1
                    and "not confirmed" in report["markdown"]
                )
                assert server.app.casebooks.get(saved["id"])["revision"] == 1
                receipt["checks"].append(
                    "installed casebook persistence and exact-source retrieval"
                )
            finally:
                server.shutdown()
                server.app.close()
                server.server_close()
                thread.join(timeout=5)
        receipt["passed"] = True
    except Exception as exc:
        receipt["passed"] = False
        receipt["error_type"] = type(exc).__name__
        receipt["error"] = str(exc)
    Path(destination).write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return 0 if receipt["passed"] else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="Sinter")
    parser.add_argument("--self-test", metavar="RECEIPT")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test(args.self_test)
    if getattr(sys, "frozen", False):
        import certifi

        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    server = make_server(port=0)
    server.app.desktop_shutdown = server.shutdown
    threading.Thread(
        target=server.app.scheduler, daemon=True, name="sinter-watches"
    ).start()
    url = f"http://127.0.0.1:{server.server_port}"
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.app.close()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
