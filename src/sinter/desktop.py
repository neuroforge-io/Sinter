"""One packaged runtime for native, browser, headless and command-line use.

--self-test exercises the installed application without external requests.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import os
import platform
import signal
import sqlite3
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
        diagnostics = launch_diagnostics()
        receipt["native_window_bundled"] = (
            diagnostics.get("native_toolkit_available") is True
            and diagnostics.get("Tcl_resources_available") is True
            and diagnostics.get("bundled_Tk_resources_available", True) is True
        )
        receipt["native_display_tested"] = False
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
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and not arguments[0].startswith("-"):
        # The frozen executable exposes the same commands as `python -m sinter`.
        from .cli import main as cli_main

        cli_main(arguments)
        return 0
    parser = argparse.ArgumentParser(prog="Sinter")
    parser.add_argument("--self-test", metavar="RECEIPT")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Explicit headless local server (legacy option)",
    )
    parser.add_argument(
        "--mode",
        choices=("native", "browser", "headless"),
        default="native",
        help=(
            "Native portable workspace (default), full browser workspace, "
            "or an explicit loopback server"
        ),
    )
    parser.add_argument(
        "--directory", metavar="PATH", help="Use a selected local workspace directory"
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help=(
            "Report bundled launch resources without a window, server "
            "or provider request"
        ),
    )
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(arguments)
    if args.self_test:
        return self_test(args.self_test)
    if args.diagnose:
        result = launch_diagnostics()
        print(json.dumps(result, indent=2))
        return 0 if result["core_assets_available"] else 1
    if getattr(sys, "frozen", False):
        import certifi

        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    mode = "headless" if args.no_browser else args.mode
    if mode == "native":
        try:
            from .native_window import NativeWindowError, run_native

            return run_native(args.directory)
        except ImportError:
            print(
                "Sinter: Native window dependencies are unavailable. "
                "Use 'Sinter operations' "
                "or reinstall a complete native package. No server was started.",
                file=sys.stderr,
            )
            return 1
        except NativeWindowError as exc:
            print(
                f"Sinter: {exc}\nUse 'Sinter operations' and 'Sinter run' "
                "for offline command-line work. The full browser workspace "
                "requires an environment that permits its loopback address. "
                "No server or browser fallback was started.",
                file=sys.stderr,
            )
            return 1
        except (OSError, sqlite3.Error) as exc:
            print(
                f"Sinter: The local workspace could not be opened "
                f"({type(exc).__name__}). Check the directory and permissions, "
                "or use an exported backup in a separate workspace. "
                "No server or browser fallback was started.",
                file=sys.stderr,
            )
            return 1
        except KeyboardInterrupt:
            print("Stopped.", file=sys.stderr)
            return 130
    return serve_desktop(args.directory, open_browser=mode == "browser")


def launch_diagnostics() -> dict:
    """Check local resources without claiming display or browser-policy access."""
    from importlib import resources

    assets = resources.files("sinter").joinpath("web")
    result = {
        "schema": "sinter-launch-check/v1",
        "version": __version__,
        "frozen": bool(getattr(sys, "frozen", False)),
        "core_assets_available": all(
            assets.joinpath(name).is_file()
            for name in ("index.html", "app.js", "style.css")
        ),
        "native_toolkit_available": False,
        "native_display_tested": False,
        "native_window": (
            "scoped portable source workspace; full web screens "
            "use explicit browser mode"
        ),
        "browser_policy_tested": False,
        "provider_requests": 0,
    }
    try:
        import tkinter

        interpreter = tkinter.Tcl()
        result.update(
            native_toolkit_available=True,
            Tcl_version=str(interpreter.call("info", "patchlevel")),
            Tk_version=tkinter.TkVersion,
            Tcl_resources_available=Path(str(interpreter.call("info", "library")))
            .joinpath("init.tcl")
            .is_file(),
        )
        library = os.environ.get("TK_LIBRARY")
        if library:
            result["bundled_Tk_resources_available"] = (
                Path(library).joinpath("tk.tcl").is_file()
            )
    except Exception as exc:
        result["native_toolkit_error"] = type(exc).__name__
    return result


def serve_desktop(directory=None, *, open_browser=False) -> int:
    """Run only an explicitly requested loopback interface, with owned cleanup."""
    try:
        server = make_server(port=0, directory=directory)
    except (OSError, ValueError) as exc:
        print(
            f"Sinter: Cannot start the local server ({type(exc).__name__}). "
            "Use the native workspace or offline CLI in a restricted environment.",
            file=sys.stderr,
        )
        return 1
    server.app.desktop_shutdown = server.shutdown
    serving = threading.Thread(
        target=server.serve_forever, daemon=True, name="sinter-http"
    )
    serving.start()
    watches = threading.Thread(
        target=server.app.scheduler, daemon=True, name="sinter-watches"
    )
    url = f"http://127.0.0.1:{server.server_port}"
    previous_signal = None
    if threading.current_thread() is threading.main_thread():
        previous_signal = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, lambda *_: server.shutdown())
    try:
        print(f"Sinter local workspace: {url}", flush=True)
        if open_browser:
            try:
                opened = webbrowser.open(url)
            except (OSError, webbrowser.Error):
                opened = False
            if not opened:
                print(
                    "Sinter: No browser accepted the launch. "
                    "The local server has stopped. Use the native workspace or "
                    "offline CLI; managed URL policies remain in force.",
                    file=sys.stderr,
                )
                return 1
        watches.start()
        print(
            "Press Ctrl+C to stop. Closing a browser tab alone does not quit Sinter.",
            file=sys.stderr,
        )
        while serving.is_alive():
            serving.join(timeout=0.2)
    except KeyboardInterrupt:
        print("Stopped.", file=sys.stderr)
    finally:
        if serving.is_alive():
            server.shutdown()
        server.app.close()
        server.server_close()
        serving.join(timeout=5)
        if watches.is_alive():
            watches.join(timeout=5)
        if previous_signal is not None:
            signal.signal(signal.SIGTERM, previous_signal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
