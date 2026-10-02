"""WSGI entry point.

Local dev:   python wsgi.py
Production:  gunicorn -c gunicorn.conf.py wsgi:app
"""
import socket

from dotenv import load_dotenv

# Load .env into the process environment if one exists next to this file. Real environment
# variables set by the shell or the hosting platform always win (override=False) -- .env is
# only a local-development convenience, never a production configuration source.
load_dotenv(override=False)

from app import create_app  # noqa: E402 - must import after load_dotenv()

app = create_app()


def _lan_ip() -> str | None:
    """Best-effort local network IP, so a phone on the same Wi-Fi can reach this server.

    Doesn't actually send any traffic -- UDP "connect" just asks the OS which local
    interface it would use to reach that address.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None


if __name__ == "__main__":
    port = 5000
    lan_ip = _lan_ip()
    print(f"\n  ClipFetch running:")
    print(f"    On this machine:        http://127.0.0.1:{port}")
    if lan_ip:
        print(f"    On your phone/Wi-Fi:    http://{lan_ip}:{port}")
    else:
        print("    (couldn't detect a LAN IP -- check you're connected to a network)")
    print("  Press CTRL+C to stop.\n")
    app.run(host="0.0.0.0", port=port,
            debug=(app.extensions["clipfetch"].config.env == "development"))

