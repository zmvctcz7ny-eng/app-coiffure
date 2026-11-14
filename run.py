"""Lance DocEdit : serveur web accessible depuis cet ordinateur et depuis les téléphones du même Wi-Fi."""
from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import ipaddress
import os
import socket
import sys
import threading
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
DATA = os.path.join(ROOT, "data")

HTTP_PORT = int(os.environ.get("DOCEDIT_PORT", "8000"))
HTTPS_PORT = int(os.environ.get("DOCEDIT_HTTPS_PORT", "8443"))


def lan_ip() -> str:
    """Adresse de l'ordinateur sur le réseau local (Wi-Fi)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.254.254.254", 1))  # aucun paquet n'est envoyé
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def free_port(preferred: int) -> int:
    for port in range(preferred, preferred + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    raise SystemExit("Aucun port réseau libre n'a été trouvé. Fermez les autres programmes et réessayez.")


def make_certificate(ip: str) -> tuple[str, str] | None:
    """Certificat auto-signé pour l'adresse https:// (caméra en direct et installation sur téléphone)."""
    cert_dir = os.path.join(DATA, "certificat")
    os.makedirs(cert_dir, exist_ok=True)
    cert, key = os.path.join(cert_dir, "cert.pem"), os.path.join(cert_dir, "cle.pem")
    stamp = os.path.join(cert_dir, "ip.txt")
    if os.path.exists(cert) and os.path.exists(key) and os.path.exists(stamp):
        with open(stamp) as f:
            if f.read().strip() == ip:
                return cert, key
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        return None
    pk = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "DocEdit (ordinateur local)")])
    alt = [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
    with contextlib.suppress(ValueError):
        alt.append(x509.IPAddress(ipaddress.ip_address(ip)))
    now = dt.datetime.now(dt.timezone.utc)
    crt = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(pk.public_key())
           .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
           .not_valid_after(now + dt.timedelta(days=825))
           .add_extension(x509.SubjectAlternativeName(alt), critical=False)
           .sign(pk, hashes.SHA256()))
    with open(key, "wb") as f:
        f.write(pk.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                 serialization.NoEncryption()))
    with open(cert, "wb") as f:
        f.write(crt.public_bytes(serialization.Encoding.PEM))
    with open(stamp, "w") as f:
        f.write(ip)
    return cert, key


def print_qr(url: str):
    try:
        import qrcode

        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        try:
            qr.print_ascii(invert=True)
        except UnicodeEncodeError:  # console Windows ancienne
            qr.print_tty() if sys.stdout.isatty() else None
    except Exception:
        pass


def banner(local: str, lan: str, lan_https: str | None, ocr_msg: str | None):
    line = "=" * 64
    print("\n" + line)
    print("  DocEdit est lancé !")
    print(line)
    print(f"  Sur cet ordinateur :   {local}")
    print(f"  Sur votre téléphone :  {lan}")
    print("     (le téléphone doit être sur le même Wi-Fi que cet ordinateur)")
    if lan_https:
        print(f"  Adresse sécurisée :    {lan_https}")
        print("     (pour la caméra en direct et l'installation sur téléphone :")
        print("      acceptez l'avertissement de sécurité, c'est votre propre ordinateur)")
    print("\n  Scannez ce QR code avec l'appareil photo de votre téléphone :\n")
    print_qr(lan)
    if ocr_msg:
        print("  ATTENTION : " + ocr_msg + "\n")
    print("  Pour arrêter DocEdit : fermez cette fenêtre ou appuyez sur Ctrl+C.")
    print(line + "\n", flush=True)


async def serve_all(servers):
    tasks = [asyncio.ensure_future(s.serve()) for s in servers]
    try:
        await asyncio.gather(*tasks)
    finally:
        for s in servers:
            s.should_exit = True


def main():
    if sys.version_info < (3, 9):
        raise SystemExit("DocEdit a besoin de Python 3.9 ou plus récent.")
    try:
        import uvicorn

        from docedit import ocr
        from docedit.server import app
    except ImportError as e:
        raise SystemExit(f"Il manque un composant ({e.name}). Lancez DocEdit avec start.sh ou start.bat, "
                         "qui installe tout automatiquement.")

    ip = lan_ip()
    http_port = free_port(HTTP_PORT)
    local = f"http://localhost:{http_port}"
    lan = f"http://{ip}:{http_port}"
    os.environ["DOCEDIT_LAN_URL"] = lan

    configs = [uvicorn.Config(app, host="0.0.0.0", port=http_port, log_level="warning")]
    lan_https = None
    if os.environ.get("DOCEDIT_NO_HTTPS") != "1":
        certs = make_certificate(ip)
        if certs:
            https_port = free_port(HTTPS_PORT)
            lan_https = f"https://{ip}:{https_port}"
            os.environ["DOCEDIT_LAN_URL_HTTPS"] = lan_https
            configs.append(uvicorn.Config(app, host="0.0.0.0", port=https_port, log_level="warning",
                                          ssl_certfile=certs[0], ssl_keyfile=certs[1]))

    servers = []
    for cfg in configs:
        srv = uvicorn.Server(cfg)
        srv.capture_signals = contextlib.nullcontext  # Ctrl+C géré ci-dessous pour les deux serveurs
        servers.append(srv)

    banner(local, lan, lan_https, ocr.status()["message"])
    if os.environ.get("DOCEDIT_NO_BROWSER") != "1":
        threading.Timer(1.5, lambda: webbrowser.open(local)).start()
    import signal

    def stop(*_):
        for s in servers:
            s.should_exit = True

    signal.signal(signal.SIGINT, stop)
    with contextlib.suppress(AttributeError, ValueError):
        signal.signal(signal.SIGTERM, stop)
    try:
        asyncio.run(serve_all(servers))
    except KeyboardInterrupt:
        pass
    print("\nDocEdit est arrêté. À bientôt !")


if __name__ == "__main__":
    main()
