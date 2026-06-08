"""3D Workshop — REST API for parametric CAD generation and mesh processing."""

import base64
import io
import json
import os
import re
import subprocess
import tempfile
import threading
import traceback
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import BaseModel
import uvicorn
import ssl
import ftplib
import socket
import zipfile
import secrets
import hashlib

# Constants for print job handling
PRINT_JOB_TIMEOUT_SECONDS = 30

class ImplicitFTP_TLS(ftplib.FTP_TLS):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sock = None

    @property
    def sock(self):
        return self._sock

    @sock.setter
    def sock(self, value):
        if value is not None and not isinstance(value, ssl.SSLSocket):
            value = self.context.wrap_socket(value, server_hostname=self.host)
        self._sock = value

WORKSHOP_PASSWORD = os.environ.get("WORKSHOP_PASSWORD")
SKIP_TEST_PRINT = os.environ.get("SKIP_TEST_PRINT", "true").lower() == "true"

def get_expected_token():
    return hashlib.sha256(f"workshop_token_{WORKSHOP_PASSWORD}".encode()).hexdigest()

def validate_subfolder(subfolder: str) -> tuple[bool, str | None, str]:
    """Validate subfolder path safety.

    Returns: (is_valid, error_msg, safe_path)
    - is_valid: True if path is safe, False otherwise
    - error_msg: Error message if invalid, None if valid
    - safe_path: Normalized safe path within MODELS_DIR, empty string if invalid
    """
    subfolder = subfolder.strip() if subfolder else ""

    # Block ".." path traversal attempts
    if ".." in subfolder:
        return False, "Invalid folder name: path traversal not allowed", ""

    # Replace disallowed characters with underscores
    safe = re.sub(r'[^a-zA-Z0-9\-_/]', '_', subfolder)

    # Ensure the final path stays within MODELS_DIR
    target_dir = os.path.join(MODELS_DIR, safe) if safe else MODELS_DIR
    target_dir = os.path.normpath(target_dir)

    # Verify the normalized path still starts with MODELS_DIR
    if not target_dir.startswith(MODELS_DIR):
        return False, "Invalid folder path", ""

    return True, None, target_dir

app = FastAPI(title="3D Workshop", version="1.0.0")

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if not WORKSHOP_PASSWORD:
        return await call_next(request)
        
    path = request.url.path
    if path in ["/", "/studio", "/auth/login", "/auth/status", "/health"]:
        return await call_next(request)
        
    workshop_session = request.cookies.get("workshop_session")
    if not workshop_session or not secrets.compare_digest(workshop_session, get_expected_token()):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
        
    return await call_next(request)

class LoginRequest(BaseModel):
    password: str

@app.post("/auth/login")
def auth_login(req: LoginRequest, response: Response):
    if not WORKSHOP_PASSWORD or req.password == WORKSHOP_PASSWORD:
        response.set_cookie(key="workshop_session", value=get_expected_token(), httponly=True, max_age=86400*30)
        return {"success": True}
    raise HTTPException(401, "Invalid password")

@app.get("/auth/status")
def auth_status(request: Request):
    if not WORKSHOP_PASSWORD:
        return {"authenticated": True, "enabled": False}
    workshop_session = request.cookies.get("workshop_session")
    is_auth = bool(workshop_session and secrets.compare_digest(workshop_session, get_expected_token()))
    return {"authenticated": is_auth, "enabled": True}

MODELS_DIR = os.environ.get("MODELS_DIR", "/models")
PORT = int(os.environ.get("WORKSHOP_PORT", "3215"))


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class CadQueryRequest(BaseModel):
    script: str
    output_format: str = "stl"  # stl, step, amf


class OpenSCADRequest(BaseModel):
    script: str
    output_format: str = "stl"  # stl, off, amf, 3mf, csg, dxf, svg, pdf
    parameters: dict | None = None  # -D overrides


class MeshInfoRequest(BaseModel):
    file_base64: str
    filename: str


class MeshTransformRequest(BaseModel):
    file_base64: str
    filename: str
    operations: list[dict]  # [{"op": "scale", "factor": 1.5}, {"op": "translate", "x": 10}]
    output_format: str = "stl"


class MeshRepairRequest(BaseModel):
    file_base64: str
    filename: str
    output_format: str = "stl"


class MeshCombineRequest(BaseModel):
    files: list[dict]  # [{"file_base64": "...", "filename": "..."}]
    output_format: str = "stl"


class MeshSliceRequest(BaseModel):
    file_base64: str
    filename: str
    plane_origin: list[float] = [0, 0, 0]
    plane_normal: list[float] = [0, 0, 1]
    keep: str = "above"  # above, below, both
    output_format: str = "stl"


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/studio")


@app.get("/ai/status")
async def ai_status():
    """Check which API keys are configured on the server."""
    return {
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "gemini": bool(os.environ.get("GEMINI_API_KEY"))
    }


class ChatMessage(BaseModel):
    role: str  # 'user' or 'assistant'
    content: str

class ChatRequest(BaseModel):
    prompt: str | None = None
    messages: list[ChatMessage] | None = None
    provider: str = "ollama"  # ollama, openai, anthropic, gemini
    model: str = "qwen2.5:7b"
    api_key: str | None = None
    system_prompt: str | None = None


