"""
Phone camera gateway — lets a phone's browser stream its camera to VITALYN.

Why a separate listener: the main API has no authentication and stays bound to
127.0.0.1. Phones need to reach this Mac over Wi-Fi, so the only thing exposed to
the local network is THIS small app (one HTML page + one WebSocket), protected by
a random single-use-per-session link token. It is OFF unless started with
VITALYN_PHONE_GATEWAY=1.

Why HTTPS: phone browsers only allow camera access on secure pages. A self-signed
certificate is generated for the Mac's LAN address; the phone shows a one-time
"not private" warning that the user accepts (the video never leaves the local
network and nothing is stored).

Flow: the Live Camera page creates a link -> the phone opens it -> the page sends
JPEG frames over a WebSocket -> phone_source.PhoneSource -> live pipeline.
"""
from __future__ import annotations

import asyncio
import datetime
import html
import ipaddress
import logging
import os
import re
import socket
import sys
import threading
from typing import Dict, Optional

from fastapi import FastAPI, Request, WebSocket
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse

ML_ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "ml-engine")
if ML_ENGINE_PATH not in sys.path:
    sys.path.insert(0, ML_ENGINE_PATH)

from phone_source import get_registry  # noqa: E402

log = logging.getLogger("vitalyn.phone_gateway")

CERT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "certs")
DEFAULT_PORT = 8443


def gateway_enabled() -> bool:
    return os.getenv("VITALYN_PHONE_GATEWAY") == "1"


