import sys
import subprocess
import os

# ── Auto-install dependencies to .cache/pip ───────────────────────────
_PIP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "pip")
if _PIP_DIR not in sys.path:
    sys.path.insert(0, _PIP_DIR)

def _ensure_deps():
    pkgs = {
        "requests": "requests",
        "flask":    "flask",
        "discord":  "discord.py",
    }
    missing = []
    for mod, pkg in pkgs.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"[DEP ] Installing: {' '.join(missing)}")
        os.makedirs(_PIP_DIR, exist_ok=True)
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install",
             "--target", _PIP_DIR, "--quiet",
             "-i", "https://mirror.kakao.com/pypi/simple"] + missing
        )
        print("[DEP ] Done. Restarting process...")
        os.execv(sys.executable, [sys.executable] + sys.argv)

_ensure_deps()

# ── Now safe to import ────────────────────────────────────────────────
import importlib.util
import random
import string
import threading
import asyncio
from pathlib import Path

import requests
from flask import Flask, jsonify, request, send_from_directory, session

try:
    import discord
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False
    print("WARNING: discord.py not installed.")

# ── Port configuration ────────────────────────────────────────────────
PORT = int(
    os.environ.get("SERVER_PORT") or
    os.environ.get("PORT") or
    os.environ.get("APP_PORT") or
    os.environ.get("ALLOCATED_PORT") or
    443
)

if   os.environ.get("SERVER_PORT"):    print(f"[PORT] Using SERVER_PORT: {PORT}")
elif os.environ.get("PORT"):           print(f"[PORT] Using PORT: {PORT}")
elif os.environ.get("APP_PORT"):       print(f"[PORT] Using APP_PORT: {PORT}")
elif os.environ.get("ALLOCATED_PORT"): print(f"[PORT] Using ALLOCATED_PORT: {PORT}")
else:
    print(f"[PORT] Using default port: {PORT}")
    print("[TIP ] Set environment variable PORT=<your_port> to override")

# ── Flask app ─────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=".")
app.secret_key = "discord-bot-sakura-secret"
app.config["PERMANENT_SESSION_LIFETIME"] = 3600

CONFIG_FILE = Path(".cache/sub.txt")


# ── Helpers ───────────────────────────────────────────────────────────
def get_public_ip() -> str | None:
    for url in ("https://api.ip.sb/ip", "https://api.ipify.org"):
        try:
            return requests.get(url, timeout=3).text.strip()
        except Exception:
            pass
    return None


def gen_password(length: int = 16) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


def gen_example_token() -> str:
    import base64
    p1 = base64.b64encode(str(random.random()).encode()).decode()[:24]
    p2 = "".join(random.choices(string.ascii_letters + string.digits, k=6))
    p3 = "".join(random.choices(string.ascii_letters + string.digits, k=27))
    return f"{p1}.{p2}.{p3}"


# ── Config ────────────────────────────────────────────────────────────
config: dict = {
    "adminPassword":      gen_password(16),
    "discordToken":       gen_example_token(),
    "translateApiUrl":    "https://libretranslate.com",
    "translateApiKey":    "",
    "botStatus":          "offline",
    "commandPrefix":      "!",
    "supportedLanguages": ["zh", "en", "ja", "ko", "fr", "de", "es", "ru"],
}


def load_config() -> None:
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text("utf-8").splitlines():
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip(); value = value.strip()
            if not key:
                continue
            if key == "supportedLanguages":
                config[key] = [l.strip() for l in value.split(",") if l.strip()]
            else:
                config[key] = value
        print("[OK ] Config loaded from file")
    else:
        print("[INIT] First run — generating new config file")
        print(f"[INIT] Admin password : {config['adminPassword']}")
        print(f"[INIT] Example token  : {config['discordToken']}")
        save_config()


def save_config() -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text("\n".join([
        f"adminPassword={config['adminPassword']}",
        f"discordToken={config['discordToken']}",
        f"translateApiUrl={config['translateApiUrl']}",
        f"translateApiKey={config['translateApiKey']}",
        f"botStatus={config['botStatus']}",
        f"commandPrefix={config['commandPrefix']}",
        f"supportedLanguages={','.join(config['supportedLanguages'])}",
    ]), "utf-8")
    print("[OK ] Config saved")


