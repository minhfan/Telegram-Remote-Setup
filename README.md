# Telegram Remote Setup

> 🇻🇳 Bản tiếng Việt ở trên. &nbsp;&nbsp; 🇬🇧 **English version below ⬇**

Wizard desktop giúp **điều khiển nhiều agent AI lập trình (Claude Code / Codex / Gemini CLI…) từ điện thoại qua Telegram**, và cho **các bot nói chuyện với nhau** qua một kênh file trung gian. Mỗi agent là "bộ não" (dùng đăng nhập sẵn của nó) — nên **KHÔNG cần API key, không tốn token khi rảnh**.

---

## 1. Cái này là gì

App **không tự gọi LLM**. Nó làm 3 việc:

1. **Ghi bộ kit Telegram RIÊNG cho từng bot** (config + `listen`/`send`/`read`) — mỗi bot tên duy nhất → folder/lock/offset riêng → **nhiều bot không đè nhau**.
2. **Dựng kênh trung gian "team"** để **bot ↔ bot** (vì Telegram, bot không đọc được tin của bot khác): `roster.json` (mỗi bot tự đăng ký + cập nhật identity) + `bus/` (hộp thư từng bot).
3. **Sinh "prompt kích hoạt 2 kênh"** để dán vào agent của từng bot: kênh 1 = người↔bot (Telegram), kênh 2 = bot↔bot (file team).

## 2. Cách hoạt động

- **Người ↔ bot:** điện thoại → Telegram → `listen.sh` → agent đọc, làm, trả lời qua `send.sh`. Idle = block trong HTTP call → **~0 token**.
- **Bot ↔ bot:** agent ghi/đọc file trong `team/` (Telegram không cho bot đọc bot). Mỗi bot chạy `bus_listen.sh` song song để thức khi bot khác nhắn; gửi bằng `bus_send.sh`.

## 3. Nhiều bot / nhiều nền tảng (không conflict)

Mỗi bot có **Tên duy nhất** (= `@tag` + tên folder). Wizard ghi kit vào `team/agents/<tên>/` với `BOT_NAME=<tên>` → **lock, offset, config tách hẳn**. Nên bạn mở **Claude** setup bot A, mở **Codex** setup bot B… mỗi con 1 token + 1 folder, **không đè nhau**. (Trùng tên → wizard chặn.)

## 4. Kênh bot ↔ bot (team)

- **`register.sh online`** — bot tự ghi/cập nhật mình vào `team/roster.json` (role, platform, status, last_seen). Roster **lớn dần** khi từng bot lên sóng.
- **`bus_listen.sh`** — block tới khi có thư cho mình, in ra, đánh dấu đã đọc.
- **`bus_send.sh <tên-bot> "…"`** — gửi riêng 1 bot. **`bus_send.sh all "…"`** — broadcast cả team (fan-out).
- Mẫu điều phối: 1 bot **PM** (trả tin người không tag) giao việc cho nhiều **specialist** qua bus rồi tổng hợp — đúng kiểu KRONOS điều phối HEPHAESTUS.

## 5. Cần gì

- **Python 3** (Windows: tích *Add Python to PATH*).
- Các **agent Claude Code / Codex / Gemini CLI…** đang chạy trên máy (mỗi bot 1 agent).
- Tài khoản **Telegram**. (Mode **git** cần thêm `git` nếu các bot ở khác máy.)

## 6. Mở app

- **Windows:** double-click **`run.bat`** (tự cài `customtkinter` lần đầu).
- **macOS / Linux:** double-click **`run.command`**, hoặc `python3 app.py`.

## 7. Các bước cài đặt

1. **Team:** chọn **Thư mục team** + **mode** (`folder` = cùng máy, mặc định; `git` = khác máy) → **🏗 Dựng team**.
2. **Thêm bot** (nút ➕): đặt **Tên** duy nhất + chọn **nền tảng** (Claude/Codex/…) + dán **Token** → **🔎 Chat ID** (nhắn 1 câu vào group rồi bấm) → bật **PM** nếu là bot điều phối → **Persona** (tự viết hoặc 📦 Nạp preset).
3. **💾 Ghi kit bot này** → **✈️ Test gửi** (chắc bot vào được group).
4. **📋 Tạo prompt** → copy → **dán vào agent của bot đó** (Claude Code/Codex…). Agent sẽ chạy `listen` + `bus_listen` + `register`.
5. Lặp bước 2–4 cho từng bot.
6. Nhắn từ điện thoại → bot trả lời; các bot tự điều phối nhau qua team. **Không API key, không tốn token.**

## 8. Đèn trạng thái

3 đèn + **🔄 Kiểm tra**:
- **Telegram:** 🟢 `@bot` = token OK (`getMe`).
- **Bộ não:** 🟢 = `listen` của bot đang chọn đang chạy (đọc lock file, **không** đụng Telegram → khỏi 409).
- **Roster:** số bot đã đăng ký / đang online (đọc `team/roster.json`).

## 9. Khi không chạy

Mở trình duyệt, thay `<TOKEN>`:
1. **Webhook chiếm bot:** `.../getWebhookInfo` có `"url"` → `.../deleteWebhook`.
2. **Privacy mode:** `.../getUpdates` rỗng → @BotFather `/setprivacy` → Disable → re-add admin.
3. **HTTP 409:** chỉ 1 `listen.sh` mỗi token.
4. **Sai Chat ID:** supergroup dạng `-1001234567890`.

## 10. Bảo mật

Kit chứa **bot token** trong `config.sh`/`config.ps1` — giữ riêng tư, đừng commit/chia sẻ. Lộ thì rotate ở @BotFather.