@app.post("/ai/chat")
async def ai_chat(req: ChatRequest):
    """Proxy prompts to either local Ollama or commercial APIs (OpenAI/Anthropic/Gemini)."""
    import httpx
    
    sys_prompt = req.system_prompt or (
        "You are an expert 3D design AI assistant. Your goal is to write code for OpenSCAD, CadQuery, or Build123d "
        "to generate 3D models.\n"
        "IMPORTANT WORKFLOW RULES:\n"
        "1. Be highly interactive. Before writing ANY code, ask clarifying questions to nail down the exact specifications and design requirements.\n"
        "2. ONLY output the script code block when the user explicitly confirms they are ready or when the requirements are crystal clear.\n"
        "3. When you DO write code, for Build123d: import 'build123d as bd' and ALWAYS assign the final shape to 'result'.\n"
        "4. Wrap your script in standard markdown code blocks (e.g. ```openscad or ```python)."
    )
    
    try:
        # Build the conversation list
        convo_messages = []
        if req.messages and len(req.messages) > 0:
            for m in req.messages:
                convo_messages.append({"role": m.role, "content": m.content})
        elif req.prompt:
            convo_messages.append({"role": "user", "content": req.prompt})
        else:
            raise HTTPException(400, "Must provide either prompt or messages")

        async with httpx.AsyncClient(timeout=120.0) as client:
            if req.provider == "ollama":
                ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
                payload_msgs = [{"role": "system", "content": sys_prompt}] + convo_messages
                resp = await client.post(f"{ollama_url}/api/chat", json={
                    "model": req.model,
                    "messages": payload_msgs,
                    "stream": False
                })
                resp.raise_for_status()
                data = resp.json()
                return {"success": True, "message": data["message"]["content"]}
                
            elif req.provider == "openai":
                api_key = req.api_key or os.environ.get("OPENAI_API_KEY")
                if not api_key:
                    raise HTTPException(400, "OpenAI API key is missing")
                payload_msgs = [{"role": "system", "content": sys_prompt}] + convo_messages
                resp = await client.post("https://api.openai.com/v1/chat/completions", headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }, json={
                    "model": req.model,
                    "messages": payload_msgs
                })
                resp.raise_for_status()
                data = resp.json()
                return {"success": True, "message": data["choices"][0]["message"]["content"]}
                
            elif req.provider == "anthropic":
                api_key = req.api_key or os.environ.get("ANTHROPIC_API_KEY")
                if not api_key:
                    raise HTTPException(400, "Anthropic API key is missing")
                resp = await client.post("https://api.anthropic.com/v1/messages", headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                }, json={
                    "model": req.model,
                    "max_tokens": 4096,
                    "system": sys_prompt,
                    "messages": convo_messages
                })
                resp.raise_for_status()
                data = resp.json()
                return {"success": True, "message": data["content"][0]["text"]}
                
            elif req.provider == "gemini":
                api_key = req.api_key or os.environ.get("GEMINI_API_KEY")
                if not api_key:
                    raise HTTPException(400, "Gemini API key is missing")
                gemini_model = req.model
                if gemini_model == "gemini-1.5-pro":
                    gemini_model = "gemini-1.5-pro-latest"
                elif gemini_model == "gemini-1.5-flash":
                    gemini_model = "gemini-1.5-flash-latest"
                elif gemini_model == "gemini-2.0-flash":
                    gemini_model = "gemini-2.0-flash"
                elif gemini_model == "gemini-2.5-pro":
                    gemini_model = "gemini-2.5-pro"
                
                # Gemini roles must be 'user' or 'model'
                gemini_contents = []
                for msg in convo_messages:
                    r = "model" if msg["role"] == "assistant" else "user"
                    gemini_contents.append({
                        "role": r,
                        "parts": [{"text": msg["content"]}]
                    })

                url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={api_key}"
                resp = await client.post(url, headers={
                    "Content-Type": "application/json"
                }, json={
                    "systemInstruction": {"parts": [{"text": sys_prompt}]},
                    "contents": gemini_contents
                })
                resp.raise_for_status()
                data = resp.json()
                return {"success": True, "message": data["candidates"][0]["content"]["parts"][0]["text"]}
                
            else:
                raise HTTPException(400, f"Unsupported provider: {req.provider}")
                
    except httpx.HTTPStatusError as e:
        # SECURITY: Never echo the upstream error body — it can contain the user's
        # API key. Return only the status code and a generic message.
        return {"success": False, "error": f"API Error ({e.response.status_code}): [authentication or request failed]"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/printer/status")
async def printer_status():
    """Check if Bambu Lab printer environment variables are set and the printer is reachable."""
    import socket
    printer_ip = os.environ.get("BAMBU_PRINTER_IP")
    serial_number = os.environ.get("BAMBU_PRINTER_SERIAL")
    access_code = os.environ.get("BAMBU_PRINTER_ACCESS_CODE")
    
    configured = bool(printer_ip and serial_number and access_code)
    online = False
    
    if configured:
        # Quick TCP check on MQTT port (8883) or FTPS port (990)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1.0)
            s.connect((printer_ip, 990))
            s.close()
            online = True
        except Exception:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1.0)
                s.connect((printer_ip, 8883))
                s.close()
                online = True
            except Exception:
                online = False
                
    return {
        "configured": configured,
        "online": online,
        "ip": printer_ip or "",
        "serial": serial_number or "",
        "has_access_code": bool(access_code)
    }


class PrintRequest(BaseModel):
    file_base64: str
    filename: str
    filament: str = "PLA"
    nozzle_temp: int = 220
    bed_temp: int = 35
    perimeters: int = 3
    plate_type: str = "cool"
    ams_slot: int = -1
    printer_model: str = "a1_mini"


