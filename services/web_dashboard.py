"""
Web Dashboard and Live Log Server for Railway Deployment.
Exposes a lightweight, modern web interface on os.getenv("PORT", 8080) allowing
the user to view real-time logs, bot stats, active accounts, and live browser screenshots.
"""

import os
import re
import html
import logging
from datetime import datetime
from pathlib import Path
from collections import deque
from typing import Optional
from aiohttp import web

import config
from services.account_manager import account_manager

logger = logging.getLogger(__name__)

# In-memory circular buffer storing the latest 1,500 log lines
LOG_BUFFER = deque(maxlen=1500)

class BufferLogHandler(logging.Handler):
    """Logging handler that appends formatted log records to in-memory LOG_BUFFER and bot.log."""
    def __init__(self, log_file: Optional[Path] = None):
        super().__init__()
        self.log_file = log_file

    def emit(self, record):
        try:
            msg = self.format(record)
            LOG_BUFFER.append(msg)
            if self.log_file:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(msg + "\n")
        except Exception:
            pass

def setup_log_capture():
    """Attaches BufferLogHandler to the root logger."""
    log_file = config.BASE_DIR / "bot.log"
    handler = BufferLogHandler(log_file=log_file)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    root = logging.getLogger()
    if root.level > logging.INFO:
        root.setLevel(logging.INFO)
    root.addHandler(handler)
    logger.info("Live Web Log Capture attached successfully.")

def get_latest_screenshot_path() -> Optional[Path]:
    """Finds the most recently modified screenshot file in screenshots directory."""
    shot_dir = config.BASE_DIR / "screenshots"
    if not shot_dir.exists():
        return None
    pngs = list(shot_dir.glob("*.png"))
    if not pngs:
        return None
    pngs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return pngs[0]

