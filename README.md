# Telegram Remote Setup

> 🇻🇳 Wizard desktop nhỏ gọn giúp bạn **điều khiển agent AI lập trình của mình (Claude Code / Antigravity) từ điện thoại qua Telegram**. Agent chính là "bộ não" (dùng đăng nhập sẵn của nó) — nên **KHÔNG cần API key, không tốn token khi rảnh**.
>
> 🇬🇧 A tiny desktop wizard that lets you **remote-control your own AI coding agent (Claude Code / Antigravity) from your phone via Telegram**. Your agent is the "brain" (it uses its own existing login) — so **NO API key, ~0 tokens while idle**.

---

## 1. Cái này là gì / What it is

🇻🇳 App **không tự gọi LLM**. Nó chỉ làm 2 việc:
1. **Ghi bộ kit Telegram** (config + script `listen`/`send`/`read`) để agent của bạn dùng làm "đường ống" nói chuyện với Telegram.
2. **Lưu & gọi lại Persona** — sinh ra một "prompt kích hoạt" để bạn dán vào agent; agent đọc xong sẽ vận hành vòng lặp Telegram theo đúng nhân cách đó.

🇬🇧 The app **never calls an LLM itself**. It does just two things:
1. **Writes a Telegram kit** (a `config` + `listen`/`send`/`read` scripts) that your agent uses as a pipe to Telegram.
2. **Saves & recalls Personas** — it generates an "activation prompt" you paste into your agent; the agent then runs the Telegram loop with that persona.

---

## 2. Cách hoạt động / How it works

🇻🇳 Điện thoại → Telegram → script `listen` → **agent của bạn đọc, suy nghĩ, làm việc** → trả lời qua `send` → Telegram → điện thoại. Agent block trong cú gọi HTTP của `listen` khi rảnh → **gần như 0 token**. Chi phí theo số tin nhắn, không theo thời gian bật.

🇬🇧 Phone → Telegram → `listen` script → **your agent reads, thinks, acts** → replies via `send` → Telegram → phone. While idle the agent is blocked on `listen`'s HTTP call → **near-zero tokens**. Cost scales with messages, not uptime.

---

## 3. Cần gì / Requirements

🇻🇳
- **Python 3** đã cài (Windows: nhớ tích *Add Python to PATH* khi cài).
- Một **agent Claude Code / Antigravity** đang chạy trên máy bạn (đây mới là bộ não).
- Một tài khoản **Telegram**.

🇬🇧
- **Python 3** installed (on Windows tick *Add Python to PATH* during install).
- A running **Claude Code / Antigravity agent** on your machine (this is the brain).
- A **Telegram** account.

---

## 4. Mở app / Run the wizard

🇻🇳
- **Windows:** double-click **`run.bat`** (lần đầu nó tự cài `customtkinter` rồi mở app).
- **macOS / Linux:** double-click **`run.command`**, hoặc chạy `python3 app.py`.

🇬🇧
- **Windows:** double-click **`run.bat`** (it auto-installs `customtkinter` on first run, then opens the app).
- **macOS / Linux:** double-click **`run.command`**, or run `python3 app.py`.

---

## 5. Các bước cài đặt / Step-by-step setup

### Bước 1 — Tạo bot / Step 1 — Create the bot
🇻🇳 Mở **@BotFather** trên Telegram → gõ `/newbot` → đặt tên → **chép token** (dạng `123456789:AAE...`).
🇬🇧 Open **@BotFather** in Telegram → `/newbot` → name it → **copy the token** (`123456789:AAE...`).

### Bước 2 — Tạo group + cho bot làm admin / Step 2 — Create a group + make the bot admin
🇻🇳 Tạo 1 **group** Telegram → add bot vào → vào *Edit → Administrators* cho bot làm **admin** (bắt buộc, để bot đọc được tin thường) → gõ 1 câu bất kỳ vào group.
🇬🇧 Create a Telegram **group** → add the bot → *Edit → Administrators* and make the bot an **admin** (required so it can read plain messages) → send any message in the group.

> ⚠️ 🇻🇳 Quên cho bot làm admin là lỗi #1 khiến bot không đọc được tin. / 🇬🇧 Forgetting admin is the #1 reason the bot can't read messages.

### Bước 3 — Kết nối (thẻ 1) / Step 3 — Connect (card 1)
🇻🇳 Dán **Bot Token** → bấm **🔎 Lấy Chat ID** (app tự bắt Chat ID từ tin bạn vừa gửi) → đặt **Tên agent** + **Role** (PM = trả mọi tin; DEV = chỉ trả `@anti`/`@all`) → chọn thư mục → **💾 Ghi bộ kit** → **✈️ Test gửi** để chắc bot nói được vào group.
🇬🇧 Paste the **Bot Token** → click **🔎 Get Chat ID** (it auto-detects the Chat ID from your message) → set an **Agent name** + **Role** (PM = answers everything; DEV = only `@anti`/`@all`) → pick a folder → **💾 Write kit** → **✈️ Test send** to confirm the bot can post.

### Bước 4 — Persona (thẻ 2) / Step 4 — Persona (card 2)
🇻🇳 Chọn **Nạp preset** (có sẵn nhiều nhân vật) hoặc tự viết nhân cách → **💾 Lưu persona**. Persona được lưu lại để gọi lại sau.
🇬🇧 Pick **Load preset** (many ready-made characters) or write your own persona → **💾 Save persona**. Personas are saved so you can recall them later.

