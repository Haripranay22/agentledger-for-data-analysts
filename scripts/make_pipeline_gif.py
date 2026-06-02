"""
Capture the pipeline progress animation as a GIF.
Uses a self-contained HTML page that plays the animation frame-by-frame.
"""
import asyncio
from pathlib import Path
from PIL import Image
from playwright.async_api import async_playwright

CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
OUT = Path("docs")
OUT.mkdir(exist_ok=True)

STEPS = [
    ("1", "Ingesting transactions from Plaid",     "312 transactions pulled · 6 months"),
    ("2", "Running data quality checks",           "0 dropped · 312 passed"),
    ("3", "Categorizing transactions (ML)",        "312 categorized · TF-IDF + RandomForest"),
    ("4", "Computing cash-flow metrics",           "8 metrics calculated · Python only"),
    ("5", "Running AI risk assessment",            "gpt-4o-mini · structured output"),
    ("6", "Validating citations & claims",         "97.0% validity · 0 hallucinations"),
    ("7", "Checking escalation criteria",          "No escalation needed"),
    ("8", "Generating credit memo",                "Saved → reports/USER_001/memo.md"),
]

def build_html(completed: int, running: int | None) -> str:
    rows = ""
    for i, (num, title, detail) in enumerate(STEPS):
        if i < completed:
            icon  = '<span style="color:#4ade80;font-size:13px">✓</span>'
            color = "#e8edf5"
            det   = f'<div style="color:#3a5a4a;font-size:11px;padding-left:22px;margin-top:1px">{detail}</div>'
        elif i == running:
            icon  = '<span style="animation:spin 0.8s linear infinite;display:inline-block;font-size:12px">⟳</span>'
            color = "#4f8ef7"
            det   = f'<div style="color:#2a4a7a;font-size:11px;padding-left:22px;margin-top:1px">{detail}</div>'
        else:
            icon  = '<span style="color:#1e2d45;font-size:13px">○</span>'
            color = "#2a3a55"
            det   = ""
        rows += f"""
        <div style="display:flex;align-items:flex-start;gap:8px;padding:7px 12px;
                    border-radius:6px;{"background:#0d1b0f;" if i<completed else "background:#0d1525;" if i==running else ""}">
          {icon}
          <div style="flex:1">
            <div style="display:flex;align-items:center;gap:6px">
              <span style="color:#2a4060;font-size:10px;font-weight:700;min-width:12px">{num}</span>
              <span style="color:{color};font-size:13px;font-weight:{"600" if i==running else "400"}">{title}</span>
            </div>
            {det}
          </div>
        </div>"""

    pct = int(completed / len(STEPS) * 100)
    if running is not None:
        pct = int((completed + 0.5) / len(STEPS) * 100)

    status_label = "Analysis complete ✓" if running is None and completed == len(STEPS) else \
                   f"Running — {STEPS[running][1]}…" if running is not None else ""
    status_color = "#4ade80" if completed == len(STEPS) else "#4f8ef7"

    return f"""<!DOCTYPE html>
<html>
<head>
<style>
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0f1117; color: #e8edf5;
    width: 640px; padding: 0;
  }}
</style>
</head>
<body>
<div style="padding: 24px 28px">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
    <div>
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:2px">
        <div style="width:22px;height:22px;border-radius:5px;
             background:linear-gradient(135deg,#4f8ef7,#7c3aed);
             display:flex;align-items:center;justify-content:center;
             font-size:11px;font-weight:900;color:white">A</div>
        <span style="font-size:1rem;font-weight:800;color:#e8edf5">AgentLedger</span>
        <span style="font-size:0.6rem;color:#4f8ef7;font-weight:600;
              letter-spacing:0.08em;text-transform:uppercase">Credit Intelligence</span>
      </div>
    </div>
    <div style="background:#0d1525;border:1px solid #1e2d45;border-radius:6px;
                padding:5px 12px;font-size:11px;color:#4a5a78">
      USER_001 · $25,000 · Home Improvement
    </div>
  </div>
  <div style="font-size:12px;font-weight:600;color:{status_color};margin-bottom:10px;min-height:16px">
    {status_label}
  </div>
  <div style="background:#1a1f2e;border-radius:4px;height:4px;margin-bottom:16px;overflow:hidden">
    <div style="background:linear-gradient(90deg,#4f8ef7,#7c3aed);height:4px;
                width:{pct}%;border-radius:4px;transition:width 0.3s"></div>
  </div>
  <div style="display:flex;flex-direction:column;gap:2px">
    {rows}
  </div>
  {"<div style='margin-top:18px;background:#0d1b0f;border:1px solid #1a4a2a;border-radius:8px;padding:14px 16px;display:flex;align-items:center;justify-content:space-between'><div><div style='color:#4ade80;font-size:13px;font-weight:700'>✓ Analysis complete</div><div style='color:#2a5a3a;font-size:11px;margin-top:2px'>Risk Score 26 · APPROVE · Citation validity 97%</div></div><div style='background:#0e2a1a;border:1px solid #1a4a2a;color:#4ade80;padding:5px 14px;border-radius:20px;font-size:12px;font-weight:700'>APPROVE</div></div>" if completed == len(STEPS) else ""}
</div>
</body>
</html>"""