load_config()


# ── Translation helpers ───────────────────────────────────────────────
def _translate(text: str, target: str = "en", source: str = "auto") -> str | None:
    try:
        headers = {"Content-Type": "application/json"}
        if config["translateApiKey"]:
            headers["Authorization"] = f"Bearer {config['translateApiKey']}"
        r = requests.post(
            f"{config['translateApiUrl']}/translate",
            json={"q": text, "source": source, "target": target, "format": "text"},
            headers=headers, timeout=10,
        )
        return r.json().get("translatedText")
    except Exception as e:
        print(f"[ERR ] Translation error: {e}")
        return None


def _detect_lang(text: str) -> str:
    try:
        r = requests.post(
            f"{config['translateApiUrl']}/detect",
            json={"q": text}, timeout=10,
        )
        return r.json()[0]["language"]
    except Exception:
        return "en"


# ── Discord bot ───────────────────────────────────────────────────────
_bot_thread: threading.Thread | None = None
_discord_client: "discord.Client | None" = None
_bot_loop: asyncio.AbstractEventLoop | None = None


def _run_bot() -> None:
    global _discord_client, _bot_loop

    _bot_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_bot_loop)

    intents = discord.Intents.default()
    intents.message_content = True
    _discord_client = discord.Client(intents=intents)

    @_discord_client.event
    async def on_ready():
        print(f"[BOT ] Online as: {_discord_client.user}")
        config["botStatus"] = "online"
        save_config()

    @_discord_client.event
    async def on_message(message: "discord.Message"):
        if message.author.bot:
            return
        content = message.content.strip()
        prefix  = config["commandPrefix"]

        for cmd in (f"{prefix}translate ", f"{prefix}tr "):
            if content.startswith(cmd):
                args = content[len(cmd):].strip().split(" ", 1)
                if len(args) < 2:
                    await message.reply(f"Usage: `{prefix}translate <target_lang> <text>`")
                    return
                target_lang, text_to_tr = args[0].lower(), args[1]
                async with message.channel.typing():
                    loop = asyncio.get_event_loop()
                    translated = await loop.run_in_executor(None, _translate, text_to_tr, target_lang)
                if translated:
                    detected = await loop.run_in_executor(None, _detect_lang, text_to_tr)
                    embed = discord.Embed(title="🌍 Translation Result", color=0x5865F2)
                    embed.add_field(name=f"Original ({detected})", value=text_to_tr,  inline=False)
                    embed.add_field(name=f"Translated ({target_lang})", value=translated, inline=False)
                    embed.set_footer(text="Translation Bot")
                    await message.reply(embed=embed)
                else:
                    await message.reply("Translation failed. Please try again later.")
                return

        if content in (f"{prefix}help",):
            embed = discord.Embed(title="🤖 Translation Bot — Help", color=0x5865F2)
            embed.add_field(
                name="Basic command",
                value=f"`{prefix}translate <lang> <text>` or `{prefix}tr <lang> <text>`",
                inline=False,
            )
            embed.add_field(
                name="Supported languages",
                value=", ".join(config["supportedLanguages"]),
                inline=False,
            )
            embed.add_field(name="Example", value=f"`{prefix}tr zh Hello world`", inline=False)
            await message.reply(embed=embed)

    try:
        _bot_loop.run_until_complete(_discord_client.start(config["discordToken"]))
    except Exception as e:
        print(f"[ERR ] Bot runtime error: {e}")
        config["botStatus"] = "error"


def start_bot() -> bool:
    global _bot_thread
    if not config.get("discordToken"):
        print("[WARN] Discord token not configured")
        return False
    if _bot_thread and _bot_thread.is_alive():
        print("[WARN] Bot is already running")
        return True
    _bot_thread = threading.Thread(target=_run_bot, daemon=True, name="discord-bot")
    _bot_thread.start()
    return True


