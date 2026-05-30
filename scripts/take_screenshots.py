"""Take screenshots of the AgentLedger dashboard — scroll stMain and crop."""
import asyncio
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright

BASE_URL = "http://localhost:8502"
OUT = Path("docs/screenshots")
OUT.mkdir(parents=True, exist_ok=True)
CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
W = 1440


def crop(src: Path, dst: Path, y0: int, height: int = 860) -> None:
    img = Image.open(src)
    y1 = min(y0 + height, img.height)
    if y1 <= y0:
        return
    img.crop((0, y0, img.width, y1)).save(dst)


async def scroll_to(page, y: int) -> None:
    """Scroll the stMain Streamlit container to a given offset."""
    await page.evaluate(f"""
        const el = document.querySelector('section[data-testid="stMain"]')
                || document.querySelector('.stMain');
        if (el) el.scrollTop = {y};
    """)
    await asyncio.sleep(1.2)


async def wait_ready(page):
    await page.wait_for_load_state("networkidle", timeout=30000)
    await asyncio.sleep(3)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=CHROMIUM,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

        # ── Tall viewport so everything renders ───────────────────────────
        ctx = await browser.new_context(viewport={"width": W, "height": 2200})
        page = await ctx.new_page()
        print("Loading demo mode with tall viewport...")
        await page.goto(BASE_URL, timeout=30000)
        await wait_ready(page)

        # Get actual scroll height
        scroll_h = await page.evaluate(
            """() => {
                const el = document.querySelector('section[data-testid="stMain"]')
                        || document.querySelector('.stMain');
                return el ? el.scrollHeight : document.body.scrollHeight;
            }"""
        )
        print(f"Streamlit content height: {scroll_h}px")

        # Capture full page with tall viewport
        full = OUT / "_full_demo.png"
        await page.screenshot(path=str(full), full_page=True)
        actual_h = Image.open(full).height
        print(f"Screenshot captured: {W}x{actual_h}")

        # If the viewport captured everything, crop sections
        if actual_h >= 1800:
            crop(full, OUT / "01_sidebar_api_status.png", y0=0,    height=900)
            crop(full, OUT / "03_pipeline_progress.png",  y0=0,    height=900)
            crop(full, OUT / "04_kpi_cards.png",          y0=0,    height=460)
            crop(full, OUT / "05_charts.png",             y0=900,  height=700)
            crop(full, OUT / "06_risk_assessment.png",    y0=1600, height=700)
            crop(full, OUT / "07_hitl_review.png",        y0=2300, height=700)
            crop(full, OUT / "08_credit_memo.png",        y0=3000, height=700)
            crop(full, OUT / "09_transactions.png",       y0=3700, height=700)
        else:
            # Viewport-based: scroll stMain and take viewport shots
            print("Falling back to scroll-based capture...")
            positions = {
                "01_sidebar_api_status.png": 0,
                "03_pipeline_progress.png":  0,
                "04_kpi_cards.png":          0,
                "05_charts.png":             500,
                "06_risk_assessment.png":    900,
                "07_hitl_review.png":        1300,
                "08_credit_memo.png":        1700,
                "09_transactions.png":       2100,
            }
            for fname, y in positions.items():
                await scroll_to(page, y)
                await page.screenshot(
                    path=str(OUT / fname),
                    clip={"x": 0, "y": 0, "width": W, "height": 860},
                )

        # ── Launch panel (separate viewport shot) ────────────────────────
        await page.set_viewport_size({"width": W, "height": 860})
        await page.get_by_text("Run live analysis").click(timeout=5000)
        await asyncio.sleep(2.5)
        await page.screenshot(path=str(OUT / "02_launch_panel.png"))
        print("Launch panel done.")

        await browser.close()

    full.unlink(missing_ok=True)
    print()
    for f in sorted(OUT.glob("[0-9]*.png")):
        img = Image.open(f)
        kb = f.stat().st_size // 1024
        print(f"  {f.name}: {img.width}x{img.height}  {kb}KB")
    print("\nDone.")


asyncio.run(main())
