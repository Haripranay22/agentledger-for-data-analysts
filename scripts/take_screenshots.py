"""Capture real screenshots of the AgentLedger demo dashboard."""
import asyncio
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright

BASE_URL = "http://localhost:8502"
OUT = Path("docs/screenshots")
OUT.mkdir(parents=True, exist_ok=True)
CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
W = 1440


async def wait_ready(page):
    await page.wait_for_load_state("networkidle", timeout=30000)
    await asyncio.sleep(3)


def save_crop(src: Path, dst: Path, y0: int, height: int) -> None:
    img = Image.open(src)
    y1 = min(y0 + height, img.height)
    img.crop((0, y0, img.width, y1)).save(dst)
    kb = dst.stat().st_size // 1024
    print(f"  {dst.name}: {img.crop((0, y0, img.width, y1)).size}  {kb}KB")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=CHROMIUM,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

        # ── Full page in tall viewport ────────────────────────────────────
        ctx = await browser.new_context(viewport={"width": W, "height": 2400})
        page = await ctx.new_page()
        print("Loading demo mode...")
        await page.goto(BASE_URL, timeout=30000)
        await wait_ready(page)

        full = OUT / "_full_demo.png"
        await page.screenshot(path=str(full), full_page=True)
        h = Image.open(full).height
        print(f"Full page captured: {W}x{h}px")

        save_crop(full, OUT / "01_sidebar_api_status.png", y0=0,    height=900)
        save_crop(full, OUT / "03_pipeline_progress.png",  y0=0,    height=430)
        save_crop(full, OUT / "04_kpi_cards.png",          y0=400,  height=430)
        save_crop(full, OUT / "05_charts.png",             y0=820,  height=430)
        save_crop(full, OUT / "06_risk_assessment.png",    y0=1220, height=560)
        save_crop(full, OUT / "07_hitl_review.png",        y0=1750, height=560)
        save_crop(full, OUT / "08_credit_memo.png",        y0=2100, height=max(200, h - 2100))
        save_crop(full, OUT / "09_transactions.png",       y0=max(0, h - 500), height=500)

        # ── Launch panel — click sidebar option ──────────────────────────
        await page.set_viewport_size({"width": W, "height": 860})
        await page.scroll_into_view_if_needed("text=Run live analysis") if False else None
        try:
            await page.get_by_text("Run live analysis").first.click(timeout=5000)
            await asyncio.sleep(2)
        except Exception:
            pass
        await page.screenshot(path=str(OUT / "02_launch_panel.png"))
        kb = (OUT / "02_launch_panel.png").stat().st_size // 1024
        print(f"  02_launch_panel.png: {W}x860  {kb}KB")

        await browser.close()

    full.unlink(missing_ok=True)
    print("\nDone.")


asyncio.run(main())
