#!/usr/bin/env python3
"""Cliente de escritorio (GUI) para el proxy Ollama privado cifrado.

Qué hace:
  1. Comprueba si el modelo BERT está en `models/`; si no, intenta descargarlo.
  2. Ejecuta unas comprobaciones mínimas del sistema.
  3. Muestra una ventana con la configuración (precargada de `.env`) y detecta
     tu IP automáticamente.
  4. Con "Arrancar": hace ping al servidor (/health → 200) y abre el chat.
  5. Levanta `local_ollama.py` para que VS Code / Codex / etc. se conecten.
  6. Con "Parar" o al cerrar la ventana, detiene el Ollama local.

Ejecutar:  python client_app.py   (o run_client.bat / run_client.sh)
"""
import base64
import json
import socket
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

import secure

ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL_REPO = "PlanTL-GOB-ES/bsc-bio-ehr-es-carmen-anon"

CONFIG_KEYS = [
    "REMOTE_URL", "ENCRYPTION_SECRET", "AUTH_USER", "AUTH_PASSWORD",
    "ALLOWED_IPS", "OLLAMA_MODEL", "LOCAL_PORT",
]

CONFIG_LABELS = {
    "REMOTE_URL": "URL del servidor",
    "ENCRYPTION_SECRET": "Secreto de cifrado",
    "AUTH_USER": "Usuario (basic auth)",
    "AUTH_PASSWORD": "Contraseña (basic auth)",
    "ALLOWED_IPS": "IPs permitidas (para el servidor)",
    "OLLAMA_MODEL": "Modelo",
    "LOCAL_PORT": "Puerto local Ollama",
}

DEFAULTS = {
    "REMOTE_URL": "",
    "ENCRYPTION_SECRET": "",
    "AUTH_USER": "",
    "AUTH_PASSWORD": "",
    "ALLOWED_IPS": "",
    "OLLAMA_MODEL": "",
    "LOCAL_PORT": "11434",
}


# ── Utilidades ──────────────────────────────────────────────────────────────
def load_env(path=".env"):
    env = dict(DEFAULTS)
    p = ROOT / path
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                env[key.strip()] = val.strip()
    return env


def model_repo(env=None):
    env = env if env is not None else load_env()
    return (env.get("BERT_MODEL") or DEFAULT_MODEL_REPO).strip()


def model_dirname(repo=None):
    repo = repo if repo is not None else model_repo()
    return repo.split("/")[-1]


def save_env(updates: dict, path=".env"):
    """Actualiza (o añade) claves en .env preservando comentarios."""
    p = ROOT / path
    lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    found = set()
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                found.add(key)
                continue
        out.append(line)
    for key, val in updates.items():
        if key not in found:
            out.append(f"{key}={val}")
    p.write_text("\n".join(out) + "\n", encoding="utf-8")


def detect_ip():
    """Detecta la IP pública (o la local como respaldo)."""
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip", "https://icanhazip.com"):
        try:
            with urllib.request.urlopen(url, timeout=6) as resp:
                ip = resp.read().decode().strip()
                if ip:
                    return ip
        except Exception:
            continue
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ""


def ensure_model(models_dir=None):
    """Comprueba el modelo BERT; si no está, intenta descargarlo (gated)."""
    repo = model_repo()
    d = Path(models_dir) if models_dir else ROOT / "models"
    model_dir = d / model_dirname(repo)
    if (model_dir / "pytorch_model.bin").exists() or (model_dir / "model.safetensors").exists():
        return True, "presente"
    try:
        from huggingface_hub import snapshot_download  # noqa: E402
        snapshot_download(repo_id=repo, local_dir=str(model_dir))
    except Exception as exc:
        return False, f"no descargable ({exc.__class__.__name__})"
    ok = (model_dir / "pytorch_model.bin").exists() or (model_dir / "model.safetensors").exists()
    return ok, ("descargado" if ok else "falló la descarga")


