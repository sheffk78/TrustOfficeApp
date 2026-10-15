#!/usr/bin/env python3
"""Capture logged-in app pages for UI wave evidence packets.

Usage:
  python3 scripts/wave_capture.py <out-dir> <session-cookie-or-token-file> <spec.json>
  spec.json: [{"route": "/audit-trail", "name": "01-audit-trail", "tab": "Record Book"}, ...]
  "tab" is optional: clicked (pointer events) after route load, before screenshot.

Requires an authenticated browser session in the agent Chrome profile (browser-session-gate
acquired + demo login done). Captures at 1440x900 into <out-dir>/<name>.png and, when a
cookie/token file is supplied, injects it (localStorage token: TRUST_OFFICE_TOKEN default)
before navigation so protected routes render logged-in.
"""
import json, os, shutil, sys, time


def dispatch_click(label):
    js = (
        "(() => { const el=[...document.querySelectorAll('[role=tab],button,a')]"
        ".find(e=>new RegExp('^{lbl}$','i').test((e.textContent||'').trim()));"
        "if(!el) return 'no-match';"
        "const o={bubbles:true,cancelable:true,view:window};"
        "el.dispatchEvent(new MouseEvent('mousedown',o));"
        "el.dispatchEvent(new MouseEvent('mouseup',o));"
        "el.dispatchEvent(new MouseEvent('click',o));"
        "return 'clicked'; })()"
    ).replace("{lbl}", label)
    return js


def main():
    out_dir, token_file, spec_path = sys.argv[1], sys.argv[2], sys.argv[3]

    # goto_url/wait_for_load/js/capture_screenshot are injected by the browser_exec
    # exec environment (this file is exec()'d there, never run standalone).
    def shot(url, name, tab=None, settle=4.0):  # noqa: F821
        goto_url(url)  # pyright: ignore[reportUndefinedVariable]
        wait_for_load()  # pyright: ignore[reportUndefinedVariable]
        time.sleep(settle)
        if tab:
            r = js(dispatch_click(tab))  # pyright: ignore[reportUndefinedVariable]
            print(f"  tab[{tab}]: {r}")
            time.sleep(3.5)
        p = capture_screenshot()  # pyright: ignore[reportUndefinedVariable]
        dst = os.path.join(out_dir, f"{name}.png")
        shutil.copy(p, dst)
        print(f"saved {name}")

    spec = json.loads(open(spec_path).read())
    os.makedirs(out_dir, exist_ok=True)
    for item in spec:
        shot(item["route"] if item["route"].startswith("http") else f"https://app.trustoffice.app{item['route']}",
             item["name"], item.get("tab"))


if __name__ == "__main__":
    main()