@app.post("/printer/print")
def printer_print(req: PrintRequest):
    """Slice the STL file, package as .gcode.3mf, upload to Bambu printer, and trigger the print.
    Returns structured error responses with step context on failure."""
    import ssl
    import ftplib
    import zipfile
    import paho.mqtt.client as mqtt
    import trimesh

    # Timeout handling with threading.Timer (safe with WSGI/Gunicorn, no signal interference)
    timeout_fired = False
    timer = None

    def timeout_callback():
        nonlocal timeout_fired
        timeout_fired = True

    timer = threading.Timer(PRINT_JOB_TIMEOUT_SECONDS, timeout_callback)
    timer.daemon = True
    timer.start()

    # Connection variables for proper cleanup in finally block
    mqtt_client = None
    ftp_conn = None

    # Get printer configuration
    printer_ip = os.environ.get("BAMBU_PRINTER_IP")
    serial_number = os.environ.get("BAMBU_PRINTER_SERIAL")
    access_code = os.environ.get("BAMBU_PRINTER_ACCESS_CODE")

    if not printer_ip or not serial_number or not access_code:
        raise HTTPException(500, "Bambu Lab printer environment variables are not set in docker-compose.yml")

    try:
        # Step 1: Decode STL base64
        try:
            stl_bytes = base64.b64decode(req.file_base64)
        except Exception as e:
            return {"success": False, "step": "base64_decode", "error": "Failed to decode base64 file", "details": str(e)}

        # Step 2: Load mesh and auto-rotate to lie flat on the bed
        try:
            mesh = _load_mesh(stl_bytes, req.filename)
        except Exception as e:
            return {"success": False, "step": "mesh_load", "error": "Failed to load mesh file", "details": str(e)}
        
        # Auto-rotate to lie flat:
        
        # Translate so bottom of bounding box is at Z=0 and centered in X/Y
        bounds = mesh.bounds
        z_min = bounds[0][2]
        center_xy = 128.0 if req.printer_model in ["x1c", "p1"] else 90.0
        mesh.apply_translation([-mesh.centroid[0] + center_xy, -mesh.centroid[1] + center_xy, -z_min])
        
        # Save rotated mesh to temporary STL
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp_stl:
            tmp_stl_name = tmp_stl.name
        mesh.export(tmp_stl_name, file_type="stl")
        
        # Step 3: Run PrusaSlicer CLI to slice STL
        with tempfile.NamedTemporaryFile(suffix=".gcode", delete=False) as tmp_gcode:
            tmp_gcode_name = tmp_gcode.name
            
        try:
            # Load the appropriate .ini file based on selected printer
            if req.printer_model == "x1c":
                base_ini = "bambu_x1c_pla.ini"
            elif req.printer_model == "p1":
                base_ini = "bambu_p1_pla.ini"
            else:
                base_ini = "bambu_a1_mini_pla.ini"
            
            # Ensure profiles directory exists in persistent storage
            profiles_dir = os.path.join(MODELS_DIR, "profiles")
            os.makedirs(profiles_dir, exist_ok=True)
            
            user_ini = os.path.join(profiles_dir, f"user_{base_ini}")
            default_export_ini = os.path.join(profiles_dir, f"default_{base_ini}")
            
            # Keep the default profile exported so users can reference it
            if not os.path.exists(default_export_ini):
                import shutil
                shutil.copy(base_ini, default_export_ini)
            
            # Read from user_ini if it exists, otherwise fallback to the default base_ini
            ini_to_use = user_ini if os.path.exists(user_ini) else base_ini
            
            # Read and patch the ini file dynamically
            with open(ini_to_use, 'r') as f:
                ini_content = f.read()
                
            z_offset = "0" if req.plate_type == "cool" else "-0.04"
            
            ini_content = re.sub(r'^z_offset\s*=\s*.*', f'z_offset = {z_offset}', ini_content, flags=re.MULTILINE)
            ini_content = re.sub(r'^temperature\s*=\s*.*', f'temperature = {req.nozzle_temp}', ini_content, flags=re.MULTILINE)
            ini_content = re.sub(r'^first_layer_temperature\s*=\s*.*', f'first_layer_temperature = {req.nozzle_temp}', ini_content, flags=re.MULTILINE)
            ini_content = re.sub(r'^bed_temperature\s*=\s*.*', f'bed_temperature = {req.bed_temp}', ini_content, flags=re.MULTILINE)
            ini_content = re.sub(r'^first_layer_bed_temperature\s*=\s*.*', f'first_layer_bed_temperature = {req.bed_temp}', ini_content, flags=re.MULTILINE)
            ini_content = re.sub(r'^perimeters\s*=\s*.*', f'perimeters = {req.perimeters}', ini_content, flags=re.MULTILINE)
            
            tmp_ini_name = tmp_gcode_name.replace(".gcode", ".ini")
            with open(tmp_ini_name, 'w') as f:
                f.write(ini_content)
            
            # Check timeout before slicing operation
            if timeout_fired:
                raise TimeoutError(f"Print job request timed out after {PRINT_JOB_TIMEOUT_SECONDS} seconds")

            cmd = [
                "prusa-slicer",
                "--load", tmp_ini_name,
                "--output", tmp_gcode_name,
                "-g", tmp_stl_name
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if os.path.exists(tmp_ini_name):
                os.remove(tmp_ini_name)
            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "Unknown slicing error"
                return {"success": False, "step": "slicing", "error": "Failed to slice STL file", "details": error_msg}
                
            # Step 4: Package G-code to a .gcode.3mf zip file
            # Always use a fixed filename on the printer SD card so the printer never
            # auto-resumes a stale job — each print overwrites the previous one.
            gcode_3mf_name = "workshop_current.gcode.3mf"
            
            with tempfile.NamedTemporaryFile(suffix=".3mf", delete=False) as tmp_3mf:
                tmp_3mf_name = tmp_3mf.name
                
            try:
                with zipfile.ZipFile(tmp_3mf_name, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    zip_file.write(tmp_gcode_name, "Metadata/plate_1.gcode")
                    
                # Check timeout before FTP upload
                if timeout_fired:
                    raise TimeoutError(f"Print job request timed out after {PRINT_JOB_TIMEOUT_SECONDS} seconds")

                # Step 5: Upload to printer's SD card via FTPS (Implicit TLS on port 990)
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

                ftp_conn = ImplicitFTP_TLS(context=ssl_context)
                ftp_conn.connect(printer_ip, port=990, timeout=15)
                ftp_conn.login(user="bblp", passwd=access_code)
                ftp_conn.prot_p()

                def storbinary_custom(cmd, fp, blocksize=8192):
                    ftp_conn.voidcmd("TYPE I")
                    with ftp_conn.transfercmd(cmd, None) as conn:
                        while 1:
                            buf = fp.read(blocksize)
                            if not buf:
                                break
                            conn.sendall(buf)
                        try:
                            conn.unwrap()
                        except Exception:
                            pass
                    return ftp_conn.voidresp()

                try:
                    with open(tmp_3mf_name, "rb") as f:
                        storbinary_custom(f"STOR {gcode_3mf_name}", f)
                    if ftp_conn:
                        ftp_conn.quit()
                        ftp_conn = None
                except Exception as e:
                    return {"success": False, "step": "ftp_upload", "error": "Failed to upload to printer", "details": f"FTPS upload error: {str(e)}"}
                
                # Check timeout before MQTT connect
                if timeout_fired:
                    raise TimeoutError(f"Print job request timed out after {PRINT_JOB_TIMEOUT_SECONDS} seconds")

                # Step 6: Trigger the print via MQTT
                mqtt_client = mqtt.Client(client_id="workshop_studio_print", transport="tcp")
                mqtt_client.username_pw_set("bblp", access_code)
                mqtt_client.tls_set_context(ssl_context)

                mqtt_connected = False
                def on_connect(c, userdata, flags, rc):
                    nonlocal mqtt_connected
                    if rc == 0:
                        mqtt_connected = True
                mqtt_client.on_connect = on_connect

                try:
                    mqtt_client.connect(printer_ip, port=8883, keepalive=60)
                    mqtt_client.loop_start()

                    import time
                    start_time = time.time()
                    while not mqtt_connected and (time.time() - start_time) < 5:
                        time.sleep(0.1)

                    if not mqtt_connected:
                        return {"success": False, "step": "mqtt_connect", "error": "Failed to connect to printer", "details": "MQTT broker connection timeout after 5s"}
                except Exception as e:
                    return {"success": False, "step": "mqtt_connect", "error": "Failed to connect to printer", "details": f"MQTT error: {str(e)}"}
                    
                payload = {
                    "print": {
                        "sequence_id": str(int(time.time())),
                        "command": "project_file",
                        "param": "Metadata/plate_1.gcode",
                        "url": f"file:///sdcard/{gcode_3mf_name}",
                        "subtask_name": gcode_3mf_name,
                        "bed_leveling": True,
                        "flow_cali": False,
                        "timelapse": False,
                        "use_ams": req.ams_slot >= 0
                    }
                }
                
                if req.ams_slot >= 0:
                    payload["print"]["ams_mapping"] = [req.ams_slot]
                
                try:
                    info = mqtt_client.publish(f"device/{serial_number}/request", json.dumps(payload), qos=1)
                    info.wait_for_publish()

                    mqtt_client.loop_stop()
                    mqtt_client.disconnect()
                    mqtt_client = None

                    return {
                        "success": True,
                        "step": "mqtt_publish",
                        "message": f"Print job '{gcode_3mf_name}' successfully sent to Bambu printer!",
                        "filename": gcode_3mf_name
                    }
                except Exception as e:
                    return {"success": False, "step": "mqtt_publish", "error": "Failed to queue print job", "details": f"MQTT publish error: {str(e)}"}
                
            finally:
                if os.path.exists(tmp_3mf_name):
                    os.remove(tmp_3mf_name)
        finally:
            if os.path.exists(tmp_stl_name):
                os.remove(tmp_stl_name)
            if os.path.exists(tmp_gcode_name):
                os.remove(tmp_gcode_name)

    except TimeoutError as e:
        return {"success": False, "step": "timeout", "error": "Print job request timed out", "details": f"Operation exceeded {PRINT_JOB_TIMEOUT_SECONDS} second limit"}
    except Exception as e:
        # Return generic error if step context is not available
        return {"success": False, "step": "unknown", "error": "Print job failed", "details": str(e)}
    finally:
        # Ensure timeout timer is canceled and resources are cleaned up
        if timer:
            timer.cancel()
        if mqtt_client:
            try:
                mqtt_client.loop_stop()
                mqtt_client.disconnect()
            except Exception:
                pass
        if ftp_conn:
            try:
                ftp_conn.quit()
            except Exception:
                pass


@app.post("/printer/cancel")
async def printer_cancel():
    """Cancel the current print job on the Bambu printer."""
    try:
        printer_ip = os.environ.get("BAMBU_PRINTER_IP")
        access_code = os.environ.get("BAMBU_PRINTER_ACCESS_CODE")
        serial_number = os.environ.get("BAMBU_PRINTER_SERIAL")
        
        if not all([printer_ip, access_code, serial_number]):
            raise Exception("Printer credentials not fully configured in environment variables.")
            
        import paho.mqtt.client as mqtt
        import ssl
        import time
        import json
        
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        client = mqtt.Client(client_id="workshop_studio_cancel", transport="tcp")
        client.username_pw_set("bblp", access_code)
        client.tls_set_context(ssl_context)
        
        mqtt_connected = False
        def on_connect(c, userdata, flags, rc):
            nonlocal mqtt_connected
            if rc == 0:
                mqtt_connected = True
        client.on_connect = on_connect
        
        client.connect(printer_ip, port=8883, keepalive=60)
        client.loop_start()
        
        start_time = time.time()
        while not mqtt_connected and (time.time() - start_time) < 5:
            time.sleep(0.1)
            
        if not mqtt_connected:
            raise Exception("Failed to connect to printer MQTT broker")
            
        payload = {
            "print": {
                "sequence_id": str(int(time.time())),
                "command": "stop"
            }
        }
        
        info = client.publish(f"device/{serial_number}/request", json.dumps(payload), qos=1)
        info.wait_for_publish()
        
        client.loop_stop()
        client.disconnect()
        
        return {
            "success": True,
            "message": "Stop command sent to printer!"
        }
    except Exception as e:
        import traceback
        return {"success": False, "error": str(e), "traceback": traceback.format_exc()}


from pydantic import BaseModel
class ProfileSaveRequest(BaseModel):
    printer_model: str
    ini_content: str

class ProfileResetRequest(BaseModel):
    printer_model: str

def get_base_ini_name(printer_model: str) -> str:
    if printer_model == "x1c": return "bambu_x1c_pla.ini"
    if printer_model == "p1": return "bambu_p1_pla.ini"
    return "bambu_a1_mini_pla.ini"

@app.get("/printer/profiles/load")
async def profile_load(printer_model: str):
    """Load the active profile content for a specific printer."""
    base_ini = get_base_ini_name(printer_model)
    profiles_dir = os.path.join(os.environ.get("MODELS_DIR", "/models"), "profiles")
    os.makedirs(profiles_dir, exist_ok=True)
    
    user_ini = os.path.join(profiles_dir, f"user_{base_ini}")
    default_ini = os.path.join(profiles_dir, f"default_{base_ini}")
    
    # Ensure default exists
    if not os.path.exists(default_ini) and os.path.exists(base_ini):
        import shutil
        shutil.copy(base_ini, default_ini)
        
    is_custom = os.path.exists(user_ini)
    target_file = user_ini if is_custom else default_ini
    
    if os.path.exists(target_file):
        with open(target_file, 'r') as f:
            content = f.read()
        return {"success": True, "content": content, "is_custom": is_custom}
    return {"success": False, "error": "Profile not found."}

@app.post("/printer/profiles/save")
async def profile_save(req: ProfileSaveRequest):
    """Save custom profile content."""
    try:
        base_ini = get_base_ini_name(req.printer_model)
        profiles_dir = os.path.join(os.environ.get("MODELS_DIR", "/models"), "profiles")
        os.makedirs(profiles_dir, exist_ok=True)
        
        user_ini = os.path.join(profiles_dir, f"user_{base_ini}")
        with open(user_ini, 'w') as f:
            f.write(req.ini_content)
            
        return {"success": True, "message": "Profile saved successfully."}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/printer/profiles/reset")
async def profile_reset(req: ProfileResetRequest):
    """Delete custom profile to revert to defaults."""
    try:
        base_ini = get_base_ini_name(req.printer_model)
        profiles_dir = os.path.join(os.environ.get("MODELS_DIR", "/models"), "profiles")
        user_ini = os.path.join(profiles_dir, f"user_{base_ini}")
        
        if os.path.exists(user_ini):
            os.remove(user_ini)
            
        return {"success": True, "message": "Profile reverted to default."}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/studio", response_class=HTMLResponse)
async def get_studio():
    """Serve the 3D Workshop Studio HTML frontend."""
    try:
        with open("studio.html", "r") as f:
            html = f.read()
        return HTMLResponse(content=html, headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0"
        })
    except Exception as e:
        return f"<h1>Error loading studio.html: {str(e)}</h1>"


@app.get("/health")
async def health():
    return {"status": "ok", "services": ["cadquery", "openscad", "trimesh"]}


# ---------------------------------------------------------------------------
# CadQuery execution
# ---------------------------------------------------------------------------

@app.post("/cadquery/execute")
async def cadquery_execute(req: CadQueryRequest):
    """Execute a CadQuery Python script and return the resulting mesh."""
    try:
        import cadquery as cq

        # Execute the script in a sandboxed namespace
        namespace = {"cq": cq, "result": None}
        exec(req.script, namespace)

        result = namespace.get("result")
        if result is None:
            raise HTTPException(400, "Script must assign the final shape to 'result'")

        # Export based on format
        fmt_map = {"stl": "STL", "step": "STEP", "amf": "AMF"}
        export_fmt = fmt_map.get(req.output_format.lower())
        if not export_fmt:
            raise HTTPException(400, f"Unsupported format: {req.output_format}")

        with tempfile.NamedTemporaryFile(suffix=f".{req.output_format}") as tmp:
            if hasattr(result, "val"):
                # Workplane object
                cq.exporters.export(result, tmp.name, export_fmt)
            elif hasattr(result, "exportStl"):
                result.exportStl(tmp.name)
            else:
                cq.exporters.export(result, tmp.name, export_fmt)

            tmp.seek(0)
            data = tmp.read()

        return {
            "success": True,
            "format": req.output_format,
            "size_bytes": len(data),
            "file_base64": base64.b64encode(data).decode(),
        }

    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e), "traceback": traceback.format_exc()}