## 11. Cấu trúc

```
app.py · run.bat · run.command · requirements.txt
~/telegram-team/                ← team (do app dựng)
  agents/<tên-bot>/             ← kit RIÊNG mỗi bot (config + listen/send/read + register/bus_*)
  team/roster.json              ← identity các bot (tự đăng ký)
  team/bus/<tên-bot>/           ← hộp thư bot↔bot
```

<br>

---
---

<br>

# Telegram Remote Setup — English

> 🇬🇧 English version. &nbsp;&nbsp; 🇻🇳 **Phiên bản tiếng Việt ở đầu trang ⬆**

A desktop wizard to **remote-control multiple AI coding agents (Claude Code / Codex / Gemini CLI…) from your phone via Telegram**, and to let **bots talk to each other** through a shared intermediate-file channel. Each agent is the "brain" (uses its own login) — so **NO API key, ~0 tokens while idle**.

---

## 1. What it is

The app **never calls an LLM**. It does three things:

1. **Writes a per-bot Telegram kit** (config + `listen`/`send`/`read`) — each bot has a unique name → its own folder/lock/offset → **multiple bots never collide**.
2. **Sets up a "team" channel** for **bot ↔ bot** (Telegram bots can't read other bots' messages): `roster.json` (each bot self-registers + updates its identity) + `bus/` (a per-bot inbox).
3. **Generates a "2-channel activation prompt"** to paste into each bot's agent: channel 1 = human↔bot (Telegram), channel 2 = bot↔bot (team files).

## 2. How it works

- **Human ↔ bot:** phone → Telegram → `listen.sh` → the agent reads, acts, replies via `send.sh`. Idle = blocked on the HTTP call → **~0 tokens**.
- **Bot ↔ bot:** agents read/write files in `team/` (Telegram won't let a bot read a bot). Each bot runs `bus_listen.sh` in parallel to wake when another bot pings it; it sends via `bus_send.sh`.

## 3. Many bots / many platforms (no conflict)

Each bot has a **unique name** (= its `@tag` + folder name). The wizard writes its kit to `team/agents/<name>/` with `BOT_NAME=<name>` → **separate lock, offset, config**. So you open **Claude** to set up bot A, **Codex** to set up bot B… each with its own token + folder, **no overwrite**. (Duplicate names are blocked.)

## 4. The bot ↔ bot channel (team)

- **`register.sh online`** — a bot writes/updates itself in `team/roster.json` (role, platform, status, last_seen). The roster **grows gradually** as each bot comes online.
- **`bus_listen.sh`** — blocks until there's mail for it, prints it, marks it read.
- **`bus_send.sh <bot-name> "…"`** — message a single bot. **`bus_send.sh all "…"`** — broadcast to the whole team (fan-out).
- Coordination pattern: one **PM** bot (answers untagged human messages) delegates to many **specialists** over the bus, then aggregates — exactly the KRONOS-coordinates-HEPHAESTUS pattern.

## 5. Requirements

- **Python 3** (on Windows tick *Add Python to PATH*).
- Your **Claude Code / Codex / Gemini CLI…** agents running on the machine (one agent per bot).
- A **Telegram** account. (The **git** mode also needs `git` if bots run on different machines.)

## 6. Run the wizard

- **Windows:** double-click **`run.bat`** (auto-installs `customtkinter` first run).
- **macOS / Linux:** double-click **`run.command`**, or `python3 app.py`.

## 7. Step-by-step setup

1. **Team:** pick a **Team folder** + **mode** (`folder` = same machine, default; `git` = different machines) → **🏗 Build team**.
2. **Add a bot** (➕): give it a unique **Name** + pick a **platform** (Claude/Codex/…) + paste its **Token** → **🔎 Chat ID** (send a message in the group, then click) → turn on **PM** if it's the coordinator → set a **Persona** (write it or 📦 Load preset).
3. **💾 Write this bot's kit** → **✈️ Test send** (confirm it can post).
4. **📋 Generate prompt** → copy → **paste into that bot's agent** (Claude Code/Codex…). The agent will run `listen` + `bus_listen` + `register`.
5. Repeat steps 2–4 for each bot.
6. Message from your phone → the bot replies; bots coordinate with each other over the team channel. **No API key, no tokens.**

## 8. Status indicators

Three indicators + a **🔄 Check** button:
- **Telegram:** 🟢 `@bot` = valid token (`getMe`).
- **Brain:** 🟢 = the selected bot's `listen` is running (reads a lock file, does **not** poll Telegram → no 409).
- **Roster:** how many bots are registered / online (reads `team/roster.json`).

## 9. Troubleshooting

In a browser, replace `<TOKEN>`:
1. **Webhook hijack:** `.../getWebhookInfo` has a `"url"` → `.../deleteWebhook`.
2. **Privacy mode:** `.../getUpdates` is empty → @BotFather `/setprivacy` → Disable → re-add as admin.
3. **HTTP 409:** only one `listen.sh` per token.
4. **Wrong Chat ID:** a supergroup looks like `-1001234567890`.

## 10. Security

The kit holds your **bot token** in `config.sh`/`config.ps1` — keep it private, never commit/share. If it leaks, rotate it in @BotFather.

## 11. Files

```
app.py · run.bat · run.command · requirements.txt
~/telegram-team/                ← the team (created by the app)
  agents/<bot-name>/            ← per-bot kit (config + listen/send/read + register/bus_*)
  team/roster.json              ← bot identities (self-registered)
  team/bus/<bot-name>/          ← bot↔bot inbox
```
