#!/usr/bin/env python3
"""Export the gos.earth presentations to PNG images.

A slide is one click of a deck: what it shows at #N in its URL. Slide N of a deck is saved as
<Topic>/<Topic>_slide_<N>.png, so GosIntro/GosIntro_slide_3.png is what-is-this/#3. With --pages,
each page is saved once instead, fully built, and N counts pages (the dots under the deck).

    python3 export_slides.py                       # every deck, served from ../static
    python3 export_slides.py --deck Ggg --pages
    python3 export_slides.py --base-url https://staging.gos.earth/

The images go to ./slides/ (gitignored) unless --out says otherwise, one folder per deck. A deck's
earlier images there are replaced, so a deck that loses slides loses their images too. The language picker and the
navigation dots are hidden, and eyes stay still. Needs Playwright for Python and its Chromium
(pip install playwright && playwright install chromium).
"""

import argparse
import functools
import http.server
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
STATIC = HERE.parent / "static"

# The file name prefix, the deck's path under static/, and how long, in ms, a step needs for the
# animations that run in JavaScript (CSS animations are waited for anyway).
DECKS = [
    ("GosIntro", "what-is-this/index.html", 3500),  # the globe glides for 2.6 s, then fades in 0.7 s
    ("Ggg", "what-is-this/ggg/index.html", 300),
]

# Hidden: the language picker and the navigation dots. Eyes look ahead and stay open, so that
# every export is the same.
HIDE_CSS = (
    ".lang, .dots { visibility: hidden !important; }"
    ".ax-pupil, .ax-led, .ax-pump { animation: none !important; } .ax-blink .ax-eye { transform: none !important; }"
)

# How many steps each page has, counted as the decks count them.
STEPS_JS = """() => Array.from(document.querySelectorAll('.page'), (page) => {
  const frags = Array.from(page.querySelectorAll('[data-frag]'), (f) => parseInt(f.dataset.frag, 10));
  return Math.max(parseInt(page.dataset.steps || '1', 10), 1 + Math.max(0, ...frags));
})"""

# Waits until every finite CSS animation and transition has ended, and at least minMs. A playing
# video then stops halfway through, so that every export shows the same frame. True if it settled
# within 20 s.
SETTLE_JS = """async (minMs) => {
  const start = performance.now();
  const finite = (a) => (a.playState === 'running' || a.playState === 'pending')
    && Number.isFinite(a.effect?.getComputedTiming().endTime);
  let settled = false;
  while (performance.now() - start < 20000) {
    if (!document.getAnimations().some(finite) && performance.now() - start >= minMs) {
      settled = true;
      break;
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  for (const v of document.querySelectorAll('video')) {
    if (v.paused || !Number.isFinite(v.duration)) continue;
    v.pause();
    await new Promise((r) => {
      v.addEventListener('seeked', r, { once: true });
      setTimeout(r, 2000);
      v.currentTime = v.duration / 2;
    });
  }
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  return settled;
}"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve_static():
    handler = functools.partial(QuietHandler, directory=str(STATIC))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/"


def export_deck(page, base, topic, path, js_ms, out, pages_only):
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base + path, wait_until="networkidle")
    page.add_style_tag(content=HIDE_CSS)
    page.evaluate("document.fonts.ready.then(() => true)")
    steps = page.evaluate(STEPS_JS)
    if pages_only:
        shots = [(i + 1, sum(steps[: i + 1])) for i in range(len(steps))]
    else:
        shots = [(n, n) for n in range(1, sum(steps) + 1)]

    out = out / topic
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob(f"{topic}_slide_*.png"):
        old.unlink()
    for number, scene in shots:
        page.evaluate("(n) => window.__goToScene(n)", scene)
        if not page.evaluate(SETTLE_JS, js_ms):
            print(f"  {topic} slide {number}: still animating after 20 s, saved anyway", file=sys.stderr)
        page.screenshot(path=out / f"{topic}_slide_{number}.png")
    print(f"{topic}: {len(shots)} images in {out}")
    for e in errors:
        print(f"  {topic} console error: {e}", file=sys.stderr)
    return not errors


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--deck", action="append", choices=[d[0] for d in DECKS],
                        help="export only this deck (repeatable); default: all")
    parser.add_argument("--pages", action="store_true",
                        help="one image per page, fully built, instead of one per step")
    parser.add_argument("--out", type=Path, default=HERE / "slides", help="default: ./slides")
    parser.add_argument("--size", default="1920x1080", help="viewport WIDTHxHEIGHT, default 1920x1080")
    parser.add_argument("--scale", type=float, default=1, help="device pixel ratio, e.g. 2 for sharper images")
    parser.add_argument("--base-url", help="export the decks from this site instead of ../static")
    args = parser.parse_args()

    width, height = (int(x) for x in args.size.lower().split("x"))
    decks = [d for d in DECKS if not args.deck or d[0] in args.deck]

    server = None
    if args.base_url:
        base = args.base_url.rstrip("/") + "/"
    else:
        server, base = serve_static()
    ok = True
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for topic, path, js_ms in decks:
                context = browser.new_context(viewport={"width": width, "height": height},
                                              device_scale_factor=args.scale, locale="en-US")
                ok &= export_deck(context.new_page(), base, topic, path, js_ms, args.out, args.pages)
                context.close()
            browser.close()
    finally:
        if server:
            server.shutdown()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