# ---------------------------------------------------------------------------
# Build123d execution
# ---------------------------------------------------------------------------

class Build123dRequest(BaseModel):
    script: str
    output_format: str = "stl"  # stl, step, 3mf


@app.post("/build123d/execute")
async def build123d_execute(req: Build123dRequest):
    """Execute a Build123d Python script and return the resulting mesh."""
    try:
        import build123d as bd

        # Execute the script in a sandboxed namespace
        namespace = {"bd": bd, "result": None}
        for name in dir(bd):
            if not name.startswith("_"):
                namespace[name] = getattr(bd, name)

        exec(req.script, namespace)

        result = namespace.get("result")
        if result is None:
            raise HTTPException(400, "Script must assign the final shape to 'result'")

        # Handle BuildPart, BuildSketch, BuildLine contexts
        if hasattr(result, "part"):
            shape = result.part
        elif hasattr(result, "sketch"):
            shape = result.sketch
        elif hasattr(result, "line"):
            shape = result.line
        else:
            shape = result

        # Export based on format
        fmt = req.output_format.lower()
        with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as tmp:
            tmp_name = tmp.name

        try:
            if fmt == "stl":
                bd.export_stl(shape, tmp_name)
            elif fmt == "step":
                bd.export_step(shape, tmp_name)
            elif fmt == "3mf":
                try:
                    exporter = bd.Mesher()
                    exporter.add_shape(shape)
                    exporter.write(tmp_name)
                except Exception:
                    # Fallback to STL-to-3MF via trimesh
                    stl_temp = tmp_name + ".stl"
                    bd.export_stl(shape, stl_temp)
                    import trimesh
                    mesh = trimesh.load(stl_temp)
                    mesh.export(tmp_name, file_type="3mf")
                    if os.path.exists(stl_temp):
                        os.remove(stl_temp)
            else:
                raise HTTPException(400, f"Unsupported format: {req.output_format}")

            with open(tmp_name, "rb") as f:
                data = f.read()
        finally:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)

        return {
            "success": True,
            "format": req.output_format,
            "size_bytes": len(data),
            "file_base64": base64.b64encode(data).decode(),
        }

    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e), "traceback": traceback.format_exc()}