def stop_bot() -> None:
    global _discord_client, _bot_thread, _bot_loop
    if _discord_client and _bot_loop:
        asyncio.run_coroutine_threadsafe(_discord_client.close(), _bot_loop)
    _discord_client = None
    _bot_thread     = None
    _bot_loop       = None
    config["botStatus"] = "offline"
    save_config()
    print("[BOT ] Bot stopped")


# ── Auth decorator ────────────────────────────────────────────────────
def require_admin(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("isAdmin"):
            return jsonify({"success": False, "message": "Admin privileges required"}), 403
        return fn(*args, **kwargs)
    return wrapper


# ── Routes ────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(".", "panel.html")

@app.route("/api/auth/check")
def auth_check():
    return jsonify({"isAdmin": bool(session.get("isAdmin"))})

@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json(silent=True) or request.form
    if data.get("password") == config["adminPassword"]:
        session.permanent = True
        session["isAdmin"] = True
        return jsonify({"success": True})
    return jsonify({"success": False})

@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    session.clear()
    return jsonify({"success": True})

@app.route("/api/auth/change-password", methods=["POST"])
@require_admin
def change_password():
    data   = request.get_json(silent=True) or request.form
    new_pw = (data.get("newPassword") or "").strip()
    if len(new_pw) < 6:
        return jsonify({"success": False, "message": "Password must be at least 6 characters"})
    config["adminPassword"] = new_pw
    save_config()
    session.clear()
    return jsonify({"success": True})

@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(config)

@app.route("/api/config", methods=["POST"])
@require_admin
def post_config():
    data = request.get_json(silent=True) or request.form
    config["discordToken"]    = (data.get("discordToken")    or "").strip()
    config["translateApiUrl"] = (data.get("translateApiUrl") or "https://libretranslate.com").strip()
    config["translateApiKey"] = (data.get("translateApiKey") or "").strip()
    config["commandPrefix"]   = (data.get("commandPrefix")   or "!").strip() or "!"
    raw = data.get("supportedLanguages") or "en"
    config["supportedLanguages"] = [l.strip() for l in raw.split(",") if l.strip()]
    save_config()
    return jsonify({"success": True})

@app.route("/api/bot/start", methods=["POST"])
@require_admin
def bot_start():
    if not DISCORD_AVAILABLE:
        return jsonify({"success": False, "message": "discord.py not installed."})
    if start_bot():
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Discord token not configured"})

@app.route("/api/bot/stop", methods=["POST"])
@require_admin
def bot_stop():
    stop_bot()
    return jsonify({"success": True})

@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(".", filename)


# ── Entry point ───────────────────────────────────────────────────────
if __name__ == "__main__":
    print("[NET ] Detecting public IP...")
    public_ip = get_public_ip()
    host = public_ip or "localhost"
    if public_ip:
        print(f"[NET ] Public IP detected: {public_ip}")
    else:
        print("[NET ] Could not detect public IP, using localhost")

    print()
    print("=" * 58)
    print("   🌸  Discord Translation Bot — Sakura Panel")
    print("=" * 58)
    print(f"  Web UI : http://{host}:{PORT}")
    print(f"  Local  : http://localhost:{PORT}")
    print("-" * 58)
    print(f"  Admin password : {config['adminPassword']}")
    print(f"  Token preview  : {config['discordToken'][:30]}...")
    print("-" * 58)
    print("  Tips:")
    print("    1. Log in with the admin password above")
    print("    2. Paste your real Discord Bot Token in the panel")
    print("    3. Change the admin password under Security Settings")
    print("    4. Config is stored in .cache/sub.txt")
    print()

    token = config.get("discordToken", "")
    if DISCORD_AVAILABLE and len(token) > 50 and "example" not in token.lower() \
            and config.get("botStatus") == "online":
        print("[BOT ] Saved token found — starting bot automatically...")
        start_bot()

    import logging
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)
    os.environ["WERKZEUG_RUN_MAIN"] = "true"
    cli = sys.modules.get("flask.cli")
    if cli:
        cli.show_server_banner = lambda *_: None

    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