async def capture_frames() -> list[Image.Image]:
    frames = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=CHROMIUM,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = await browser.new_page(viewport={"width": 640, "height": 520})

        async def snap(html: str, hold: int = 1) -> None:
            await page.set_content(html)
            await asyncio.sleep(0.15)
            buf = await page.screenshot()
            img = Image.open(__import__("io").BytesIO(buf))
            for _ in range(hold):
                frames.append(img.copy())

        # Launch panel frame
        launch_html = """<!DOCTYPE html><html><head>
        <style>* {box-sizing:border-box;margin:0;padding:0}
        body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
              background:#0f1117;color:#e8edf5;width:640px;padding:28px}</style>
        </head><body>
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:20px">
          <div style="width:22px;height:22px;border-radius:5px;
               background:linear-gradient(135deg,#4f8ef7,#7c3aed);
               display:flex;align-items:center;justify-content:center;
               font-size:11px;font-weight:900;color:white">A</div>
          <span style="font-size:1rem;font-weight:800">AgentLedger</span>
          <span style="font-size:0.6rem;color:#4f8ef7;font-weight:600;letter-spacing:0.08em;text-transform:uppercase">Credit Intelligence</span>
        </div>
        <div style="background:#111827;border:1px solid #1e2d45;border-radius:12px;padding:28px;text-align:center">
          <div style="font-size:1.3rem;font-weight:800;margin-bottom:6px">One-Click Credit Analysis</div>
          <div style="color:#4a5a78;font-size:12px;margin-bottom:20px">
            Ingest → Profile → Categorize → Risk Assess → Validate → Report
          </div>
          <div style="display:flex;gap:8px;justify-content:center;margin-bottom:24px">
            <span style="background:#0d2a1a;border:1px solid #1a4a2a;color:#4ade80;padding:4px 12px;border-radius:4px;font-size:11px">✅ LLM API</span>
            <span style="background:#0d2a1a;border:1px solid #1a4a2a;color:#4ade80;padding:4px 12px;border-radius:4px;font-size:11px">✅ Plaid</span>
            <span style="background:#0d2a1a;border:1px solid #1a4a2a;color:#4ade80;padding:4px 12px;border-radius:4px;font-size:11px">✅ Access Token</span>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:18px;text-align:left">
            <div>
              <div style="font-size:11px;color:#4a5a78;margin-bottom:4px">Borrower ID</div>
              <div style="background:#1a1f2e;border:1px solid #1e2d45;border-radius:6px;padding:8px 12px;font-size:13px">USER_001</div>
            </div>
            <div>
              <div style="font-size:11px;color:#4a5a78;margin-bottom:4px">Loan Amount ($)</div>
              <div style="background:#1a1f2e;border:1px solid #1e2d45;border-radius:6px;padding:8px 12px;font-size:13px">25,000.00</div>
            </div>
          </div>
          <div style="background:linear-gradient(135deg,#4f8ef7,#7c3aed);border-radius:8px;padding:12px;
                      font-size:13px;font-weight:700;cursor:pointer;letter-spacing:0.03em">
            ⚡ Run Complete Analysis
          </div>
        </div>
        </body></html>"""
        await snap(launch_html, hold=8)

        for i in range(len(STEPS)):
            await snap(build_html(i, i), hold=3)
            await snap(build_html(i + 1, None if i == len(STEPS)-1 else i+1), hold=2)

        await snap(build_html(len(STEPS), None), hold=12)
        await browser.close()

    print(f"Captured {len(frames)} frames")
    return frames


def frames_to_gif(frames: list[Image.Image], path: Path, fps: int = 5) -> None:
    duration = int(1000 / fps)
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        optimize=True,
        duration=duration,
        loop=0,
    )
    size_kb = path.stat().st_size // 1024
    print(f"GIF saved: {path}  ({size_kb}KB, {len(frames)} frames @ {fps}fps)")


async def main():
    frames = await capture_frames()
    gif_path = OUT / "pipeline_demo.gif"
    frames_to_gif(frames, gif_path, fps=5)


asyncio.run(main())
