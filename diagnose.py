"""Unauthenticated browser probe; never loads account env or submits check-in."""
import asyncio
import json
import tempfile
import urllib.request

import nodriver as uc
from api import browser_options


async def cleanup_probe(browser, profile):
    """Keep shutdown failures separate from the public-page verdict."""
    try:
        if browser is not None:
            process = getattr(browser, "_process", None)
            browser.stop()
            if process is not None:
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    process.kill()
                    await asyncio.wait_for(process.wait(), timeout=2)
    except Exception as exc:
        print(json.dumps({"cleanup_warning": "browser_shutdown", "error": type(exc).__name__}), flush=True)
    finally:
        try:
            profile.cleanup()
        except OSError as exc:
            # Chrome may still write profile files while shutting down. The
            # disposable container removes any remaining files on exit.
            print(json.dumps({"cleanup_warning": "temporary_profile", "errno": exc.errno}), flush=True)


async def probe():
    # This request also uses the shared VPN network, independently of Chrome.
    try:
        with urllib.request.urlopen("https://www.cloudflare.com/cdn-cgi/trace", timeout=20) as response:
            fields = dict(line.split("=", 1) for line in response.read(8192).decode().splitlines() if "=" in line)
        print(json.dumps({"exit_ip": fields.get("ip"), "exit_country": fields.get("loc")}), flush=True)
    except Exception as exc:
        print(json.dumps({"exit_probe_error": type(exc).__name__}), flush=True)
        return 1
    profile = tempfile.TemporaryDirectory(prefix="public-probe-")
    browser = None
    try:
        browser = await uc.start(user_data_dir=profile.name, **browser_options())
        tab = await browser.get("https://2dfan.com/")
        # Wait passively; do not interact with challenges or login controls.
        for _ in range(15):
            await asyncio.sleep(2)
            raw = await tab.evaluate("""JSON.stringify({
                title: document.title,
                host: location.hostname,
                challenge: /just a moment|请稍候|checking your browser/i.test(document.title),
                blocked: /sorry, you have been blocked|access denied|error (?:code: )?1020/i.test((document.title || '') + ' ' + (document.body?.innerText || '')),
                network: /ERR_[A-Z_]+/.test(document.body?.innerText || ''),
                content: (document.body?.innerText || '').length > 100
            })""")
            flags = json.loads(raw)
            if not flags.get("challenge"):
                break
        print(json.dumps({"public_page": flags}, ensure_ascii=False), flush=True)
        return 0 if (flags.get("host") == "2dfan.com" and flags.get("content")
                     and not any(flags.get(k) for k in ("challenge", "blocked", "network"))) else 2
    finally:
        await cleanup_probe(browser, profile)


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(asyncio.wait_for(probe(), timeout=100)))
    except Exception as exc:
        print(json.dumps({"probe_error": type(exc).__name__}), flush=True)
        raise SystemExit(1)