### Bước 5 — Tạo & dán Prompt kích hoạt (thẻ 3) / Step 5 — Generate & paste the Activation prompt (card 3)
🇻🇳 Bấm **📋 Tạo & Copy** → app sinh đoạn prompt (nhân cách + cách vận hành vòng lặp + đường dẫn kit) và copy sẵn → **dán thẳng vào Claude Code / Antigravity của bạn**. Agent sẽ bắt đầu chạy `listen` và lắng nghe.
🇬🇧 Click **📋 Generate & Copy** → it produces the prompt (persona + how to run the loop + kit path) and copies it → **paste it into your Claude Code / Antigravity agent**. The agent will start running `listen` and listening.

### Bước 6 — Remote từ điện thoại / Step 6 — Remote from your phone
🇻🇳 Nhắn vào group từ điện thoại → agent đọc, làm, trả lời. Xong!
🇬🇧 Message the group from your phone → the agent reads, acts, replies. Done!

---

## 6. Đèn trạng thái / Status indicators

🇻🇳 Trên cùng có 2 đèn + nút **🔄 Kiểm tra**:
- **Telegram:** 🟢 `@tên_bot` = token hợp lệ; 🔴 = token sai/lỗi mạng.
- **Bộ não:** 🟢 *đang lắng nghe* = agent đã chạy `listen` (kiểm bằng lock file trên máy, **không** đụng Telegram nên không gây lỗi 409); ⚪ = chưa chạy.
- "Đã thông" hoàn toàn = cả 2 đèn 🟢 + bạn thấy agent trả lời khi nhắn vào group.

🇬🇧 Two indicators at the top + a **🔄 Check** button:
- **Telegram:** 🟢 `@bot_name` = valid token; 🔴 = bad token/network error.
- **Brain:** 🟢 *listening* = the agent's `listen` is running (detected via a local lock file, it does **not** poll Telegram so it can't cause a 409); ⚪ = not running.
- Fully connected = both 🟢 + you see the agent reply when you message the group.

---

## 7. Khi không chạy / Troubleshooting

🇻🇳 Mở trình duyệt, thay `<TOKEN>`:
1. **Webhook chiếm bot.** Mở `https://api.telegram.org/bot<TOKEN>/getWebhookInfo` — nếu `"url"` không rỗng thì `getUpdates` không nhận gì. Sửa: mở `https://api.telegram.org/bot<TOKEN>/deleteWebhook`.
2. **Privacy mode còn bật.** Gửi tin vào group rồi mở `https://api.telegram.org/bot<TOKEN>/getUpdates` — nếu `"result":[]` rỗng nghĩa là bot không đọc được bạn. Sửa: @BotFather → `/setprivacy` → chọn bot → **Disable** → re-add bot làm admin.
3. **Hai listener cùng 1 bot = HTTP 409.** Chỉ chạy MỘT `listen` cho mỗi token. (Wizard chỉ kiểm lock, không poll, nên an toàn.)
4. **Sai Chat ID.** Supergroup có dạng `-1001234567890` — lấy đúng từ getUpdates.

🇬🇧 In a browser, replace `<TOKEN>`:
1. **A webhook is hijacking it.** Open `.../getWebhookInfo` — if `"url"` is non-empty, `getUpdates` returns nothing. Fix: open `.../deleteWebhook`.
2. **Privacy mode still on.** Send a message, open `.../getUpdates` — empty `"result":[]` means the bot can't read you. Fix: @BotFather → `/setprivacy` → pick the bot → **Disable** → re-add as admin.
3. **Two listeners on one bot = HTTP 409.** Run only ONE `listen` per token. (The wizard only checks a lock, never polls, so it's safe.)
4. **Wrong Chat ID.** A supergroup looks like `-1001234567890` — copy it exactly from getUpdates.

---

## 8. Bảo mật / Security

🇻🇳 Bộ kit chứa **bot token** trong `config.sh`/`config.ps1` — giữ riêng tư, đừng commit/chia sẻ. Lộ token thì rotate ở @BotFather. Persona lưu ở `~/.chronos_forge/personas.json` (chỉ là văn bản, không có secret).
🇬🇧 The kit holds your **bot token** in `config.sh`/`config.ps1` — keep it private, never commit/share. If it leaks, rotate it in @BotFather. Personas are stored in `~/.chronos_forge/personas.json` (plain text, no secrets).

---

## 9. Cấu trúc / Files

```
app.py             # Wizard (UI + logic; nhúng sẵn script kit)  /  the wizard (UI + logic; scripts embedded)
run.bat            # Mở trên Windows  /  launcher for Windows
run.command        # Mở trên macOS/Linux  /  launcher for macOS/Linux
requirements.txt   # customtkinter
```

🇻🇳 Bộ kit (`config` + `listen`/`send`/`read`, cả `.sh` lẫn `.ps1`) được app **tự ghi ra** thư mục bạn chọn khi bấm *Ghi bộ kit*.
🇬🇧 The kit (`config` + `listen`/`send`/`read`, both `.sh` and `.ps1`) is **written out** by the app to your chosen folder when you click *Write kit*.