def run_checks():
    checks = []
    checks.append(("Python 3.9+", sys.version_info >= (3, 9), sys.version.split()[0]))
    for mod in ("torch", "transformers", "cryptography", "numpy"):
        try:
            __import__(mod)
            checks.append((mod, True, "importado"))
        except Exception as exc:
            checks.append((mod, False, str(exc)))
    ok_model, detail = ensure_model()
    checks.append((f"Modelo {model_dirname()}", ok_model, detail))
    env = load_env()
    missing = [k for k in ("REMOTE_URL", "ENCRYPTION_SECRET") if not env.get(k)]
    checks.append(("Configuración .env", not missing,
                   "ok" if not missing else f"faltan: {', '.join(missing)}"))
    return checks


def ping_server(url):
    with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return resp.status == 200 and data.get("ok") is True


def secure_request(secret, base_url, method, path, body, auth=None, timeout=600):
    """Petición cifrada al proxy remoto. Devuelve {status, body}."""
    inner = {"method": method, "path": path, "body": body}
    envelope = secure.encrypt(secret, json.dumps(inner).encode("utf-8"))
    data = json.dumps(envelope).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = auth
    req = urllib.request.Request(
        base_url + "/secure/request", data=data, headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        resp_envelope = json.loads(resp.read().decode("utf-8"))
    return json.loads(secure.decrypt(secret, resp_envelope).decode("utf-8"))


# ── Paleta de colores (tono marrón) ────────────────────────────────────────
COLORS = {
    "bg": "#e9dccb",
    "fg": "#3a2a1a",
    "accent": "#8b5a2b",
    "field_bg": "#fbf5ec",
    "border": "#c9b59c",
    "section": "#5d4633",
    "sub": "#7a6452",
}


class CollapsibleSection(ttk.Frame):
    """Sección con cabecera clicable que muestra/oculta su contenido."""

    def __init__(self, parent, title, body_fill="x", body_expand=False,
                 collapsed=False, on_toggle=None, **kwargs):
        super().__init__(parent, style="TFrame", **kwargs)
        self._title = title
        self._body_fill = body_fill
        self._body_expand = body_expand
        self._collapsed = collapsed
        self._on_toggle = on_toggle
        self._arrow = "▸" if collapsed else "▾"
        self.header = ttk.Button(self, text=f"{self._arrow} {title}",
                                 style="Section.TButton", command=self.toggle)
        self.header.pack(fill="x", anchor="w")
        self.body = ttk.Frame(self, style="TFrame")
        if not collapsed:
            self.body.pack(fill=body_fill, expand=body_expand, pady=(6, 0))

    def toggle(self):
        self._collapsed = not self._collapsed
        if self._collapsed:
            self.body.pack_forget()
            self._arrow = "▸"
        else:
            self.body.pack(fill=self._body_fill, expand=self._body_expand, pady=(6, 0))
            self._arrow = "▾"
        self.header.config(text=f"{self._arrow} {self._title}")
        if self._on_toggle:
            self._on_toggle()


class ClientApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Pukara v1.0 - Secure Ollama")
        self._set_icon()
        self.env = load_env()
        self.ollama_proc = None
        self.log_file = None
        self.anon = None
        self.history = []
        self.started = False
        self.vars = {}
        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._fit_window()

        self.status("Ejecutando comprobaciones del sistema...")
        self.run_bg(run_checks, done=self._on_checks,
                    error=lambda e: self.status(f"✗ Error en comprobaciones: {e}"))
        self.run_bg(detect_ip, done=self._on_ip_detected)

    # ── UI ────────────────────────────────────────────────────────────────
    def _setup_style(self):
        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        bg = COLORS["bg"]
        fg = COLORS["fg"]
        accent = COLORS["accent"]
        self.root.configure(bg=bg)
        self.style.configure(".", background=bg, foreground=fg, font=("Segoe UI", 10))
        self.style.configure("TFrame", background=bg)
        self.style.configure("TLabel", background=bg, foreground=fg)
        self.style.configure("Header.TLabel", background=bg, foreground=fg,
                             font=("Segoe UI", 17, "bold"))
        self.style.configure("Sub.TLabel", background=bg, foreground=COLORS["sub"],
                             font=("Segoe UI", 10))
        self.style.configure("TLabelframe", background=bg, bordercolor=COLORS["border"])
        self.style.configure("TLabelframe.Label", background=bg, foreground=COLORS["section"],
                             font=("Segoe UI", 10, "bold"))
        self.style.configure("TEntry", padding=7, fieldbackground=COLORS["field_bg"])
        self.style.configure("TButton", padding=(14, 7))
        self.style.configure("Section.TButton", background=bg, foreground=COLORS["section"],
                             font=("Segoe UI", 11, "bold"), padding=(2, 4), relief="flat")
        self.style.map("Section.TButton", background=[("active", bg)])
        self.style.configure("Accent.TButton", background=accent, foreground="white",
                             font=("Segoe UI", 10, "bold"))
        self.style.map("Accent.TButton",
                       background=[("active", "#6f4420"), ("disabled", "#cbb69b")],
                       foreground=[("disabled", "#f6efe4")])

    def build_ui(self):
        self._setup_style()

        header = ttk.Frame(self.root, style="TFrame", padding=(18, 14))
        header.pack(fill="x")
        ttk.Label(header, text="Cliente Ollama Privado", style="Header.TLabel").pack(anchor="w")
        ttk.Label(header, text="Conexión cifrada AES-GCM · anonimización BERT local",
                  style="Sub.TLabel").pack(anchor="w")

        status_frame = ttk.LabelFrame(self.root, text="Estado del sistema", padding=10)
        status_frame.pack(fill="x", padx=18, pady=(4, 0))
        self.status_text = scrolledtext.ScrolledText(
            status_frame, height=6, state="disabled", font=("Consolas", 9),
            bg=COLORS["field_bg"], fg=COLORS["fg"], relief="flat", borderwidth=0)
        self.status_text.pack(fill="x")

        # Configuración: colapsable, abierta por defecto.
        self.config_section = CollapsibleSection(
            self.root, "Configuración (se guarda en .env)", on_toggle=self._fit_window)
        self.config_section.pack(fill="x", padx=18, pady=(10, 0))
        for i, key in enumerate(CONFIG_KEYS):
            ttk.Label(self.config_section.body, text=CONFIG_LABELS[key]).grid(
                row=i, column=0, sticky="e", padx=(0, 8), pady=4)
            var = tk.StringVar(value=self.env.get(key, ""))
            ttk.Entry(self.config_section.body, textvariable=var, width=58).grid(
                row=i, column=1, sticky="we", pady=4)
            self.vars[key] = var
        self.config_section.body.columnconfigure(1, weight=1)

        btns = ttk.Frame(self.root, style="TFrame", padding=(18, 10))
        btns.pack(fill="x")
        ttk.Button(btns, text="Detectar IP", command=self.on_detect_ip).pack(side="left", padx=(0, 8))
        self.start_btn = ttk.Button(btns, text="Arrancar", style="Accent.TButton", command=self.on_start)
        self.start_btn.pack(side="left", padx=(0, 8))
        self.stop_btn = ttk.Button(btns, text="Parar", command=self.on_stop, state="disabled")
        self.stop_btn.pack(side="left")

        # Chat: colapsable, abierto por defecto.
        self.chat_section = CollapsibleSection(
            self.root, "Chat", body_fill="both", body_expand=True, on_toggle=self._fit_window)
        self.chat_section.pack(fill="both", expand=True, padx=18, pady=(10, 18))
        # La fila de entrada va anclada abajo para que siempre sea visible.
        inrow = ttk.Frame(self.chat_section.body, style="TFrame")
        inrow.pack(side="bottom", fill="x", pady=(8, 0))
        ttk.Label(inrow, text="Mensaje:", style="TLabel").pack(side="left")
        self.input = ttk.Entry(inrow)
        self.input.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self.input.bind("<Return>", self.on_send)
        self.send_btn = ttk.Button(inrow, text="Enviar", style="Accent.TButton",
                                   command=self.on_send, state="disabled")
        self.send_btn.pack(side="left", padx=(8, 0))
        self.chat_text = scrolledtext.ScrolledText(
            self.chat_section.body, height=8, state="disabled", font=("Segoe UI", 10),
            bg=COLORS["field_bg"], fg=COLORS["fg"], relief="flat", borderwidth=0)
        self.chat_text.pack(side="top", fill="both", expand=True)

    # ── Helpers UI ────────────────────────────────────────────────────────
    def _set_icon(self):
        icon_path = ROOT / "image.png"
        if icon_path.exists():
            try:
                self._icon = tk.PhotoImage(file=str(icon_path))
                self.root.iconphoto(True, self._icon)
            except Exception as exc:
                print(f"[icon] no se pudo cargar {icon_path}: {exc}")

    def _fit_window(self):
        """Ajusta el tamaño de la ventana al contenido (responsive)."""
        self.root.update_idletasks()
        w = max(self.root.winfo_reqwidth(), 640)
        h = max(self.root.winfo_reqheight(), 480)
        self.root.geometry(f"{w}x{h}")

    def status(self, msg):
        self._append(self.status_text, msg + "\n")

    def append_chat(self, speaker, text):
        self._append(self.chat_text, f"{speaker}: {text}\n\n")

    def _append(self, widget, text):
        widget.config(state="normal")
        widget.insert(tk.END, text)
        widget.see(tk.END)
        widget.config(state="disabled")

    def _ui(self, fn, *args):
        """Programa una actualización de UI en el hilo principal, con guarda."""
        try:
            if self.root.winfo_exists():
                self.root.after(0, lambda: fn(*args))
        except Exception:
            pass

    def run_bg(self, fn, done=None, error=None):
        def target():
            try:
                result = fn()
            except Exception as exc:
                if error:
                    self._ui(error, exc)
                return
            if done:
                self._ui(done, result)
        threading.Thread(target=target, daemon=True).start()

    # ── Comprobaciones ────────────────────────────────────────────────────
    def _on_checks(self, checks):
        for label, ok, detail in checks:
            mark = "✓" if ok else "✗"
            self.status(f"{mark} {label}: {detail}")
        self.status("Comprobaciones terminadas.")

    # ── IP ────────────────────────────────────────────────────────────────
    def on_detect_ip(self):
        self.run_bg(detect_ip, done=self._on_ip_detected)

    def _on_ip_detected(self, ip):
        if ip:
            self.vars["ALLOWED_IPS"].set(ip)
            self.status(f"IP detectada: {ip}")
        else:
            self.status("⚠ No se pudo detectar la IP automáticamente")

    # ── Arranque / parada ─────────────────────────────────────────────────
    def on_start(self):
        updates = {k: self.vars[k].get().strip() for k in CONFIG_KEYS}
        save_env(updates)
        url = updates["REMOTE_URL"].rstrip("/")
        if not updates["ENCRYPTION_SECRET"]:
            messagebox.showerror("Configuración", "Falta el secreto de cifrado (ENCRYPTION_SECRET).")
            return
        self.status(f"Haciendo ping a {url}/health ...")
        self.start_btn.config(state="disabled")
        self.run_bg(
            lambda: ping_server(url),
            done=lambda ok: self._on_ping(ok, url),
            error=lambda e: self._on_ping_error(e),
        )

    def _on_ping(self, ok, url):
        if not ok:
            self.status("✗ El servidor no respondió 200 en /health")
            messagebox.showerror("Conexión", "El servidor no respondió 200 en /health.")
            self.start_btn.config(state="normal")
            return
        self.status("✓ Servidor responde 200")
        self._start_ollama()
        self.status("Cargando anonimizador (BERT)...")
        self.run_bg(
            lambda: _load_anonymizer(),
            done=self._on_anon_loaded,
            error=lambda e: self._on_anon_loaded((None, str(e))),
        )

    def _on_ping_error(self, exc):
        self.status(f"✗ Error de conexión: {exc}")
        messagebox.showerror("Conexión", f"No se pudo conectar:\n{exc}")
        self.start_btn.config(state="normal")

    def _start_ollama(self):
        if self.ollama_proc is not None:
            return
        try:
            self.log_file = open(ROOT / "client_ollama.log", "ab")
            self.ollama_proc = subprocess.Popen(
                [sys.executable, str(ROOT / "local_ollama.py")],
                cwd=str(ROOT), stdout=self.log_file, stderr=self.log_file,
            )
            self.status(f"✓ Ollama local levantado en puerto {self.vars['LOCAL_PORT'].get()}")
        except Exception as exc:
            self.status(f"✗ No se pudo levantar Ollama local: {exc}")

    def _on_anon_loaded(self, result):
        anon, error = result
        self.anon = anon
        if anon is None:
            self.status(f"⚠ Anonimizador no disponible: {error}")
        else:
            self.status("✓ Anonimizador listo")
        self.status("✓ Cliente listo. Escribe tu mensaje.")
        # Arrancar queda deshabilitado: ya estamos en marcha.
        self.started = True
        self.stop_btn.config(state="normal")
        self.send_btn.config(state="normal")
        self.input.focus_set()

    def on_stop(self):
        self._stop_ollama()
        if self.anon is not None:
            self.anon.reset()
        self.history.clear()
        self.started = False
        self.chat_text.config(state="normal")
        self.chat_text.delete("1.0", tk.END)
        self.chat_text.config(state="disabled")
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.send_btn.config(state="disabled")
        self.status("Detenido. Puedes volver a Arrancar.")

    def _stop_ollama(self):
        if self.ollama_proc is not None:
            try:
                self.ollama_proc.terminate()
            except Exception:
                pass
            self.ollama_proc = None
        if self.log_file is not None:
            try:
                self.log_file.close()
            except Exception:
                pass
            self.log_file = None

    def on_close(self):
        self._stop_ollama()
        self.root.destroy()

    # ── Chat ──────────────────────────────────────────────────────────────
    def on_send(self, event=None):
        if not self.started:
            return
        text = self.input.get().strip()
        if not text:
            return
        self.input.delete(0, tk.END)
        self.append_chat("Tú", text)
        self.history.append({"role": "user", "content": text})
        self.send_btn.config(state="disabled")
        self.run_bg(self._do_chat, done=self._on_chat_done, error=self._on_chat_error)

    def _do_chat(self):
        url = self.vars["REMOTE_URL"].get().strip().rstrip("/")
        secret = self.vars["ENCRYPTION_SECRET"].get().strip()
        model = self.vars["OLLAMA_MODEL"].get().strip()
        user = self.vars["AUTH_USER"].get().strip()
        password = self.vars["AUTH_PASSWORD"].get().strip()

        auth = None
        if user and password:
            token = base64.b64encode(("%s:%s" % (user, password)).encode("utf-8")).decode("ascii")
            auth = "Basic " + token

        messages = [dict(m) for m in self.history]
        if self.anon is not None:
            for m in messages:
                if isinstance(m.get("content"), str):
                    m["content"] = self.anon.anonymize(m["content"])

        body = {"model": model, "messages": messages, "stream": False}
        result = secure_request(secret, url, "POST", "/v1/chat/completions", body, auth)

        status = result.get("status")
        resp_body = result.get("body")
        if status == 200 and isinstance(resp_body, dict):
            choices = resp_body.get("choices") or []
            content = ""
            if choices:
                content = (choices[0].get("message") or {}).get("content") or ""
        else:
            content = f"[Error {status}] {json.dumps(resp_body, ensure_ascii=False)[:300]}"

        if self.anon is not None and status == 200:
            content = self.anon.deanonymize(content)
        return content

    def _on_chat_done(self, content):
        self.history.append({"role": "assistant", "content": content})
        self.append_chat("Modelo", content)
        self.send_btn.config(state="normal")

    def _on_chat_error(self, exc):
        self.append_chat("Error", str(exc))
        self.send_btn.config(state="normal")


def _load_anonymizer():
    try:
        from anonymizer import get_anonymizer
        return get_anonymizer(), None
    except Exception as exc:
        return None, str(exc)


def main():
    root = tk.Tk()
    root.minsize(640, 480)
    ClientApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