async def index_handler(request: web.Request) -> web.Response:
    """Renders the main dark-mode dashboard."""
    active_accs = account_manager.get_active()
    all_accs = account_manager.get_all()
    tot_bal = account_manager.get_total_balance()
    mode_badge = "SIMULATION (Safe)" if config.SIMULATION_MODE else "LIVE PURCHASING (Real)"
    mode_color = "#3b82f6" if config.SIMULATION_MODE else "#10b981"

    # Accounts table rows
    acc_rows = ""
    for idx, acc in enumerate(all_accs, 1):
        is_act = acc.get("is_active", True)
        status_badge = '<span class="badge green">Active</span>' if is_act else '<span class="badge gray">Paused</span>'
        acc_id = acc.get("id", f"acc_{idx}")
        lbl = html.escape(str(acc.get("label", acc_id)))
        bal = float(acc.get("wallet_balance", 0.0))
        uid = html.escape(str(acc.get("user_id", "N/A")))
        acc_rows += f"""
        <tr>
            <td><strong>#{idx}</strong></td>
            <td>{lbl} <small>({acc_id})</small></td>
            <td><code>{uid}</code></td>
            <td style="color: #38bdf8; font-weight: 600;">₹{bal:,.2f}</td>
            <td>{status_badge}</td>
        </tr>
        """

    if not acc_rows:
        acc_rows = '<tr><td colspan="5" style="text-align:center; color:#94a3b8;">No accounts configured. Use /settoken on Telegram.</td></tr>'

    has_screenshot = get_latest_screenshot_path() is not None
    screenshot_html = ""
    if has_screenshot:
        screenshot_html = """
        <div class="card">
            <div class="card-header">
                <h2>📸 Latest Browser View</h2>
                <a href="/screenshot" target="_blank" class="btn">View Full Size</a>
            </div>
            <div style="text-align: center; background: #000; border-radius: 8px; padding: 10px; margin-top: 10px;">
                <img src="/screenshot" id="liveScreenshot" style="max-width: 100%; height: auto; max-height: 420px; border-radius: 6px; border: 1px solid #334155;" alt="Latest Screenshot" />
            </div>
        </div>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PlayStation Auto-Buyer Bot | Live Dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #090d16;
            --surface: #111827;
            --border: #1f293d;
            --accent: #6366f1;
            --text: #f1f5f9;
            --muted: #94a3b8;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: var(--bg);
            color: var(--text);
            font-family: 'Outfit', -apple-system, sans-serif;
            padding: 24px;
            line-height: 1.5;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border);
            margin-bottom: 24px;
            flex-wrap: wrap;
            gap: 16px;
        }}
        .logo {{
            display: flex;
            align-items: center;
            gap: 12px;
            font-size: 22px;
            font-weight: 700;
        }}
        .status-pill {{
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(16, 185, 129, 0.1);
            color: #10b981;
            border: 1px solid rgba(16, 185, 129, 0.25);
            padding: 6px 14px;
            border-radius: 999px;
            font-size: 14px;
            font-weight: 600;
        }}
        .pulse {{
            width: 10px; height: 10px; background: #10b981; border-radius: 50%;
            box-shadow: 0 0 10px #10b981;
            animation: pulse 1.8s infinite;
        }}
        @keyframes pulse {{
            0% {{ transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }}
            70% {{ transform: scale(1); box-shadow: 0 0 0 10px rgba(16, 185, 129, 0); }}
            100% {{ transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }}
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 24px;
        }}
        .stat-card h3 {{ font-size: 13px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }}
        .stat-card .val {{ font-size: 26px; font-weight: 700; color: #fff; }}
        .badge {{ padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }}
        .badge.green {{ background: rgba(16, 185, 129, 0.2); color: #34d399; }}
        .badge.gray {{ background: rgba(148, 163, 184, 0.2); color: #94a3b8; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid var(--border); font-size: 14px; }}
        th {{ color: var(--muted); font-weight: 600; }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; }}
        .btn {{
            background: var(--accent); color: white; border: none; padding: 8px 16px;
            border-radius: 6px; font-weight: 600; font-size: 13px; text-decoration: none; cursor: pointer;
            display: inline-flex; align-items: center; gap: 6px;
        }}
        .btn:hover {{ opacity: 0.9; }}
        .console-container {{
            background: #050811;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
            height: 480px;
            overflow-y: auto;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12.5px;
            line-height: 1.6;
            color: #cbd5e1;
        }}
        .log-line {{ margin-bottom: 4px; word-break: break-all; white-space: pre-wrap; }}
        .log-info {{ color: #7dd3fc; }}
        .log-warning {{ color: #fde047; font-weight: 600; }}
        .log-error {{ color: #f87171; font-weight: 600; }}
        code {{ font-family: 'JetBrains Mono', monospace; background: rgba(255,255,255,0.06); padding: 2px 6px; border-radius: 4px; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="logo">
                <span>🎮</span>
                <div>
                    <div>PlayStation Auto-Buyer Bot</div>
                    <small style="font-size: 13px; color: var(--muted); font-weight: 400;">Railway High-Concurrency Auto-Sniper Dashboard</small>
                </div>
            </div>
            <div style="display: flex; gap: 12px; align-items: center;">
                <a href="/logs" class="btn" style="background: #1e293b; color: #94a3b8; border: 1px solid #334155;">📄 Raw Logs</a>
                <div class="status-pill">
                    <div class="pulse"></div>
                    <span>Online & Ready</span>
                </div>
            </div>
        </header>

        <div class="grid">
            <div class="card stat-card">
                <h3>Execution Mode</h3>
                <div class="val" style="color: {mode_color}; font-size: 20px;">{mode_badge}</div>
            </div>
            <div class="card stat-card">
                <h3>Active Accounts</h3>
                <div class="val">{len(active_accs)} <span style="font-size: 15px; color: var(--muted); font-weight: normal;">/ {len(all_accs)} configured</span></div>
            </div>
            <div class="card stat-card">
                <h3>Total Wallet Balance</h3>
                <div class="val" style="color: #38bdf8;">₹{tot_bal:,.2f}</div>
            </div>
            <div class="card stat-card">
                <h3>Sniper Refresh Rate</h3>
                <div class="val">{config.SNIPE_INTERVAL_SECONDS}s</div>
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <h2>👥 Registered Rooter Accounts (5-10 Concurrency)</h2>
                <span style="font-size: 13px; color: var(--muted);">Auto-synced via aiohttp</span>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Account Label</th>
                        <th>User ID</th>
                        <th>Live Balance</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {acc_rows}
                </tbody>
            </table>
        </div>

        {screenshot_html}

        <div class="card">
            <div class="card-header" style="margin-bottom: 12px;">
                <h2>📋 Live Container Logs <span style="font-size: 13px; color: var(--muted); font-weight: normal;">(Auto-refreshing every 3s)</span></h2>
                <div style="display: flex; gap: 8px;">
                    <button class="btn" style="background:#1e293b;" onclick="refreshLogs()">🔄 Refresh Now</button>
                    <button class="btn" style="background:#1e293b;" onclick="copyLogs()">📋 Copy Logs</button>
                </div>
            </div>
            <div class="console-container" id="logConsole">
                Loading live logs...
            </div>
        </div>
    </div>

    <script>
        function colorize(line) {{
            let escaped = line.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            if (escaped.includes('[ERROR]')) {{
                return '<div class="log-line log-error">' + escaped + '</div>';
            }} else if (escaped.includes('[WARNING]') || escaped.includes('⚠️')) {{
                return '<div class="log-line log-warning">' + escaped + '</div>';
            }} else if (escaped.includes('[INFO]')) {{
                return '<div class="log-line log-info">' + escaped + '</div>';
            }}
            return '<div class="log-line">' + escaped + '</div>';
        }}

        async function refreshLogs() {{
            try {{
                const res = await fetch('/logs/json');
                const data = await res.json();
                const container = document.getElementById('logConsole');
                if (data.logs && data.logs.length > 0) {{
                    container.innerHTML = data.logs.map(colorize).join('');
                    container.scrollTop = container.scrollHeight;
                }} else {{
                    container.innerHTML = '<div style="color: #64748b;">No logs recorded yet.</div>';
                }}
            }} catch (e) {{
                console.error("Log fetch error", e);
            }}
        }}

        function copyLogs() {{
            const text = document.getElementById('logConsole').innerText;
            navigator.clipboard.writeText(text).then(() => alert("Logs copied to clipboard!"));
        }}

        setInterval(refreshLogs, 3000);
        refreshLogs();
    </script>
</body>
</html>
"""
    return web.Response(text=html_content, content_type="text/html")

