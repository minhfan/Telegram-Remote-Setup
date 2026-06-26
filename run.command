#!/bin/bash
# ── Telegram Remote Setup — chạy trên macOS/Linux (cần python3) ──
# Double-click (mac) hoặc: bash run.command
cd "$(dirname "$0")"
echo "[*] Kiểm tra / cài customtkinter..."
python3 -m pip install --quiet customtkinter 2>/dev/null
echo "[*] Mở Telegram Remote Setup..."
python3 app.py
