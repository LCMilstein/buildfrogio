# BuildFrog 🐸

**Type a prompt. Hold the result.**

BuildFrog is an open-source, browser-based AI-to-print pipeline. Describe what you want to build, watch AI write the CAD code, preview it in 3D, and send it directly to your Bambu Lab printer — no Bambu Studio, no cloud, no CAD experience required.

🌐 **[buildfrog.io](https://buildfrog.io)** · ⭐ Star us if you find this useful!

---

## How It Works

1. **Write a prompt** — "A wall mount for a Nintendo Switch" or "A bracket to hold my water bottle"
2. **AI generates code** — BuildFrog writes CadQuery, Build123d, or OpenSCAD for you
3. **Preview & tweak** — Live 3D preview in the browser, iterate in seconds
4. **Slice & print** — Auto-slices with PrusaSlicer, sends directly to your Bambu printer over LAN

---

## Features

- **Multi-Engine CAD**: CadQuery, Build123d, and OpenSCAD — all running in the browser
- **Multi-LLM Support**: Ollama (local/private), OpenAI, Anthropic, and Gemini
- **100% Air-Gapped**: Local LLM + LAN printing — zero data leaves your network
- **No Bambu Cloud**: Communicates directly with your printer via FTPS/MQTT LAN Mode
- **Works on Chromebooks**: Browser-only, no installs, no accounts
- **One Docker command**: Full stack up in under a minute

---

## Supported Printers

| Printer | Status |
|---|---|
| Bambu Lab A1 Mini | ✅ Supported |
| Bambu Lab X1 Carbon | ✅ Supported |
| Bambu Lab P1S / P1P | ✅ Supported |
| Prusa / Creality / Klipper | 🔜 Community contributions welcome |

---

## ⚠️ Security Warning

**Do NOT expose BuildFrog to the public internet via port forwarding.**

This app is designed for secure local networks (LAN) only. Exposing it publicly could allow attackers to send arbitrary G-Code to your physical printer or exhaust your LLM API credits.

Always set a strong `WORKSHOP_PASSWORD` in your `.env` file.

---

## Getting Started

### 1. Clone the repository
```bash
git clone https://github.com/LCMilstein/buildfrogio
cd 3d-workshop
```

### 2. Configure your environment
```bash
cp .env.example .env
```

Edit `.env` and fill in:

| Variable | Description |
|---|---|
| `WORKSHOP_PASSWORD` | Password to access the UI |
| `BAMBU_PRINTER_IP` | Your printer's local IP (e.g. `192.168.1.100`) |
| `BAMBU_PRINTER_SERIAL` | Printer serial number (from printer info screen) |
| `BAMBU_PRINTER_ACCESS_CODE` | 8-digit LAN access code (from printer settings) |
| `OLLAMA_URL` | Ollama endpoint (e.g. `http://localhost:11434`) |
| `OPENAI_API_KEY` | Optional — OpenAI API key |
| `ANTHROPIC_API_KEY` | Optional — Anthropic API key |
| `GEMINI_API_KEY` | Optional — Google Gemini API key |

> **Finding your Bambu credentials:** On your printer, go to **Settings → Network → LAN Only Mode**. Enable it to get your Access Code. The Serial number is under **Settings → Device Info**.

### 3. Run
```bash
docker compose up --build
```

Open `http://localhost:3215` in your browser.

---

## File Structure

```
buildfrog/
├── server.py              # FastAPI backend — CAD execution, slicing, FTP/MQTT
├── studio.html            # Browser workbench UI
├── Dockerfile             # Container build
├── docker-compose.yml     # Stack configuration
├── .env.example           # Environment template
├── bambu_a1_mini_pla.ini  # Slicer profile — A1 Mini
├── bambu_x1c_pla.ini      # Slicer profile — X1 Carbon
├── bambu_p1_pla.ini       # Slicer profile — P1S/P1P
└── landing/               # Marketing site (buildfrog.io)
```

---

## Contributing

Printer support PRs are very welcome! To add a new printer:
1. Add a `.ini` slicer profile
2. Add the printer model to the UI dropdown in `studio.html`
3. Update the bed size logic in `server.py`

---

## License

MIT — free to use, modify, and self-host.

---

*Built with ❤️ by [@LCMilstein](https://github.com/LCMilstein) · [buildfrog.io](https://buildfrog.io)*