def detect_lan_ip() -> str:
    """This Mac's LAN address (override with VITALYN_PHONE_HOST)."""
    override = os.getenv("VITALYN_PHONE_HOST")
    if override:
        return override
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))      # no packet is sent; picks the outgoing interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def ensure_cert(host_ip: str, cert_dir: str = CERT_DIR):
    """Create (or reuse) a self-signed certificate valid for host_ip. Returns (cert, key) paths."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    os.makedirs(cert_dir, exist_ok=True)
    cert_path = os.path.join(cert_dir, "phone-gateway.crt")
    key_path = os.path.join(cert_dir, "phone-gateway.key")
    ip = ipaddress.ip_address(host_ip)

    if os.path.exists(cert_path) and os.path.exists(key_path):
        try:
            existing = x509.load_pem_x509_certificate(open(cert_path, "rb").read())
            san = existing.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            ips = san.get_values_for_type(x509.IPAddress)
            valid_for = existing.not_valid_after_utc - datetime.datetime.now(datetime.timezone.utc)
            # iOS needs the serverAuth extended key usage; older certs without it are replaced.
            eku = existing.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
            if (ip in ips and valid_for > datetime.timedelta(days=30)
                    and x509.oid.ExtendedKeyUsageOID.SERVER_AUTH in eku):
                return cert_path, key_path
        except Exception:
            pass  # regenerate below

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "VITALYN phone gateway")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ip), x509.DNSName("localhost")]),
            critical=False,
        )
        # iOS/Safari only accept a TLS server certificate that declares what it is for.
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
    return cert_path, key_path


# ── the phone-facing app ─────────────────────────────────────────────────────

PAGE_PATIENT = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VITALYN phone camera</title>
<style>
body{font-family:-apple-system,system-ui,sans-serif;margin:0;background:#0f172a;color:#e2e8f0;
display:flex;flex-direction:column;align-items:center;gap:14px;padding:20px;min-height:100vh;box-sizing:border-box}
h1{font-size:18px;margin:8px 0 0}p{font-size:13px;color:#94a3b8;text-align:center;max-width:340px;margin:0}
video{width:100%;max-width:420px;border-radius:12px;background:#000}
button{font-size:16px;font-weight:600;padding:14px 22px;border:0;border-radius:10px;background:#10b981;color:#fff;width:100%;max-width:420px}
#status{font-size:14px;font-weight:600;text-align:center}.live{color:#34d399}.bad{color:#f87171}
</style></head><body>
<h1>VITALYN phone camera</h1>
<p><b>__LABEL__</b></p>
<p>Video goes only to your Mac over this Wi-Fi. Nothing is stored on the phone or the Mac.</p>
<video id="v" playsinline muted autoplay></video>
<div id="status">Connecting...</div>
<button id="go" hidden>Start streaming</button>
<p>Prop the phone steady, keep this page open and the screen on. Staff start the camera from VITALYN.</p>
<script>
const v=document.getElementById("v"), st=document.getElementById("status"), go=document.getElementById("go");
const canvas=document.createElement("canvas");
let ws, stream=null, timer=null, wake=null, streaming=false, pingTimer=null, pendingServerStart=false;
function say(t,cls){ st.textContent=t; st.className=cls||""; }
function showGo(label){ go.hidden=false; go.disabled=false; go.textContent=label; }
function connect(){
  ws=new WebSocket("wss://"+location.host+"__WS_PATH__"); ws.binaryType="arraybuffer";
  ws.onopen=()=>{ say(streaming?"Streaming to VITALYN - keep this page open":"Connected - waiting for staff","live");
    clearInterval(pingTimer); pingTimer=setInterval(()=>{ if(ws.readyState===1) ws.send("ping"); },20000);
    if(streaming) loop(); };
  ws.onmessage=async(m)=>{
    const t=m.data; if(typeof t!=="string") return;
    if(t==="standby"){ endCamera(); say("Connected - waiting for staff","live"); showGo("Start streaming"); }
    else if(t==="live"||t==="start"){ if(!streaming) await beginCamera(true); }
    else if(t==="stop"){ endCamera(); say("Monitoring stopped - waiting for staff","live"); showGo("Start streaming"); }
    else if(t.startsWith("busy:")){ endCamera(); say(t.slice(5),"bad"); showGo("Start streaming"); }
  };
  ws.onclose=(e)=>{ clearInterval(pingTimer); clearTimeout(timer);
    if(e.code===4404){ endCamera(); go.hidden=true; say(e.reason||"This QR code is no longer valid - ask staff for a new one","bad"); return; }
    if(e.code===4409){ endCamera(); go.hidden=true; say(e.reason||"Camera is busy","bad"); return; }
    say("Connection lost - reconnecting...","bad"); setTimeout(connect,3000); };
}
async function beginCamera(fromServer){
  go.disabled=true; say("Opening camera...");
  try{ stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:"environment"},width:{ideal:1280},height:{ideal:720}},audio:false}); }
  catch(e){ stream=null; pendingServerStart=fromServer;
    showGo(fromServer?"Tap to resume camera":"Start streaming");
    say(fromServer?"Staff started monitoring - tap to resume the camera":"Camera blocked ("+e.name+"). Allow camera access and try again.","bad"); return; }
  v.srcObject=stream; await v.play().catch(()=>{});
  try{ wake=await navigator.wakeLock.request("screen"); }catch(e){}
  streaming=true; pendingServerStart=false; go.hidden=true; say("Streaming to VITALYN - keep this page open","live");
  if(!fromServer && ws && ws.readyState===1) ws.send("start_request");
  loop();
}
function endCamera(){ streaming=false; clearTimeout(timer); if(stream){ stream.getTracks().forEach(t=>t.stop()); stream=null; }
  v.srcObject=null; try{ if(wake) wake.release(); }catch(e){} wake=null; }
function loop(){
  if(!streaming||!ws||ws.readyState!==1) return;
  if(v.videoWidth && ws.bufferedAmount<400000){
    const w=Math.min(640,v.videoWidth), h=Math.round(v.videoHeight*w/v.videoWidth);
    canvas.width=w; canvas.height=h; canvas.getContext("2d").drawImage(v,0,0,w,h);
    canvas.toBlob(b=>{ if(b&&ws.readyState===1) b.arrayBuffer().then(buf=>ws.send(buf)); },"image/jpeg",0.6);
  }
  timer=setTimeout(loop,100);
}
go.onclick=()=>beginCamera(pendingServerStart);
document.addEventListener("visibilitychange",()=>{ if(!document.hidden&&streaming&&!wake){ navigator.wakeLock.request("screen").then(w=>{wake=w;}).catch(()=>{}); } });
connect();
</script></body></html>"""


gateway_app = FastAPI(title="VITALYN phone gateway", docs_url=None, redoc_url=None, openapi_url=None)


DISCONNECT_GRACE_S = 60       # how long a patient's session waits for a dropped phone before stopping


async def _reject(ws: WebSocket, code: int, reason: str) -> None:
    """Accept then close, so the phone's page receives the close code and reason."""
    await ws.accept()
    await ws.close(code=code, reason=reason[:120])


def _who(client, user_agent: str) -> str:
    host = client.host if client else "?"
    return f"{host} ({(user_agent or 'unknown browser')[:70]})"


# ── patient camera QR: /c/{token} ────────────────────────────────────────────
# The QR secret identifies an admitted patient. Scanning it starts monitoring for that
# patient and their room (one patient at a time). Logs show the patient CODE, never a name.

_patient_sources: Dict[str, str] = {}              # patient id -> registry token of the running phone source
_grace_timers: Dict[str, threading.Timer] = {}


def _lookup_patient(token: str) -> Optional[dict]:
    from sqlmodel import Session
    from database import engine
    from models import Room
    from patient_routes import find_patient_by_token

    with Session(engine) as session:
        patient = find_patient_by_token(session, token)
        if patient is None:
            return None
        room = session.get(Room, patient.room_id) if patient.room_id else None
        return {
            "id": str(patient.id),
            "code": patient.patient_code,
            "room_id": str(patient.room_id) if patient.room_id else None,
            "room_number": room.room_number if room else "-",
        }