# ---------------------------------------------------------------------------
# OpenSCAD execution
# ---------------------------------------------------------------------------

@app.post("/openscad/execute")
async def openscad_execute(req: OpenSCADRequest):
    """Execute an OpenSCAD script and return the resulting mesh."""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            scad_path = os.path.join(tmpdir, "input.scad")
            out_path = os.path.join(tmpdir, f"output.{req.output_format}")

            with open(scad_path, "w") as f:
                f.write(req.script)

            cmd = ["xvfb-run", "-a", "openscad", "-o", out_path]

            # Add parameter overrides
            if req.parameters:
                for key, value in req.parameters.items():
                    if isinstance(value, str):
                        cmd.extend(["-D", f'{key}="{value}"'])
                    else:
                        cmd.extend(["-D", f"{key}={value}"])

            cmd.append(scad_path)

            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120
            )

            if proc.returncode != 0:
                return {
                    "success": False,
                    "error": proc.stderr or proc.stdout,
                }

            with open(out_path, "rb") as f:
                data = f.read()

            return {
                "success": True,
                "format": req.output_format,
                "size_bytes": len(data),
                "file_base64": base64.b64encode(data).decode(),
            }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "OpenSCAD execution timed out (120s)"}
    except Exception as e:
        return {"success": False, "error": str(e), "traceback": traceback.format_exc()}