async def raw_logs_handler(request: web.Request) -> web.Response:
    """Returns raw text logs."""
    text = "\n".join(LOG_BUFFER)
    return web.Response(text=text, content_type="text/plain")

async def json_logs_handler(request: web.Request) -> web.Response:
    """Returns logs as a JSON list for dynamic frontend updating."""
    return web.json_response({"logs": list(LOG_BUFFER)})

async def screenshot_handler(request: web.Request) -> web.Response:
    """Returns the latest screenshot image."""
    latest = get_latest_screenshot_path()
    if not latest or not latest.exists():
        return web.Response(status=404, text="No screenshot captured yet.")
    try:
        data = latest.read_bytes()
        return web.Response(body=data, content_type="image/png")
    except Exception as e:
        return web.Response(status=500, text=str(e))

async def health_handler(request: web.Request) -> web.Response:
    """Healthcheck endpoint for Railway."""
    return web.json_response({
        "status": "healthy",
        "service": "playstation-bot",
        "timestamp": datetime.utcnow().isoformat(),
        "active_accounts": len(account_manager.get_active()),
    })

_WEB_RUNNER: Optional[web.AppRunner] = None

async def start_web_dashboard(port: int = 8080):
    """Starts the aiohttp web server on 0.0.0.0:$PORT."""
    global _WEB_RUNNER
    try:
        app = web.Application()
        app.router.add_get("/", index_handler)
        app.router.add_get("/logs", raw_logs_handler)
        app.router.add_get("/logs/json", json_logs_handler)
        app.router.add_get("/screenshot", screenshot_handler)
        app.router.add_get("/health", health_handler)

        _WEB_RUNNER = web.AppRunner(app)
        await _WEB_RUNNER.setup()
        site = web.TCPSite(_WEB_RUNNER, "0.0.0.0", port)
        await site.start()
        logger.info(f"🚀 Live Web Dashboard active on http://0.0.0.0:{port}")
    except Exception as e:
        logger.error(f"Failed to launch Web Dashboard on port {port}: {e}", exc_info=True)

async def stop_web_dashboard():
    """Stops the web dashboard server gracefully."""
    global _WEB_RUNNER
    if _WEB_RUNNER:
        try:
            await _WEB_RUNNER.cleanup()
            logger.info("Web Dashboard shut down gracefully.")
        except Exception:
            pass