def _ensure_patient_session(info: dict):
    """(PhoneSource, None) when this patient's session is ready/running, else (None, reason)."""
    import live_pipeline

    manager = live_pipeline.get_manager()
    registry = get_registry()
    existing_token = _patient_sources.get(info["id"])
    source = registry.get(existing_token) if existing_token else None
    if manager.get(info["id"]) is not None and source is not None:
        return source, None                                       # this patient is already monitored
    if not info["room_id"]:
        return None, "This patient has no room assigned."
    source = registry.create()
    try:
        manager.start(info["room_id"], f"phone:{source.token}", patient_id=info["id"])
    except Exception as exc:                                      # limit reached, camera error, ...
        registry.remove(source.token)
        return None, f"Could not start monitoring: {str(exc)[:100]}"
    _patient_sources[info["id"]] = source.token
    return source, None


def _arm_grace_timer(info: dict, source) -> None:
    """If the phone does not come back within the grace period, end the patient's session."""
    def expire():
        if source.connected:
            return
        try:
            import live_pipeline
            manager = live_pipeline.get_manager()
            if manager.get(info["id"]) is not None:
                print(f"[phone gateway] {info['code']}: phone did not return, stopping session", flush=True)
                manager.stop(patient_id=info["id"])
        finally:
            _grace_timers.pop(info["id"], None)

    old = _grace_timers.pop(info["id"], None)
    if old:
        old.cancel()
    timer = threading.Timer(DISCONNECT_GRACE_S, expire)
    timer.daemon = True
    _grace_timers[info["id"]] = timer
    timer.start()


@gateway_app.get("/c/{token}", response_class=HTMLResponse)
async def patient_page(token: str, request: Request):
    info = await run_in_threadpool(_lookup_patient, token)
    who = _who(request.client, request.headers.get("user-agent", ""))
    if info is None:
        print(f"[phone gateway] patient page REQUESTED WITH INVALID/REVOKED QR by {who}", flush=True)
        return HTMLResponse(
            "<body style='font-family:sans-serif;padding:24px'><h3>QR code no longer valid</h3>"
            "<p>Ask staff to generate a new one.</p></body>",
            status_code=404,
        )
    print(f"[phone gateway] page opened for {info['code']} by {who}", flush=True)
    label = f"Patient {info['code']} - Room {info['room_number']}"
    page = PAGE_PATIENT.replace("__LABEL__", html.escape(label)).replace("__WS_PATH__", f"/c/{token}/ws")
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})


# ── standby registry: phones that are online but not streaming ───────────────

class _Standby:
    """A phone connected for one patient. `source` is set while a monitoring session uses it."""

    def __init__(self, ws: WebSocket, loop, info: dict, label: str):
        self.ws = ws
        self.loop = loop
        self.info = info
        self.label = label
        self.source = None


_standby: Dict[str, _Standby] = {}                 # patient id -> connected phone


def phone_online(patient_id: str) -> bool:
    return patient_id in _standby


def _send_to_phone(entry: _Standby, text: str, timeout: float = 3.0) -> None:
    """Thread-safe: the gateway runs its own event loop in its own thread."""
    asyncio.run_coroutine_threadsafe(entry.ws.send_text(text), entry.loop).result(timeout)


def start_phone_monitoring(info: dict):
    """Called by the main API: begin the patient's session and tell their phone to start the camera."""
    entry = _standby.get(info["id"])
    if entry is None:
        return False, "The registered phone is offline."
    source, error = _ensure_patient_session(info)
    if source is None:
        return False, error or "Cannot start monitoring"
    source.set_connected(True)
    entry.source = source
    try:
        _send_to_phone(entry, "start")
    except Exception as exc:
        return False, f"Could not reach the phone: {str(exc)[:80]}"
    return True, ""


def kick_standby(patient_id: str, reason: str) -> bool:
    """Disconnect the patient's phone (QR replaced, discharged, camera unregistered)."""
    entry = _standby.pop(patient_id, None)
    if entry is None:
        return False
    try:
        asyncio.run_coroutine_threadsafe(entry.ws.close(code=4404, reason=reason[:120]), entry.loop).result(3.0)
    except Exception:
        pass
    return True


def _device_label(user_agent: str) -> str:
    ua = user_agent or ""
    m = re.search(r"iPhone OS (\d+)", ua)
    if m:
        return f"iPhone (iOS {m.group(1)})"
    m = re.search(r"CPU OS (\d+)", ua)
    if "iPad" in ua and m:
        return f"iPad (iPadOS {m.group(1)})"
    m = re.search(r"Android (\d+)", ua)
    if m:
        return f"Android phone ({m.group(1)})"
    return "Phone browser"