# ---------------------------------------------------------------------------
# OpenSCAD render (PNG preview from multiple angles)
# ---------------------------------------------------------------------------

class OpenSCADRenderRequest(BaseModel):
    script: str
    parameters: dict | None = None
    imgsize: str = "800,600"  # WxH
    camera: str = ""  # OpenSCAD --camera arg: tx,ty,tz,rx,ry,rz,dist
    views: list[str] | None = None  # ["front", "top", "right", "iso"] for multi-angle


CAMERA_PRESETS = {
    "iso":   "0,0,30,55,0,25,280",
    "front": "0,0,30,0,0,0,280",
    "top":   "0,0,30,90,0,0,280",
    "right": "0,0,30,0,0,90,280",
    "back":  "0,0,30,0,0,180,280",
}


@app.post("/openscad/render")
async def openscad_render(req: OpenSCADRenderRequest):
    """Render an OpenSCAD script to PNG preview image(s).
    Returns base64-encoded PNG(s). Use 'views' for multi-angle renders,
    or 'camera' for a custom OpenSCAD camera string."""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            scad_path = os.path.join(tmpdir, "input.scad")
            with open(scad_path, "w") as f:
                f.write(req.script)

            # Determine which views to render
            if req.views:
                view_list = req.views
            elif req.camera:
                view_list = [("custom", req.camera)]
            else:
                view_list = ["iso", "front"]

            renders = {}
            for view in view_list:
                if isinstance(view, tuple):
                    view_name, cam = view
                elif view in CAMERA_PRESETS:
                    view_name = view
                    cam = CAMERA_PRESETS[view]
                else:
                    continue

                png_path = os.path.join(tmpdir, f"{view_name}.png")
                cmd = [
                    "xvfb-run", "-a", "openscad",
                    "--imgsize", req.imgsize.replace("x", ","),
                    "--camera", cam,
                    "--render",
                    "-o", png_path,
                ]

                if req.parameters:
                    for key, value in req.parameters.items():
                        if isinstance(value, str):
                            cmd.extend(["-D", f'{key}="{value}"'])
                        else:
                            cmd.extend(["-D", f"{key}={value}"])

                cmd.append(scad_path)

                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=120
                )

                if proc.returncode == 0 and os.path.exists(png_path):
                    with open(png_path, "rb") as f:
                        renders[view_name] = base64.b64encode(f.read()).decode()

            if not renders:
                return {"success": False, "error": "No renders produced"}

            return {
                "success": True,
                "renders": renders,
                "views": list(renders.keys()),
            }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Render timed out (120s)"}
    except Exception as e:
        return {"success": False, "error": str(e), "traceback": traceback.format_exc()}