def _register_phone(patient_id: str, label: str) -> None:
    """Remember that this patient's camera is a phone (set when the phone connects with their QR)."""
    import uuid as _uuid
    from datetime import datetime, timezone
    from sqlmodel import Session
    from database import engine
    from models import Patient

    with Session(engine) as session:
        patient = session.get(Patient, _uuid.UUID(patient_id))
        if patient is None:
            return
        if patient.camera_kind != "phone" or patient.camera_registered_at is None:
            patient.camera_registered_at = datetime.now(timezone.utc)
        patient.camera_kind = "phone"
        patient.camera_index = None
        patient.camera_label = label
        session.add(patient)
        session.commit()


@gateway_app.websocket("/c/{token}/ws")
async def patient_ws(ws: WebSocket, token: str):
    info = await run_in_threadpool(_lookup_patient, token)
    if info is None:
        await _reject(ws, 4404, "QR code no longer valid")
        return
    pid = info["id"]
    if pid in _standby:
        await _reject(ws, 4409, "A phone is already connected for this patient")
        return

    await ws.accept()
    label = _device_label(ws.headers.get("user-agent", ""))
    entry = _Standby(ws, asyncio.get_running_loop(), info, label)
    _standby[pid] = entry
    await run_in_threadpool(_register_phone, pid, label)

    timer = _grace_timers.pop(pid, None)
    if timer:
        timer.cancel()
    # Reconnecting mid-session (network blip): re-attach to the running session.
    token_in_use = _patient_sources.get(pid)
    resumed = get_registry().get(token_in_use) if token_in_use else None
    if resumed is not None and resumed.isOpened():
        entry.source = resumed
        resumed.set_connected(True)
    await ws.send_text("live" if entry.source is not None else "standby")
    print(f"[phone gateway] {info['code']}: phone online ({label})", flush=True)

    try:
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=1.0)
            except asyncio.TimeoutError:
                msg = None
            if msg is not None:
                if msg["type"] == "websocket.disconnect":
                    break
                data, text = msg.get("bytes"), msg.get("text")
                if data and entry.source is not None:
                    entry.source.push_jpeg(data)
                elif text == "start_request":                    # the user tapped Start on the phone
                    source, error = await run_in_threadpool(_ensure_patient_session, info)
                    if source is None:
                        await ws.send_text("busy:" + (error or "Cannot start monitoring"))
                    else:
                        source.set_connected(True)
                        entry.source = source
            if entry.source is not None and not entry.source.isOpened():     # session ended on the Mac
                entry.source = None
                _patient_sources.pop(pid, None)
                await ws.send_text("stop")
    finally:
        if _standby.get(pid) is entry:
            _standby.pop(pid, None)
        if entry.source is not None:
            entry.source.set_connected(False)
            _arm_grace_timer(info, entry.source)
        print(f"[phone gateway] {info['code']}: phone offline", flush=True)


# ── lifecycle ────────────────────────────────────────────────────────────────

class PhoneGateway:
    def __init__(self):
        self.server = None
        self.thread: Optional[threading.Thread] = None
        self.host_ip: Optional[str] = None
        self.port = DEFAULT_PORT

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def base_url(self) -> Optional[str]:
        return f"https://{self.host_ip}:{self.port}" if self.running else None

    def start(self, port: int = DEFAULT_PORT) -> None:
        import uvicorn
        if self.running:
            return
        self.port = int(os.getenv("VITALYN_PHONE_PORT", port))
        self.host_ip = detect_lan_ip()
        cert, key = ensure_cert(self.host_ip)
        config = uvicorn.Config(
            gateway_app, host="0.0.0.0", port=self.port,
            ssl_certfile=cert, ssl_keyfile=key, log_level="warning",
        )
        self.server = uvicorn.Server(config)
        self.server.install_signal_handlers = lambda: None     # not the main thread
        self.thread = threading.Thread(target=self.server.run, name="phone-gateway", daemon=True)
        self.thread.start()
        threading.Thread(target=self._warm_up, name="live-warmup", daemon=True).start()
        log.info("Phone gateway listening on %s", self.base_url())

    @staticmethod
    def _warm_up() -> None:
        """Import the heavy ML modules now so the first QR scan does not wait for them."""
        try:
            import live_pipeline  # noqa: F401
        except Exception as exc:
            print(f"[phone gateway] live pipeline not available: {exc}", flush=True)

    def stop(self) -> None:
        if self.server is not None:
            self.server.should_exit = True
        if self.thread is not None:
            self.thread.join(timeout=5)


_gateway = PhoneGateway()


def get_gateway() -> PhoneGateway:
    return _gateway