# ---------------------------------------------------------------------------
# Mesh info
# ---------------------------------------------------------------------------

@app.post("/mesh/info")
async def mesh_info(req: MeshInfoRequest):
    """Get information about a mesh file."""
    import trimesh

    try:
        file_bytes = base64.b64decode(req.file_base64)
        mesh = trimesh.load(
            io.BytesIO(file_bytes),
            file_type=_ext(req.filename),
        )

        if isinstance(mesh, trimesh.Scene):
            geometries = list(mesh.geometry.values())
            combined = trimesh.util.concatenate(geometries) if geometries else None
            if combined is None:
                return {"success": True, "info": {"type": "empty_scene"}}
            mesh = combined

        bounds = mesh.bounds.tolist() if mesh.bounds is not None else None
        extents = mesh.extents.tolist() if hasattr(mesh, "extents") else None

        return {
            "success": True,
            "info": {
                "vertices": len(mesh.vertices),
                "faces": len(mesh.faces),
                "bounds_mm": bounds,
                "extents_mm": extents,
                "volume_mm3": float(mesh.volume) if mesh.is_volume else None,
                "is_watertight": bool(mesh.is_watertight),
                "is_volume": bool(mesh.is_volume),
                "euler_number": int(mesh.euler_number),
                "center_mass": mesh.center_mass.tolist() if mesh.is_volume else None,
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Mesh transform
# ---------------------------------------------------------------------------

@app.post("/mesh/transform")
async def mesh_transform(req: MeshTransformRequest):
    """Apply transformations to a mesh: scale, translate, rotate, mirror."""
    import trimesh
    import numpy as np

    try:
        file_bytes = base64.b64decode(req.file_base64)
        mesh = _load_mesh(file_bytes, req.filename)

        for op in req.operations:
            action = op.get("op")
            if action == "scale":
                factor = op.get("factor", 1.0)
                if isinstance(factor, (list, tuple)):
                    mesh.apply_scale(factor)
                else:
                    mesh.apply_scale(float(factor))
            elif action == "translate":
                vec = [op.get("x", 0), op.get("y", 0), op.get("z", 0)]
                mesh.apply_translation(vec)
            elif action == "rotate":
                axis = op.get("axis", "z")
                angle = float(op.get("angle", 0))
                axis_vec = {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}.get(
                    axis, [0, 0, 1]
                )
                rot = trimesh.transformations.rotation_matrix(
                    np.radians(angle), axis_vec
                )
                mesh.apply_transform(rot)
            elif action == "mirror":
                axis = op.get("axis", "x")
                normal = {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}.get(
                    axis, [1, 0, 0]
                )
                mirror = trimesh.transformations.reflection_matrix([0, 0, 0], normal)
                mesh.apply_transform(mirror)

        data = _export_mesh(mesh, req.output_format)
        return {
            "success": True,
            "format": req.output_format,
            "size_bytes": len(data),
            "file_base64": base64.b64encode(data).decode(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Mesh repair
# ---------------------------------------------------------------------------

@app.post("/mesh/repair")
async def mesh_repair(req: MeshRepairRequest):
    """Repair a mesh: fix normals, fill holes, remove degenerate faces."""
    import trimesh

    try:
        file_bytes = base64.b64decode(req.file_base64)
        mesh = _load_mesh(file_bytes, req.filename)

        # Repair operations
        trimesh.repair.fix_normals(mesh)
        trimesh.repair.fix_inversion(mesh)
        trimesh.repair.fix_winding(mesh)
        trimesh.repair.fill_holes(mesh)
        mesh.remove_degenerate_faces()
        mesh.remove_duplicate_faces()
        mesh.remove_unreferenced_vertices()

        data = _export_mesh(mesh, req.output_format)
        return {
            "success": True,
            "format": req.output_format,
            "size_bytes": len(data),
            "is_watertight": bool(mesh.is_watertight),
            "file_base64": base64.b64encode(data).decode(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Mesh combine
# ---------------------------------------------------------------------------

@app.post("/mesh/combine")
async def mesh_combine(req: MeshCombineRequest):
    """Combine multiple meshes into one."""
    import trimesh

    try:
        meshes = []
        for f in req.files:
            file_bytes = base64.b64decode(f["file_base64"])
            mesh = _load_mesh(file_bytes, f["filename"])
            meshes.append(mesh)

        if not meshes:
            return {"success": False, "error": "No meshes provided"}

        combined = trimesh.util.concatenate(meshes)
        data = _export_mesh(combined, req.output_format)

        return {
            "success": True,
            "format": req.output_format,
            "size_bytes": len(data),
            "vertices": len(combined.vertices),
            "faces": len(combined.faces),
            "file_base64": base64.b64encode(data).decode(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Mesh slice (cut with a plane)
# ---------------------------------------------------------------------------

@app.post("/mesh/slice")
async def mesh_slice(req: MeshSliceRequest):
    """Cut a mesh with a plane, keeping one or both halves."""
    import trimesh
    import numpy as np

    try:
        file_bytes = base64.b64decode(req.file_base64)
        mesh = _load_mesh(file_bytes, req.filename)

        origin = np.array(req.plane_origin)
        normal = np.array(req.plane_normal)

        if req.keep == "both":
            above = mesh.slice_plane(origin, normal)
            below = mesh.slice_plane(origin, -normal)
            result_above = base64.b64encode(_export_mesh(above, req.output_format)).decode()
            result_below = base64.b64encode(_export_mesh(below, req.output_format)).decode()
            return {
                "success": True,
                "format": req.output_format,
                "above_base64": result_above,
                "below_base64": result_below,
            }
        else:
            if req.keep == "below":
                normal = -normal
            sliced = mesh.slice_plane(origin, normal)
            data = _export_mesh(sliced, req.output_format)
            return {
                "success": True,
                "format": req.output_format,
                "size_bytes": len(data),
                "file_base64": base64.b64encode(data).decode(),
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# File save to shared volume (for Manyfold direct access)
# ---------------------------------------------------------------------------

class FileSaveRequest(BaseModel):
    file_base64: str
    filename: str
    subfolder: str = ""  # e.g. "Watch Stand v1"


@app.post("/files/save")
async def files_save(req: FileSaveRequest):
    """Save a file to the shared models volume (accessible by Manyfold)."""
    try:
        file_bytes = base64.b64decode(req.file_base64)

        # Validate and sanitize subfolder parameter
        is_valid, error_msg, target_dir = validate_subfolder(req.subfolder if req.subfolder else "")
        if not is_valid:
            return {"success": False, "error": error_msg}

        # SECURITY: Sanitize filename to prevent path traversal attacks
        # Filename must be a leaf name only (no "/" or ".." sequences)
        filename = req.filename.strip()
        if ".." in filename or "/" in filename or filename.startswith("/"):
            return {"success": False, "error": "Invalid filename: path characters not allowed"}

        os.makedirs(target_dir, exist_ok=True)
        filepath = os.path.join(target_dir, filename)

        with open(filepath, "wb") as f:
            f.write(file_bytes)

        return {
            "success": True,
            "path": filepath,
            "size_bytes": len(file_bytes),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/files/list")
async def files_list(subfolder: str = ""):
    """List files in the shared models volume."""
    try:
        # Validate and sanitize subfolder parameter
        is_valid, error_msg, target_dir = validate_subfolder(subfolder if subfolder else "")
        if not is_valid:
            return {"success": False, "error": error_msg}

        if not os.path.isdir(target_dir):
            return {"success": True, "files": []}

        entries = []
        for item in os.listdir(target_dir):
            full = os.path.join(target_dir, item)
            if os.path.isdir(full):
                entries.append({"name": item, "type": "directory"})
            else:
                entries.append({
                    "name": item,
                    "type": "file",
                    "size_bytes": os.path.getsize(full),
                })

        return {"success": True, "files": entries}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ext(filename: str) -> str:
    """Get file extension without dot."""
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else "stl"


def _load_mesh(file_bytes: bytes, filename: str):
    """Load a mesh from bytes, handling scenes."""
    import trimesh

    mesh = trimesh.load(io.BytesIO(file_bytes), file_type=_ext(filename))
    if isinstance(mesh, trimesh.Scene):
        geometries = list(mesh.geometry.values())
        if not geometries:
            raise ValueError("Scene contains no geometry")
        mesh = trimesh.util.concatenate(geometries)
    return mesh


def _export_mesh(mesh, fmt: str) -> bytes:
    """Export a mesh to bytes in the given format."""
    buf = io.BytesIO()
    mesh.export(buf, file_type=fmt)
    buf.seek(0)
    return buf.read()


@app.get("/files/read")
async def files_read(filepath: str):
    """Read a file's content from the shared models volume."""
    try:
        full_path = os.path.normpath(os.path.join(MODELS_DIR, filepath))
        if not full_path.startswith(MODELS_DIR):
            return {"success": False, "error": "Invalid path"}
        if not os.path.isfile(full_path):
            return {"success": False, "error": "File not found"}
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"success": True, "content": content}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ---------------------------------------------------------------------------
# Startup Guard
# ---------------------------------------------------------------------------

# Prevent accidental auto-printing on server startup
if SKIP_TEST_PRINT:
    print("[STARTUP] Test printing is disabled (SKIP_TEST_PRINT=true). No automatic prints will execute on startup.")
else:
    print("[WARNING] Test printing is enabled (SKIP_TEST_PRINT=false). This may cause unintended printer activity.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
