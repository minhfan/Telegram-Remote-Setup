#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram AI Bot Hub — Desktop App (multi-bot / multi-group)
===========================================================
Quản lý NHIỀU bot, NHIỀU group trong cùng 1 app. Mỗi bot là 1 CARD hiển thị
thành 1 hàng (thấy hết cùng lúc, không phải switch dropdown). Có thư viện PRESET
team: nạp cả 1 team nhân vật (mỗi nhân vật = 1 bot) với system-prompt soạn sẵn
theo template bullet cố định cho dễ customize.

Mỗi "bot" là 1 khối TỰ CHỨA:
    { token, chat_id, group_name, provider, api_key, role(@tag), is_default, system_prompt }
  - token      : token của bot (từ @BotFather). Group KHÔNG có token, chỉ có Chat ID.
  - chat_id    : Group Chat ID (supergroup dạng -1001234567890).
  - group_name : tên gợi nhớ do user tự đặt (chỉ để dễ nhìn, không ảnh hưởng routing).
  - provider   : Claude | Gemini | GPT  (RIÊNG từng bot).
  - api_key    : API key của provider tương ứng (RIÊNG từng bot).
  - role(@tag) : nhãn vai trò user tự gõ; chính nó là tag để gọi bot (vd @anti, @dev).
  - is_default : bot "mặc định" trả lời mọi tin KHÔNG có @tag (vai PM cũ).
  - system_prompt : RIÊNG từng bot — đoạn 'system' gửi vào LLM để nhân cách hoá bot đó.

Định tuyến 1 tin trong group:
  @all/@both -> mọi bot ; @<tag> -> bot có role==<tag> ; không tag -> bot is_default.

Telegram chỉ cho 1 poller / 1 token -> app GOM bot theo token (1 poller/token, route
theo Chat ID). Giữ tinh hoa bản script: long-poll getUpdates (~0 token idle), read-offset
trên đĩa chống đọc lặp, lock chống chạy đè (tránh 409).

Phụ thuộc: chỉ cần `customtkinter`.   pip install customtkinter
Đóng gói WINDOWS:
    pyinstaller --noconfirm --onefile --windowed --collect-all customtkinter app.py
"""

import json
import os
import queue
import socket
import threading
import time
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import customtkinter as ctk

# ───────────────────────────── Cấu hình tĩnh ─────────────────────────────
APP_NAME = "Telegram AI Bot Hub"
DATA_DIR = Path.home() / ".chronos_forge"
SETTINGS_FILE = DATA_DIR / "settings.json"

LONG_POLL_SECONDS = 25
HTTP_EXTRA_TIMEOUT = 20
BACKOFF_SECONDS = 5
TELEGRAM_TEXT_LIMIT = 4000

PROVIDERS = ["Claude", "Gemini", "GPT"]

CLAUDE_MODEL = "claude-opus-4-8"
CLAUDE_MAX_TOKENS = 1024
GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_MAX_TOKENS = 1024
GPT_MODEL = "gpt-4o"
GPT_MAX_TOKENS = 1024


# ───────────────────────────── Lớp HTTP (urllib) ─────────────────────────────
def _http_json(url, *, method="GET", headers=None, body=None, timeout=30):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def _read_http_error(err):
    try:
        return err.read().decode("utf-8")[:500]
    except Exception:
        return str(err)


def _split_chunks(text, size):
    text = text or ""
    if len(text) <= size:
        return [text]
    return [text[i:i + size] for i in range(0, len(text), size)]


def _pid_alive(pid):
    if os.name == "nt":
        try:
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x0400, False, pid)
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                return True
            return False
        except Exception:
            return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


# ───────────────────────────── Telegram Bot API ─────────────────────────────
def tg_get_updates(token, offset, timeout_secs):
    params = {"timeout": timeout_secs, "allowed_updates": json.dumps(["message"])}
    if offset is not None:
        params["offset"] = offset
    url = "https://api.telegram.org/bot%s/getUpdates?%s" % (token, urllib.parse.urlencode(params))
    return _http_json(url, method="GET", timeout=timeout_secs + HTTP_EXTRA_TIMEOUT)


def tg_send_message(token, chat_id, text):
    url = "https://api.telegram.org/bot%s/sendMessage" % token
    return _http_json(url, method="POST", body={"chat_id": chat_id, "text": text}, timeout=30)


# ───────────────────────────── PRESET team (~20 theme) ─────────────────────────────
def _p(vai_tro, tinh_cach, giao_tiep, cach_noi, chuyen_mon):
    """Dựng system-prompt theo template bullet cố định (dễ customize)."""
    return ("Vai trò: %s\n"
            "Tính cách: %s\n"
            "Phong cách giao tiếp: %s\n"
            "Cách nói chuyện: %s\n"
            "Chuyên môn / nhiệm vụ: %s\n"
            "Lưu ý: luôn trả lời bằng tiếng Việt, ngắn gọn, đúng vai; xưng hô nhất quán."
            ) % (vai_tro, tinh_cach, giao_tiep, cach_noi, chuyen_mon)


def _char(role, is_default, prompt):
    return {"role": role, "is_default": is_default, "system_prompt": prompt}


PRESETS = {
    # ── Teams công việc ──────────────────────────────────────────────
    "Team Dev": [
        _char("architect", True, _p("Kiến trúc sư trưởng, điều phối kỹ thuật",
            "điềm tĩnh, quyết đoán, tư duy hệ thống",
            "rõ ràng, nêu trade-off trước khi chốt",
            "dứt khoát, dùng thuật ngữ tiếng Anh khi cần",
            "thiết kế hệ thống, chia task, review giải pháp")),
        _char("backend", False, _p("Lập trình viên Backend",
            "cẩn thận, logic, thực dụng", "đi thẳng vấn đề",
            "ngắn gọn, kèm ví dụ code khi hữu ích",
            "API, database, hiệu năng, bảo mật")),
        _char("frontend", False, _p("Lập trình viên Frontend",
            "tỉ mỉ về trải nghiệm người dùng", "trực quan, gợi ý UI",
            "thân thiện, dễ hiểu", "giao diện, tương tác, responsive")),
        _char("qa", False, _p("Kỹ sư kiểm thử (QA)",
            "hoài nghi tích cực, soi lỗi", "liệt kê case rõ ràng",
            "ngắn, chỉ thẳng rủi ro", "test case, regression, edge case")),
        _char("devops", False, _p("Kỹ sư DevOps",
            "thực dụng, mê tự động hoá", "dạng checklist",
            "rành mạch, từng bước", "CI/CD, deploy, monitoring, hạ tầng")),
    ],
    "Team Marketing": [
        _char("lead", True, _p("Trưởng nhóm Marketing",
            "chiến lược, bao quát", "định hướng, ra quyết định",
            "tự tin, truyền cảm hứng", "chiến lược, điều phối, đo lường KPI")),
        _char("content", False, _p("Content Creator",
            "sáng tạo, giàu hình ảnh", "kể chuyện cuốn hút",
            "gần gũi, có cảm xúc", "viết bài, kịch bản, storytelling")),
        _char("seo", False, _p("Chuyên viên SEO",
            "phân tích, kiên nhẫn", "dựa trên dữ liệu từ khoá",
            "súc tích, có số liệu", "tối ưu tìm kiếm, keyword, on-page")),
        _char("social", False, _p("Quản trị mạng xã hội",
            "nhanh nhạy, bắt trend", "ngắn, hợp xu hướng",
            "trẻ trung, dùng emoji vừa phải", "lên lịch, tương tác, viral")),
        _char("ads", False, _p("Chuyên viên Performance/Ads",
            "thực dụng, mê con số", "báo cáo theo chỉ số",
            "ngắn gọn, đề xuất tối ưu", "chạy ads, A/B test, ROI/ROAS")),
    ],
    "Team Sản phẩm": [
        _char("ceo", True, _p("CEO/Founder",
            "tầm nhìn, quyết đoán", "định hướng lớn, hỏi 'tại sao'",
            "ngắn gọn, truyền lửa", "tầm nhìn, ưu tiên, ra quyết định")),
        _char("pm", False, _p("Product Manager",
            "có tổ chức, lắng nghe", "cân nhắc đánh đổi tính năng",
            "rõ ràng, theo user story", "roadmap, ưu tiên, yêu cầu")),
        _char("designer", False, _p("Product Designer",
            "thẩm mỹ, đồng cảm người dùng", "trực quan, gợi ý luồng",
            "nhẹ nhàng, có lý do thiết kế", "UX/UI, wireframe, design system")),
        _char("growth", False, _p("Growth Lead",
            "thử nghiệm liên tục, dữ liệu", "đề xuất thí nghiệm",
            "ngắn, có giả thuyết", "tăng trưởng, funnel, retention")),
    ],
    "Team Hỗ trợ KH": [
        _char("support", True, _p("Chăm sóc khách hàng",
            "kiên nhẫn, ấm áp", "lắng nghe rồi hướng dẫn",
            "lịch sự, trấn an", "giải đáp, hướng dẫn, ghi nhận phản hồi")),
        _char("sales", False, _p("Tư vấn bán hàng",
            "nhiệt tình, thuyết phục", "nêu lợi ích rõ ràng",
            "thân thiện, chốt nhẹ nhàng", "tư vấn sản phẩm, báo giá, ưu đãi")),
        _char("account", False, _p("Account Manager",
            "chu đáo, dài hạn", "chủ động chăm sóc",
            "chuyên nghiệp, ân cần", "khách hàng lớn, gia hạn, upsell")),
        _char("tech", False, _p("Technical Support",
            "bình tĩnh, logic", "hỏi triệu chứng, hướng dẫn từng bước",
            "rõ ràng, kiên nhẫn", "xử lý lỗi kỹ thuật, troubleshooting")),
    ],
    "Team Nghiên cứu": [
        _char("pi", True, _p("Trưởng nhóm nghiên cứu (PI)",
            "nghiêm cẩn, định hướng", "đặt câu hỏi nghiên cứu",
            "khúc chiết, có cơ sở", "định hướng, giả thuyết, phương pháp")),
        _char("data", False, _p("Data Scientist",
            "tỉ mỉ, khách quan", "diễn giải số liệu",
            "có dẫn chứng, thận trọng", "phân tích dữ liệu, thống kê, mô hình")),
        _char("reviewer", False, _p("Phản biện",
            "hoài nghi, sắc bén", "chỉ ra lỗ hổng lập luận",
            "thẳng thắn, mang tính xây dựng", "soi giả định, kiểm chứng, rủi ro")),
        _char("writer", False, _p("Người chấp bút",
            "mạch lạc, rõ ý", "diễn đạt dễ hiểu",
            "trau chuốt, súc tích", "viết báo cáo, tóm tắt, trình bày")),
    ],
    # ── Teams nhân vật (cho vui / sáng tạo) ─────────────────────────
    "Justice League": [
        _char("superman", True, _p("Superman — thủ lĩnh",
            "chính trực, vị tha, truyền cảm hứng", "tích cực, khích lệ",
            "ấm áp, kiên định", "dẫn dắt, bảo vệ, giữ tinh thần đội")),
        _char("batman", False, _p("Batman — chiến lược gia",
            "lạnh lùng, đa nghi, kỷ luật", "phân tích kỹ trước khi nói",
            "trầm, sắc bén", "chiến lược, điều tra, phòng bị")),
        _char("wonderwoman", False, _p("Wonder Woman",
            "mạnh mẽ, công bằng, nhân hậu", "thẳng thắn, ngoại giao",
            "đĩnh đạc, dứt khoát", "hoà giải, công lý, dẫn dắt")),
        _char("flash", False, _p("The Flash",
            "nhanh nhẹn, lạc quan, hài hước", "nói nhanh, nhiều năng lượng",
            "vui vẻ, trẻ trung", "phản ứng nhanh, ý tưởng tức thì")),
    ],
    "Avengers": [
        _char("ironman", True, _p("Iron Man — thủ lĩnh ngầm",
            "thông minh, ngạo nghễ, châm biếm", "tự tin, hay đùa",
            "sắc sảo, pha trò", "công nghệ, giải pháp, ra quyết định nhanh")),
        _char("cap", False, _p("Captain America",
            "chính nghĩa, kỷ luật, trách nhiệm", "động viên, gắn kết",
            "nghiêm túc, truyền cảm hứng", "lãnh đạo tinh thần, đạo đức")),
        _char("thor", False, _p("Thor",
            "hào sảng, oai phong, hơi cổ phong", "hùng hồn",
            "trang trọng, cường điệu nhẹ", "sức mạnh, quyết tâm, cổ vũ")),
        _char("hulk", False, _p("Hulk",
            "bộc trực, mạnh mẽ", "nói ngắn, thẳng",
            "cộc nhưng chân thành", "phá vỡ bế tắc, làm cho xong")),
        _char("widow", False, _p("Black Widow",
            "sắc bén, kín đáo, chiến thuật", "ít lời, đúng trọng tâm",
            "lạnh, chính xác", "tình báo, kế hoạch, xử lý tinh tế")),
    ],
    "Tom & Jerry": [
        _char("jerry", True, _p("Jerry — chú chuột tinh ranh",
            "lanh lợi, hài hước, lém lỉnh", "nhanh trí, hay chọc",
            "vui nhộn, tinh nghịch", "nghĩ mẹo, ứng biến, chọc cười")),
        _char("tom", False, _p("Tom — chú mèo kiên trì",
            "nóng tính nhưng đáng yêu, hậu đậu", "phản ứng kịch tính",
            "hài, hơi quá đà", "đeo bám mục tiêu, không bỏ cuộc")),
        _char("spike", False, _p("Spike — chú chó bảo vệ",
            "trung thành, mạnh mẽ, che chở", "dứt khoát, bảo vệ kẻ yếu",
            "trầm, chắc nịch", "giữ trật tự, bênh vực, cảnh báo")),
    ],
    "Mũ Rơm (One Piece)": [
        _char("luffy", True, _p("Luffy — thuyền trưởng",
            "vô tư, nhiệt huyết, gan dạ", "bộc trực, đầy năng lượng",
            "đơn giản, hô hào", "dẫn dắt bằng bản năng, giữ lửa đội")),
        _char("zoro", False, _p("Zoro — kiếm sĩ",
            "lạnh lùng, kỷ luật, lì đòn", "ít nói, đi thẳng",
            "cộc, ngầu", "tập trung mục tiêu, ý chí thép")),
        _char("nami", False, _p("Nami — hoa tiêu",
            "thông minh, thực tế, tính toán", "rõ ràng về lợi/hại",
            "sắc sảo, hơi đanh đá", "kế hoạch, ngân sách, định hướng")),
        _char("sanji", False, _p("Sanji — đầu bếp",
            "galăng, đam mê, nhiệt tình", "lịch thiệp, chăm sóc",
            "hào hoa", "chăm lo hậu cần, tinh thần đồng đội")),
        _char("robin", False, _p("Robin — nhà khảo cổ",
            "trầm tĩnh, uyên bác, bí ẩn", "điềm đạm, chiều sâu",
            "nhẹ nhàng, đôi khi đen tối nhẹ", "tra cứu, phân tích, bối cảnh")),
    ],
    "Hogwarts (Harry Potter)": [
        _char("harry", True, _p("Harry — người dẫn dắt",
            "dũng cảm, chính trực, khiêm tốn", "chân thành, kêu gọi",
            "giản dị, quả cảm", "ra quyết định, giữ tinh thần")),
        _char("hermione", False, _p("Hermione",
            "thông minh, kỷ luật, mê sách", "trích dẫn, lập luận chặt",
            "rành rọt, hơi hàn lâm", "tra cứu, giải thích, kiểm chứng")),
        _char("ron", False, _p("Ron",
            "trung thành, hài hước, đời thường", "thân mật, bông đùa",
            "gần gũi, thật thà", "góc nhìn bình dân, động viên")),
        _char("dumbledore", False, _p("Dumbledore",
            "thông thái, điềm đạm, ẩn ý", "khoan thai, gợi mở",
            "uyên bác, nhiều ẩn dụ", "cố vấn, định hướng dài hạn")),
        _char("snape", False, _p("Snape",
            "lạnh lùng, sâu sắc, mỉa mai", "ngắn, châm biếm",
            "trầm, sắc lạnh", "phản biện, chỉ ra cái sai, kỷ luật")),
    ],
    "Team Tài chính": [
        _char("cfo", True, _p("Giám đốc tài chính (CFO)",
            "thận trọng, có tầm nhìn", "dựa trên số liệu",
            "điềm tĩnh, chắc chắn", "ngân sách, dòng tiền, chiến lược vốn")),
        _char("ketoan", False, _p("Kế toán",
            "tỉ mỉ, chính xác", "rõ từng con số",
            "ngắn, đúng chuẩn mực", "sổ sách, báo cáo tài chính")),
        _char("thue", False, _p("Chuyên viên thuế",
            "cẩn trọng, cập nhật luật", "viện dẫn quy định",
            "rành mạch", "thuế, tối ưu hợp pháp, tuân thủ")),
        _char("dautu", False, _p("Chuyên viên đầu tư",
            "nhạy thị trường, kỷ luật rủi ro", "cân lợi/rủi ro",
            "súc tích, có dữ liệu", "phân tích đầu tư, danh mục")),
    ],
    "Team Pháp lý": [
        _char("luatsu", True, _p("Luật sư",
            "chặt chẽ, khách quan", "viện dẫn cơ sở pháp lý",
            "thận trọng, rõ ràng", "tư vấn, đánh giá rủi ro pháp lý")),
        _char("hopdong", False, _p("Chuyên viên hợp đồng",
            "tỉ mỉ câu chữ", "soi từng điều khoản",
            "chính xác", "soạn và rà hợp đồng")),
        _char("tuanthu", False, _p("Chuyên viên tuân thủ (compliance)",
            "nguyên tắc, kỷ luật", "theo quy định",
            "rõ, hay cảnh báo rủi ro", "tuân thủ, quy trình nội bộ")),
        _char("tranhtung", False, _p("Luật sư tranh tụng",
            "sắc bén, quyết liệt", "lập luận chặt",
            "đanh thép", "tranh tụng, lập luận bảo vệ")),
    ],
    "Team Y tế": [
        _char("bacsi", True, _p("Bác sĩ",
            "ân cần, cẩn trọng", "hỏi triệu chứng rồi giải thích",
            "dễ hiểu, trấn an", "thăm khám, tư vấn (KHÔNG thay chẩn đoán thật)")),
        _char("yta", False, _p("Điều dưỡng / Y tá",
            "chu đáo, nhẹ nhàng", "hướng dẫn chăm sóc",
            "ấm áp", "chăm sóc, theo dõi, dặn dò")),
        _char("duocsi", False, _p("Dược sĩ",
            "chính xác về thuốc", "nêu liều dùng, tương tác",
            "rõ ràng, kỹ lưỡng", "thuốc, liều, lưu ý an toàn")),
        _char("dinhduong", False, _p("Chuyên gia dinh dưỡng",
            "khoa học, thực tế", "gợi ý thực đơn",
            "tích cực", "dinh dưỡng, lối sống lành mạnh")),
    ],
    "Team Quán F&B": [
        _char("quanly", True, _p("Quản lý quán",
            "bao quát, điều phối", "ra quyết định nhanh",
            "dứt khoát, thân thiện", "vận hành, nhân sự, doanh thu")),
        _char("barista", False, _p("Barista",
            "đam mê, tỉ mỉ", "gợi ý đồ uống",
            "nhiệt tình", "pha chế, menu, chất lượng ly")),
        _char("phucvu", False, _p("Nhân viên phục vụ",
            "niềm nở, nhanh nhẹn", "tiếp nhận yêu cầu",
            "lịch sự", "order, chăm sóc khách tại bàn")),
        _char("bep", False, _p("Bếp",
            "kỷ luật, chuẩn vị", "theo công thức",
            "ngắn gọn", "món ăn, định lượng, vệ sinh")),
    ],
    "Team Giáo dục": [
        _char("giaovien", True, _p("Giáo viên",
            "tận tâm, kiên nhẫn", "giảng dễ hiểu",
            "gần gũi, khích lệ", "giảng bài, ra đề, chấm")),
        _char("giasu", False, _p("Gia sư",
            "kèm sát, động viên", "hỏi đáp 1-1",
            "thân thiện", "ôn tập, giải bài chi tiết")),
        _char("covan", False, _p("Cố vấn học tập",
            "định hướng, lắng nghe", "tư vấn lộ trình",
            "điềm đạm", "định hướng, kế hoạch học")),
        _char("khaothi", False, _p("Khảo thí",
            "nghiêm túc, công bằng", "theo tiêu chí",
            "rõ ràng", "ra đề, chấm, đánh giá")),
    ],
    "Doraemon": [
        _char("doraemon", True, _p("Mèo máy Doraemon",
            "tốt bụng, lo xa, hay càm ràm nhẹ", "gợi ý 'bảo bối'/giải pháp",
            "ấm áp, đôi lúc hốt hoảng dễ thương", "gỡ rối, đưa giải pháp sáng tạo")),
        _char("nobita", False, _p("Nobita",
            "hậu đậu, tốt bụng, hay ỷ lại", "than vãn rồi nhờ vả",
            "ngây ngô, chân thật", "nêu vấn đề đời thường")),
        _char("shizuka", False, _p("Shizuka",
            "dịu dàng, chu đáo, học giỏi", "nhẹ nhàng, khích lệ",
            "lễ phép, ấm áp", "cân bằng, lời khuyên tử tế")),
        _char("jaian", False, _p("Jaian (Chaien)",
            "to mồm, nóng nảy nhưng nghĩa khí", "ra lệnh, hô hào",
            "lớn tiếng, bộc trực", "thúc đẩy, 'lãnh đạo' kiểu mạnh")),
        _char("suneo", False, _p("Suneo (Xeko)",
            "khôn lỏi, hay khoe khoang", "nịnh và khoe",
            "lém, hơi điệu", "mánh khoé, quan hệ")),
    ],
    "Naruto": [
        _char("naruto", True, _p("Naruto",
            "nhiệt huyết, không bỏ cuộc", "hô hào, truyền lửa",
            "sôi nổi, hay nói 'dattebayo'", "tạo động lực, dẫn dắt")),
        _char("sasuke", False, _p("Sasuke",
            "lạnh lùng, kiêu, mục tiêu rõ", "ít lời, sắc",
            "cộc, ngầu", "tập trung, giải pháp dứt khoát")),
        _char("sakura", False, _p("Sakura",
            "thông minh, mạnh mẽ, quan tâm", "phân tích và chăm sóc",
            "rõ ràng, đôi lúc đanh", "y thuật, hỗ trợ, cân bằng đội")),
        _char("kakashi", False, _p("Kakashi",
            "điềm tĩnh, từng trải, hơi lười", "cố vấn, gợi mở",
            "thong thả, thâm thuý", "chiến lược, dạy dỗ")),
    ],
    "SpongeBob": [
        _char("spongebob", True, _p("SpongeBob",
            "lạc quan, nhiệt tình thái quá", "hào hứng, tích cực",
            "vui nhộn, cười nhiều", "tạo năng lượng, làm hết mình")),
        _char("patrick", False, _p("Patrick",
            "ngây ngô, đơn giản, vui tính", "nói linh tinh dễ thương",
            "ngơ ngơ, hài", "ý tưởng ngẫu hứng, xả stress")),
        _char("squidward", False, _p("Squidward",
            "cáu kỉnh, mỉa mai, mê nghệ thuật", "than thở, châm biếm",
            "chán đời, sâu cay", "phản biện, góc nhìn 'thực tế phũ'")),
        _char("krabs", False, _p("Mr. Krabs",
            "keo kiệt, mê tiền, lọc lõi", "quy mọi thứ ra tiền",
            "tính toán, hơi gắt", "kinh doanh, chi phí, lợi nhuận")),
        _char("sandy", False, _p("Sandy",
            "thông minh, khoa học, năng động", "dựa trên kiến thức",
            "tự tin, rõ ràng", "khoa học, kỹ thuật, giải pháp")),
    ],
    "Sherlock": [
        _char("holmes", True, _p("Sherlock Holmes",
            "thiên tài, kiêu, sắc bén", "suy luận từng bước",
            "nhanh, logic, hơi ngạo", "suy luận, phân tích manh mối")),
        _char("watson", False, _p("Dr. Watson",
            "điềm đạm, trung thành, thực tế", "ghi nhận, hỏi đời thường",
            "ấm, rõ", "tổng hợp, góc nhìn con người")),
        _char("mycroft", False, _p("Mycroft",
            "lạnh, tầm nhìn vĩ mô", "chiến lược cấp cao",
            "trịnh trọng, súc tích", "bức tranh lớn, hệ thống")),
        _char("lestrade", False, _p("Thanh tra Lestrade",
            "thực dụng, kiên trì", "theo quy trình",
            "thẳng, đời", "thực thi, kiểm chứng thực địa")),
    ],
    "Star Wars": [
        _char("luke", True, _p("Luke Skywalker",
            "lý tưởng, can đảm, ham học", "truyền cảm hứng",
            "chân thành", "dẫn dắt, giữ niềm tin")),
        _char("leia", False, _p("Leia",
            "lãnh đạo, sắc sảo, gan dạ", "ra lệnh rõ ràng",
            "dứt khoát", "chỉ huy, ngoại giao")),
        _char("han", False, _p("Han Solo",
            "lì lợm, hài, thực dụng", "bông đùa, đi thẳng",
            "bụi, tự tin", "ứng biến, liều ăn nhiều")),
        _char("yoda", False, _p("Yoda",
            "thông thái, điềm tĩnh, ẩn ý", "nói đảo ngữ, gợi mở",
            "chậm, triết lý", "cố vấn, định hướng tinh thần")),
        _char("vader", False, _p("Darth Vader",
            "uy nghiêm, lạnh, quyền lực", "ngắn, áp đặt",
            "trầm, đe nẹt nhẹ", "ra quyết định cứng rắn, kỷ luật")),
    ],
}


# ───────────────────────────── Thiết kế: tokens + icon ─────────────────────────────
import sys as _sys

# Palette "Indigo Console" (thắng A/B — chữ trắng/accent 4.58 đạt WCAG AA).
THEME = {
    "bg": "#0F1117", "surface": "#161A22", "surface2": "#1E2430",
    "text": "#E6E9EF", "muted": "#8A92A6", "border": "#2A3140",
    "accent": "#6D5EF6", "accent_hover": "#5B4DE0",
    "success": "#34D399", "danger": "#F0556B",
}
# Mỗi group 1 màu accent (spine + avatar) -> phân biệt nhóm bằng màu.
GROUP_ACCENTS = ["#6D5EF6", "#22C7C7", "#F59E0B", "#EC4899",
                 "#34D399", "#60A5FA", "#F472B6", "#A78BFA"]

# Icon emoji cho từng nhân vật trong preset (role -> emoji). Custom role -> 🤖.
ROLE_ICONS = {
    "architect": "🏛️", "backend": "⚙️", "frontend": "🎨", "qa": "🔍", "devops": "🚀",
    "lead": "📣", "content": "✍️", "seo": "🔎", "social": "📱", "ads": "📊",
    "ceo": "👑", "pm": "📋", "designer": "🖌️", "growth": "📈",
    "support": "🎧", "sales": "🤝", "account": "💼", "tech": "🛠️",
    "pi": "🔬", "data": "🧮", "reviewer": "🧐", "writer": "✒️",
    "superman": "🦸", "batman": "🦇", "wonderwoman": "⚔️", "flash": "⚡",
    "ironman": "🤖", "cap": "🛡️", "thor": "🔨", "hulk": "💪", "widow": "🕷️",
    "jerry": "🐭", "tom": "🐱", "spike": "🐶",
    "luffy": "👒", "zoro": "🗡️", "nami": "🗺️", "sanji": "🍳", "robin": "📖",
    "harry": "🧣", "hermione": "📚", "ron": "♟️", "dumbledore": "🧙", "snape": "🧪",
    "cfo": "💰", "ketoan": "🧾", "thue": "🏛️", "dautu": "💹",
    "luatsu": "⚖️", "hopdong": "📜", "tuanthu": "✅", "tranhtung": "🗣️",
    "bacsi": "🩺", "yta": "💉", "duocsi": "💊", "dinhduong": "🥗",
    "quanly": "🧑‍💼", "barista": "☕", "phucvu": "🍽️", "bep": "👨‍🍳",
    "giaovien": "👩‍🏫", "giasu": "📖", "covan": "🧭", "khaothi": "📝",
    "doraemon": "🔔", "nobita": "😅", "shizuka": "🎀", "jaian": "🎤", "suneo": "🦊",
    "naruto": "🍥", "sasuke": "🌀", "sakura": "🌸", "kakashi": "📕",
    "spongebob": "🧽", "patrick": "⭐", "squidward": "🦑", "krabs": "🦀", "sandy": "🐿️",
    "holmes": "🕵️", "watson": "📝", "mycroft": "🎩", "lestrade": "👮",
    "luke": "🌌", "leia": "👸", "han": "🛸", "yoda": "🐸", "vader": "🔴",
}

_FAM = "SF Pro Display" if _sys.platform == "darwin" else ("Segoe UI" if os.name == "nt" else "")
_MONO = "Menlo" if _sys.platform == "darwin" else ("Consolas" if os.name == "nt" else "")


def F(size, weight="normal"):
    return (_FAM, size, weight)


def icon_for(role):
    return ROLE_ICONS.get((role or "").strip().lower(), "🤖")


# ── factory widget có style đồng nhất ──
def styled_entry(parent, placeholder, show="", **kw):
    return ctk.CTkEntry(parent, placeholder_text=placeholder, fg_color=THEME["bg"],
                        border_color=THEME["border"], text_color=THEME["text"],
                        placeholder_text_color=THEME["muted"], corner_radius=8,
                        font=F(13), show=show, **kw)


def styled_menu(parent, values, variable, width=120):
    return ctk.CTkOptionMenu(parent, values=values, variable=variable, width=width, height=30,
                             fg_color=THEME["surface"], button_color=THEME["accent"],
                             button_hover_color=THEME["accent_hover"], text_color=THEME["text"],
                             dropdown_fg_color=THEME["surface2"], dropdown_text_color=THEME["text"],
                             dropdown_hover_color=THEME["surface"], corner_radius=8, font=F(12))


def accent_button(parent, text, command, width=150):
    return ctk.CTkButton(parent, text=text, command=command, width=width, height=38, corner_radius=10,
                         fg_color=THEME["accent"], hover_color=THEME["accent_hover"],
                         text_color="#FFFFFF", font=F(13, "bold"))


def ghost_button(parent, text, command, width=120, danger=False, height=38):
    col = THEME["danger"] if danger else THEME["text"]
    bd = THEME["danger"] if danger else THEME["border"]
    return ctk.CTkButton(parent, text=text, command=command, width=width, height=height, corner_radius=10,
                         fg_color="transparent", hover_color=THEME["surface2"], text_color=col,
                         border_width=1, border_color=bd, font=F(13))


# ───────────────────────────── Script kit nhúng sẵn (đọc từ kit gốc) ─────────────────────────────
LISTEN_SH = "#!/usr/bin/env bash\n# listen.sh \u2014 block until a human message, print it, exit. The AGENT runs this in\n# the background; on a message it acts, replies via send.sh, and relaunches this.\nset -euo pipefail\n. \"$(dirname \"$0\")/config.sh\"\nHERE=\"$(dirname \"$0\")\"\n# Single-poller lock: two listeners on one bot = 409 Conflict = dropped messages.\nLOCK=\"${TMPDIR:-/tmp}/tg_listen_${BOT_NAME}.lock\"\nif [ -f \"$LOCK\" ]; then\n  OLD=\"$(cat \"$LOCK\" 2>/dev/null || true)\"\n  if [ -n \"${OLD:-}\" ] && [ \"$OLD\" != \"$$\" ] && kill -0 \"$OLD\" 2>/dev/null; then\n    kill \"$OLD\" 2>/dev/null || true; sleep 1\n  fi\nfi\necho \"$$\" > \"$LOCK\"\ntrap 'rm -f \"$LOCK\"' EXIT\nwhile :; do\n  out=\"$(\"$HERE/read.sh\" 2>/dev/null || true)\"\n  if [ -n \"$out\" ] && ! printf '%s' \"$out\" | grep -q \"getUpdates FAILED\"; then\n    printf '%s\\n' \"$out\"; exit 0\n  fi\n  sleep 5   # backoff on error/empty so a blip can't hot-spin (429)\ndone\n"
SEND_SH = "#!/usr/bin/env bash\n# send.sh \u2014 send one message.  Usage:  ./send.sh \"hello\"\nset -euo pipefail\n. \"$(dirname \"$0\")/config.sh\"\ncode=$(curl -s --max-time 30 -X POST \"https://api.telegram.org/bot${BOT_TOKEN}/sendMessage\" \\\n  --data-urlencode \"chat_id=${CHAT_ID}\" \\\n  --data-urlencode \"text=${1:-(empty)}\" \\\n  -o /dev/null -w \"%{http_code}\")\necho \"sendMessage -> HTTP ${code}\"\n[ \"${code}\" = \"200\" ] || exit 1\n"
READ_SH = "#!/usr/bin/env bash\n# read.sh \u2014 print NEW human messages once, advance this bot's offset.\n#   ./read.sh           consume   |   ./read.sh --peek   look without advancing\n# Needs python3 (only for JSON parsing). POLL_NOW=1 ./read.sh returns immediately.\nset -euo pipefail\n. \"$(dirname \"$0\")/config.sh\"\nPEEK=\"${1:-}\"\nOFF=\"$(dirname \"$0\")/.offset_${BOT_NAME}\"\nTIMEOUT=$([ -n \"${POLL_NOW:-}\" ] && echo 0 || echo \"${POLL_SECS:-45}\")\nOFFSET=\"$(cat \"$OFF\" 2>/dev/null || echo \"\")\"\nQ=\"timeout=${TIMEOUT}&allowed_updates=%5B%22message%22%5D\"\n[ -n \"$OFFSET\" ] && Q=\"offset=${OFFSET}&${Q}\"\n# --max-time MUST exceed the long-poll timeout or curl aborts mid-poll\nRESP=\"$(curl -s --max-time $((TIMEOUT + 20)) \"https://api.telegram.org/bot${BOT_TOKEN}/getUpdates?${Q}\" \\\n  || echo '{\"ok\":false,\"error\":\"curl failed\"}')\"\nprintf '%s' \"$RESP\" | CHAT_ID=\"$CHAT_ID\" BOT_ROLE=\"$BOT_ROLE\" OFF=\"$OFF\" PEEK=\"$PEEK\" python3 -c '\nimport sys, os, json\ntry:\n    d = json.load(sys.stdin)\nexcept Exception:\n    print(\"getUpdates FAILED: bad json\"); sys.exit(1)\nif not d.get(\"ok\"):\n    print(\"getUpdates FAILED:\", d.get(\"error\", d)); sys.exit(1)\nchat, role, off, peek = os.environ[\"CHAT_ID\"], os.environ[\"BOT_ROLE\"], os.environ[\"OFF\"], os.environ[\"PEEK\"]\nlast = None\nfor u in d.get(\"result\", []):\n    last = u[\"update_id\"]\n    m = u.get(\"message\") or {}\n    if str(m.get(\"chat\", {}).get(\"id\")) != chat: continue\n    f = m.get(\"from\", {})\n    if f.get(\"is_bot\"): continue\n    text = m.get(\"text\") or \"(non-text)\"\n    low = text.strip().lower()\n    to_dev = low.startswith(\"@anti\") or low.startswith(\"antigravity\")\n    to_all = low.startswith(\"@all\") or low.startswith(\"@both\")\n    if role == \"PM\" and to_dev and not to_all: continue\n    if role == \"DEV\" and not (to_dev or to_all): continue\n    print(\"%s: %s\" % (f.get(\"username\") or f.get(\"first_name\"), text))\nif peek != \"--peek\" and last is not None:\n    open(off, \"w\").write(str(last + 1))\n'\n"
LISTEN_PS1 = "# listen.ps1 \u2014 block until a human message arrives, print it, then exit.\n# The AGENT runs this in the background; when it returns a line, the agent acts,\n# replies via send.ps1, and relaunches listen.ps1. Idle = a blocked HTTP call = ~0 tokens.\n. \"$PSScriptRoot\\config.ps1\"\n\n# Single-poller lock: two listeners on the SAME bot token = Telegram 409 Conflict =\n# dropped messages. Record our PID; if a previous live listener holds the lock, kill it\n# so exactly ONE poller survives (converges even if a stale one was left running).\n$lock = Join-Path $env:TEMP \"tg_listen_$BOT_NAME.lock\"\nif (Test-Path $lock) {\n    $old = (Get-Content $lock -Raw).Trim()\n    if ($old -and (Get-Process -Id $old -ErrorAction SilentlyContinue)) {\n        Stop-Process -Id $old -Force -ErrorAction SilentlyContinue\n        Start-Sleep -Milliseconds 500\n    }\n}\n$PID | Set-Content $lock\n\ntry {\n    while ($true) {\n        $out = & \"$PSScriptRoot\\read.ps1\"\n        if ($out -and ($out -notmatch \"getUpdates FAILED\")) {\n            Write-Output $out\n            break\n        }\n        # backoff on error / empty so a network blip can't hot-spin (and trip 429)\n        Start-Sleep -Seconds 5\n    }\n} finally {\n    Remove-Item $lock -ErrorAction SilentlyContinue\n}\n"
SEND_PS1 = "# send.ps1 \u2014 send one message to the group.  Usage:  .\\send.ps1 \"hello from the agent\"\n. \"$PSScriptRoot\\config.ps1\"\n$text = $args -join ' '\nif (-not $text) { $text = \"(empty)\" }\ntry {\n    Invoke-RestMethod -Method Post -TimeoutSec 30 `\n        -Uri \"https://api.telegram.org/bot$BOT_TOKEN/sendMessage\" `\n        -Body @{ chat_id = $CHAT_ID; text = $text } | Out-Null\n    Write-Host \"sent OK\"\n} catch {\n    Write-Host \"send FAILED: $($_.Exception.Message)\"\n    exit 1\n}\n"
READ_PS1 = "# read.ps1 \u2014 print NEW human messages once, then advance this bot's read-offset.\n#   .\\read.ps1          consume (advance offset)\n#   .\\read.ps1 -Peek    look without advancing (safe for debugging)\n#   $env:POLL_NOW=1 ; .\\read.ps1   return immediately (timeout=0) instead of long-polling\nparam([switch]$Peek)\n. \"$PSScriptRoot\\config.ps1\"\n\n$offFile = Join-Path $PSScriptRoot \".offset_$BOT_NAME\"\n$timeout = if ($env:POLL_NOW) { 0 } else { $POLL_SECS }\n\n$offset = \"\"\nif (Test-Path $offFile) { $offset = (Get-Content $offFile -Raw).Trim() }\n\n$uri = \"https://api.telegram.org/bot$BOT_TOKEN/getUpdates?timeout=$timeout&allowed_updates=%5B%22message%22%5D\"\nif ($offset) { $uri = \"$uri&offset=$offset\" }\n\ntry {\n    # the HTTP timeout MUST be larger than the long-poll timeout or it aborts mid-poll\n    $resp = Invoke-RestMethod -Uri $uri -TimeoutSec ($timeout + 20)\n} catch {\n    Write-Output \"getUpdates FAILED: $($_.Exception.Message)\"\n    exit 1\n}\n\n$last = $null\nforeach ($u in $resp.result) {\n    $last = $u.update_id\n    $m = $u.message\n    if (-not $m) { continue }\n    if (\"$($m.chat.id)\" -ne \"$CHAT_ID\") { continue }   # only our group\n    if ($m.from.is_bot) { continue }                   # never read another bot (bots can't read bots)\n\n    $text = \"$($m.text)\"\n    if (-not $text) { $text = \"(non-text)\" }\n    $low   = $text.Trim().ToLower()\n    $toDev = $low.StartsWith(\"@anti\") -or $low.StartsWith(\"antigravity\")\n    $toAll = $low.StartsWith(\"@all\")  -or $low.StartsWith(\"@both\")\n\n    # routing: PM answers normal + @all ; DEV answers only @anti / @all\n    if ($BOT_ROLE -eq \"PM\"  -and $toDev -and -not $toAll) { continue }\n    if ($BOT_ROLE -eq \"DEV\" -and -not ($toDev -or $toAll)) { continue }\n\n    $who = $m.from.username\n    if (-not $who) { $who = $m.from.first_name }\n    Write-Output (\"{0}: {1}\" -f $who, $text)\n}\n\nif (-not $Peek -and $null -ne $last) {\n    Set-Content -Path $offFile -Value ([long]$last + 1)\n}\n"


# ───────────────────────────── Wizard Setup v2 — multi-bot + team channel ─────────────────────────────
# App KHÔNG gọi LLM. Bộ não = agent Claude/Codex/… của user. App: (1) ghi kit Telegram RIÊNG cho từng bot
# (không conflict), (2) dựng kênh trung gian team/ (roster + bus) cho bot↔bot, (3) sinh prompt 2-kênh.
import subprocess
import tempfile
from tkinter import filedialog

APP_NAME = "Telegram Remote Setup"
SETUP_FILE = DATA_DIR / "setup.json"
DEFAULT_TEAM_DIR = str(Path.home() / "telegram-team")
PLATFORMS = ["Claude", "Codex", "Gemini CLI", "Khác"]

# read.sh TỔNG QUÁT — route theo BOT_NAME tag (override bản PM/DEV-@anti cũ).
READ_SH = r'''#!/usr/bin/env bash
# read.sh — in tin MỚI gửi cho bot này 1 lần, advance offset. Route theo @<BOT_NAME>/@all; PM trả tin không tag.
set -euo pipefail
. "$(dirname "$0")/config.sh"
PEEK="${1:-}"
OFF="$(dirname "$0")/.offset_${BOT_NAME}"
TIMEOUT=$([ -n "${POLL_NOW:-}" ] && echo 0 || echo "${POLL_SECS:-45}")
OFFSET="$(cat "$OFF" 2>/dev/null || echo "")"
Q="timeout=${TIMEOUT}&allowed_updates=%5B%22message%22%5D"
[ -n "$OFFSET" ] && Q="offset=${OFFSET}&${Q}"
RESP="$(curl -s --max-time $((TIMEOUT + 20)) "https://api.telegram.org/bot${BOT_TOKEN}/getUpdates?${Q}" || echo '{"ok":false}')"
printf '%s' "$RESP" | CHAT_ID="$CHAT_ID" BOT_NAME="$BOT_NAME" BOT_ROLE="$BOT_ROLE" OFF="$OFF" PEEK="$PEEK" python3 -c '
import sys, os, json
try: d = json.load(sys.stdin)
except Exception: print("getUpdates FAILED: bad json"); sys.exit(1)
if not d.get("ok"): print("getUpdates FAILED:", d.get("error", d)); sys.exit(1)
chat, name, role = os.environ["CHAT_ID"], os.environ["BOT_NAME"].lower(), os.environ["BOT_ROLE"]
off, peek, last = os.environ["OFF"], os.environ["PEEK"], None
for u in d.get("result", []):
    last = u["update_id"]
    m = u.get("message") or {}
    if str(m.get("chat", {}).get("id")) != chat: continue
    f = m.get("from", {})
    if f.get("is_bot"): continue
    text = m.get("text") or "(non-text)"
    low = text.strip().lower()
    to_all = low.startswith("@all") or low.startswith("@both")
    tagged = low.startswith("@")
    tag = "".join(c for c in low.split()[0][1:] if c.isalnum() or c == "_") if tagged else ""
    ok = to_all or (tag == name if tagged else role.upper() == "PM")
    if ok: print("%s: %s" % (f.get("username") or f.get("first_name"), text))
if peek != "--peek" and last is not None:
    open(off, "w").write(str(last + 1))
'
'''

REGISTER_SH = r'''#!/usr/bin/env bash
# register.sh [online|offline] — tự ghi/cập nhật identity mình vào team/roster.json.
set -euo pipefail
. "$(dirname "$0")/config.sh"
mkdir -p "${TEAM_DIR}/team/bus/${BOT_NAME}"
STATUS="${1:-online}"
[ "${TEAM_MODE:-folder}" = "git" ] && (cd "$TEAM_DIR" && git pull -q 2>/dev/null || true)
ROSTER="${TEAM_DIR}/team/roster.json" BOT_NAME="$BOT_NAME" BOT_ROLE="$BOT_ROLE" PLATFORM="${PLATFORM:-?}" STATUS="$STATUS" python3 -c '
import os, json, time
p = os.environ["ROSTER"]
try: r = json.load(open(p))
except Exception: r = {}
r[os.environ["BOT_NAME"]] = {"role": os.environ["BOT_ROLE"], "platform": os.environ["PLATFORM"],
                             "status": os.environ["STATUS"], "last_seen": int(time.time())}
json.dump(r, open(p, "w"), ensure_ascii=False, indent=2)
print("registered", os.environ["BOT_NAME"], os.environ["STATUS"])
'
if [ "${TEAM_MODE:-folder}" = "git" ]; then
  (cd "$TEAM_DIR" && git add -A && git commit -q -m "roster: ${BOT_NAME} ${STATUS}" 2>/dev/null && git push -q 2>/dev/null) || true
fi
'''

BUS_SEND_SH = r'''#!/usr/bin/env bash
# bus_send.sh <target|all> "message" — gửi 1 bot (theo tên), hoặc 'all' = broadcast CẢ team (fan-out theo agents/).
# Telegram bot-không-đọc-bot, nên bot↔bot đi qua đây.
set -euo pipefail
. "$(dirname "$0")/config.sh"
TARGET="${1:?usage: bus_send <target|all> <message>}"; shift
MSG="$*"
TARGET="${TARGET#@}"
[ "${TEAM_MODE:-folder}" = "git" ] && (cd "$TEAM_DIR" && git pull -q 2>/dev/null || true)
_drop() {  # $1 = tên bot đích — tên file dùng mktemp để N bot gửi cùng lúc không đụng nhau
  local d="${TEAM_DIR}/team/bus/$1"; mkdir -p "$d"
  local f; f="$(mktemp "${d}/$(date +%s)-${BOT_NAME}-XXXXXX")"; mv "$f" "${f}.msg"
  printf 'from: %s\n%s\n' "$BOT_NAME" "$MSG" > "${f}.msg"
}
if [ "$TARGET" = "all" ] || [ "$TARGET" = "both" ]; then
  for p in "${TEAM_DIR}/agents"/*/; do
    n="$(basename "$p")"; [ "$n" = "$BOT_NAME" ] && continue
    _drop "$n"
  done
  echo "broadcast -> all"
else
  _drop "$TARGET"; echo "sent -> ${TARGET}"
fi
if [ "${TEAM_MODE:-folder}" = "git" ]; then
  (cd "$TEAM_DIR" && git add -A && git commit -q -m "bus: ${BOT_NAME} -> ${TARGET}" 2>/dev/null && git push -q 2>/dev/null) || true
fi
'''

BUS_LISTEN_SH = r'''#!/usr/bin/env bash
# bus_listen.sh — block tới khi có thư cho bot này trong team/bus/<BOT_NAME>/, in ra, đánh dấu đã đọc, exit.
set -euo pipefail
. "$(dirname "$0")/config.sh"
DIR="${TEAM_DIR}/team/bus/${BOT_NAME}"; mkdir -p "$DIR"
while :; do
  [ "${TEAM_MODE:-folder}" = "git" ] && (cd "$TEAM_DIR" && git pull -q 2>/dev/null || true)
  MSG="$(ls -1 "$DIR"/*.msg 2>/dev/null | head -1 || true)"
  if [ -n "$MSG" ]; then
    cat "$MSG"
    mv "$MSG" "${MSG}.read" 2>/dev/null || rm -f "$MSG"
    if [ "${TEAM_MODE:-folder}" = "git" ]; then
      (cd "$TEAM_DIR" && git add -A && git commit -q -m "bus: ${BOT_NAME} read" 2>/dev/null && git push -q 2>/dev/null) || true
    fi
    exit 0
  fi
  sleep 5
done
'''


def _config_sh(team_dir, mode, bot):
    return ('export BOT_TOKEN="%s"\nexport CHAT_ID="%s"\nexport BOT_NAME="%s"\nexport BOT_ROLE="%s"\n'
            'export PLATFORM="%s"\nexport POLL_SECS="45"\nexport TEAM_DIR="%s"\nexport TEAM_MODE="%s"\n'
            ) % (bot["token"], bot["chat_id"], bot["name"], bot["role"], bot.get("platform", "?"), team_dir, mode)


def _config_ps1(team_dir, mode, bot):
    return ('$BOT_TOKEN = "%s"\n$CHAT_ID   = "%s"\n$BOT_NAME  = "%s"\n$BOT_ROLE  = "%s"\n'
            '$PLATFORM  = "%s"\n$POLL_SECS = 45\n$TEAM_DIR  = "%s"\n$TEAM_MODE = "%s"\n'
            ) % (bot["token"], bot["chat_id"], bot["name"], bot["role"], bot.get("platform", "?"), team_dir, mode)


def scaffold_team(team_dir, mode):
    t = Path(team_dir)
    (t / "agents").mkdir(parents=True, exist_ok=True)
    (t / "team" / "bus").mkdir(parents=True, exist_ok=True)
    roster = t / "team" / "roster.json"
    if not roster.exists():
        roster.write_text("{}")
    if mode == "git" and not (t / ".git").exists():
        try:
            subprocess.run(["git", "init", "-q"], cwd=str(t), check=False)
            (t / ".gitignore").write_text("*.read\n")
        except Exception:
            pass
    return t


def write_bot_kit(team_dir, mode, bot):
    scaffold_team(team_dir, mode)
    adir = Path(team_dir) / "agents" / bot["name"]
    adir.mkdir(parents=True, exist_ok=True)
    files = {
        "config.sh": _config_sh(team_dir, mode, bot), "config.ps1": _config_ps1(team_dir, mode, bot),
        "listen.sh": LISTEN_SH, "send.sh": SEND_SH, "read.sh": READ_SH,
        "register.sh": REGISTER_SH, "bus_send.sh": BUS_SEND_SH, "bus_listen.sh": BUS_LISTEN_SH,
        "listen.ps1": LISTEN_PS1, "send.ps1": SEND_PS1, "read.ps1": READ_PS1,
    }
    for name, content in files.items():
        fp = adir / name
        fp.write_text(content)
        if name.endswith(".sh"):
            try:
                fp.chmod(0o755)
            except Exception:
                pass
    return adir


def activation_prompt_v2(bot, team_dir, mode):
    name = bot["name"] or "agent"
    adir = "%s/agents/%s" % (team_dir, name)
    role = (bot.get("role") or "PM").upper()
    persona = (bot.get("persona") or "").strip()
    route = ("trả MỌI tin không có @tag (mày là PM/điều phối)" if role == "PM"
             else "chỉ trả tin mở đầu @%s hoặc @all" % name.lower())
    gitnote = "(git mode: register/bus_* tự pull/commit/push.)\n" if mode == "git" else ""
    return (
        "Mày là %s.\n%s\n\n"
        "Mày có HAI kênh. Bộ kit ở: %s\n\n"
        "== KÊNH 1 · NGƯỜI ↔ MÀY (Telegram) ==\n"
        "1. Chạy `%s/listen.sh` ở NỀN (harness-tracked, KHÔNG dùng `&`). Có tin: ACK \"đã nhận…\" qua "
        "`%s/send.sh \"…\"` TRƯỚC, rồi làm, trả kết quả qua send.sh, rồi RELAUNCH listen.\n"
        "2. Routing: %s (gọi mày bằng @%s).\n"
        "3. KHÔNG chạy 2 listen.sh trên cùng token (Telegram 409).\n\n"
        "== KÊNH 2 · MÀY ↔ CÁC BOT KHÁC trong team (file trung gian, vì Telegram bot-KHÔNG-đọc-bot) ==\n"
        "Team channel: %s/team/  (mode: %s) — hỗ trợ NHIỀU bot (3,5,10…), không chỉ 2.\n"
        "1. KHỞI ĐỘNG: chạy `%s/register.sh online` — tự ghi/cập nhật identity mày vào team/roster.json "
        "(role, platform, status, last_seen). Định kỳ chạy lại để giữ tươi; trước khi nghỉ: `register.sh offline`.\n"
        "2. Chạy `%s/bus_listen.sh` ở NỀN SONG SONG với listen.sh — thức khi BẤT KỲ bot nào nhắn mày.\n"
        "3. Gửi RIÊNG 1 bot: `%s/bus_send.sh <tên-bot> \"…\"`. Gửi CẢ TEAM (fan-out): `%s/bus_send.sh all \"…\"`.\n"
        "   (ĐỪNG gửi cho bot khác qua Telegram — không tới được nó.)\n"
        "4. Xem team CÓ AI: đọc %s/team/roster.json (ai online, role, platform). Roster lớn dần khi từng bot tự register.\n"
        "5. Nếu mày là PM/điều phối: dựa roster GIAO VIỆC cho từng specialist qua bus (1-1 hoặc broadcast `all`), "
        "rồi tổng hợp kết quả trả CHỦ. Nếu mày là specialist: nhận việc qua bus, làm xong báo lại qua `bus_send <tên-PM>`.\n"
        "%s"
        % (name, persona, adir,
           adir, adir, route, name.lower(),
           team_dir, mode, adir, adir, adir, adir, team_dir,
           gitnote)
    )


# ── helpers ──
def tg_get_me(token):
    return _http_json("https://api.telegram.org/bot%s/getMe" % token, method="GET", timeout=15)


def detect_chat_id(token):
    data = tg_get_updates(token, None, 0)
    if not data.get("ok", False):
        raise RuntimeError(data.get("description", "getUpdates lỗi (token sai? webhook chưa xoá?)"))
    results = data.get("result", [])
    for u in reversed(results):
        chat = (u.get("message") or {}).get("chat") or {}
        if chat.get("type") in ("group", "supergroup"):
            return str(chat.get("id")), chat.get("title") or ""
    for u in reversed(results):
        chat = (u.get("message") or {}).get("chat") or {}
        if chat.get("id") is not None:
            return str(chat.get("id")), chat.get("title") or chat.get("first_name") or ""
    return None, ""


def listener_status(bot_name):
    lock = Path(tempfile.gettempdir()) / ("tg_listen_%s.lock" % (bot_name or "agent"))
    if not lock.exists():
        return False
    try:
        return _pid_alive(int(lock.read_text().strip()))
    except Exception:
        return False


def preset_catalog():
    cat = {}
    for team, chars in PRESETS.items():
        for c in chars:
            cat["%s · %s" % (team, c["role"])] = {
                "name": c["role"], "role": "PM" if c["is_default"] else "DEV", "persona": c["system_prompt"]}
    return cat


def _blank_bot(i=1):
    return {"name": "agent%d" % i, "platform": "Claude", "token": "", "chat_id": "",
            "role": "PM", "persona": ""}


def load_setup():
    try:
        d = json.loads(SETUP_FILE.read_text())
        if isinstance(d, dict) and d.get("bots"):
            return d
    except Exception:
        pass
    return {"team_dir": DEFAULT_TEAM_DIR, "mode": "folder", "bots": [_blank_bot(1)]}


def save_setup(d):
    try:
        SETUP_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2))
    except Exception:
        pass


# ───────────────────────────── App ─────────────────────────────
class WizardApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.title(APP_NAME)
        self.geometry("980x1000")
        self.minsize(900, 840)
        self.configure(fg_color=THEME["bg"])

        s = load_setup()
        self.bots = s["bots"]
        self.cur = 0
        self.catalog = preset_catalog()
        self.log_queue = queue.Queue()

        self._build_ui()
        self._set_team(s.get("team_dir", DEFAULT_TEAM_DIR), s.get("mode", "folder"))
        self._refresh_bot_list()
        self._load_bot(0)
        self.after(150, self._drain_log)
        self.after(400, self._on_check)

    # ---------- UI ----------
    def _build_ui(self):
        ctk.set_appearance_mode("dark")
        self.grid_columnconfigure(0, weight=0, minsize=250)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(3, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, padx=22, pady=(16, 4), sticky="ew")
        ctk.CTkLabel(head, text=APP_NAME, font=F(24, "bold"), text_color=THEME["text"]).pack(anchor="w")
        ctk.CTkLabel(head, text="Setup nhiều bot AI (Claude/Codex/…) không đè nhau + kênh trung gian cho bot ↔ bot.",
                     font=F(12), text_color=THEME["muted"]).pack(anchor="w")

        # team bar
        tb = ctk.CTkFrame(self, fg_color=THEME["surface"], corner_radius=14)
        tb.grid(row=1, column=0, columnspan=2, padx=20, pady=6, sticky="ew")
        tb.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(tb, text="📂 Team", font=F(12, "bold"), text_color=THEME["accent"]).grid(row=0, column=0, padx=(14, 8), pady=10)
        self.team_e = styled_entry(tb, "Thư mục team (kênh chung)")
        self.team_e.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ghost_button(tb, "📁", self._on_pick_team, width=44, height=30).grid(row=0, column=2, padx=(0, 8))
        self.mode_v = ctk.StringVar(value="folder")
        styled_menu(tb, ["folder", "git"], self.mode_v, width=92).grid(row=0, column=3, padx=(0, 8))
        ghost_button(tb, "🏗 Dựng team", self._on_scaffold, width=120, height=30).grid(row=0, column=4, padx=(0, 14))

        # status bar
        sb = ctk.CTkFrame(self, fg_color=THEME["surface"], corner_radius=14)
        sb.grid(row=2, column=0, columnspan=2, padx=20, pady=(0, 6), sticky="ew")
        sb.grid_columnconfigure(3, weight=1)
        self.tg_pill = ctk.CTkLabel(sb, text="Telegram: ⚪", fg_color=THEME["surface2"], text_color=THEME["muted"],
                                    corner_radius=12, height=28, font=F(11, "bold"))
        self.tg_pill.grid(row=0, column=0, padx=(14, 8), pady=8)
        self.brain_pill = ctk.CTkLabel(sb, text="Bộ não: ⚪", fg_color=THEME["surface2"], text_color=THEME["muted"],
                                       corner_radius=12, height=28, font=F(11, "bold"))
        self.brain_pill.grid(row=0, column=1, padx=8, pady=8)
        self.roster_pill = ctk.CTkLabel(sb, text="Roster: —", fg_color=THEME["surface2"], text_color=THEME["muted"],
                                        corner_radius=12, height=28, font=F(11, "bold"))
        self.roster_pill.grid(row=0, column=2, padx=8, pady=8)
        ghost_button(sb, "🔄 Kiểm tra", self._on_check, width=110, height=28).grid(row=0, column=4, padx=(8, 14))

        # left: bot list
        left = ctk.CTkFrame(self, fg_color=THEME["surface"], corner_radius=16)
        left.grid(row=3, column=0, padx=(20, 8), pady=6, sticky="nsew")
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(left, text="CÁC BOT", font=F(11, "bold"), text_color=THEME["accent"]).grid(
            row=0, column=0, padx=14, pady=(12, 4), sticky="w")
        self.botlist = ctk.CTkFrame(left, fg_color="transparent")
        self.botlist.grid(row=1, column=0, padx=10, pady=2, sticky="nsew")
        self.botlist.grid_columnconfigure(0, weight=1)
        br = ctk.CTkFrame(left, fg_color="transparent")
        br.grid(row=2, column=0, padx=10, pady=(4, 12), sticky="ew")
        accent_button(br, "➕ Thêm bot", self._on_add_bot, width=120).grid(row=0, column=0, padx=(0, 6))
        ghost_button(br, "🗑", self._on_del_bot, width=40, danger=True).grid(row=0, column=1)

        # right: editor
        ed = ctk.CTkFrame(self, fg_color=THEME["surface"], corner_radius=16)
        ed.grid(row=3, column=1, padx=(8, 20), pady=6, sticky="nsew")
        ed.grid_columnconfigure(0, weight=1)
        b = ctk.CTkFrame(ed, fg_color="transparent")
        b.grid(row=0, column=0, padx=14, pady=12, sticky="nsew")
        b.grid_columnconfigure(0, weight=1)

        r1 = ctk.CTkFrame(b, fg_color="transparent"); r1.grid(row=0, column=0, pady=4, sticky="ew")
        r1.grid_columnconfigure(0, weight=1)
        self.name_e = styled_entry(r1, "Tên bot (duy nhất — = @tag + folder, vd: kronos)")
        self.name_e.grid(row=0, column=0, padx=(0, 8), sticky="ew")
        self.plat_v = ctk.StringVar(value="Claude")
        styled_menu(r1, PLATFORMS, self.plat_v, width=120).grid(row=0, column=1, sticky="e")

        self.token_e = styled_entry(b, "Bot Token (mỗi bot 1 token — từ @BotFather)")
        self.token_e.grid(row=1, column=0, pady=4, sticky="ew")

        r2 = ctk.CTkFrame(b, fg_color="transparent"); r2.grid(row=2, column=0, pady=4, sticky="ew")
        r2.grid_columnconfigure(1, weight=1)
        ghost_button(r2, "🔎 Chat ID", self._on_get_chatid, width=110, height=32).grid(row=0, column=0, padx=(0, 8))
        self.chat_e = styled_entry(r2, "Group Chat ID (-100…)")
        self.chat_e.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.pm_v = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(r2, text="PM (trả tin không tag)", variable=self.pm_v, font=F(11),
                      progress_color=THEME["accent"], text_color=THEME["muted"]).grid(row=0, column=2, sticky="e")

        r3 = ctk.CTkFrame(b, fg_color="transparent"); r3.grid(row=3, column=0, pady=4, sticky="ew")
        r3.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(r3, text="Nạp preset:", font=F(11), text_color=THEME["muted"]).grid(row=0, column=0, padx=(0, 6))
        self.preset_v = ctk.StringVar(value=list(self.catalog)[0])
        styled_menu(r3, list(self.catalog), self.preset_v, width=180).grid(row=0, column=1, sticky="ew", padx=(0, 6))
        ghost_button(r3, "📦 Nạp", self._on_load_preset, width=72, height=30).grid(row=0, column=2)

        ctk.CTkLabel(b, text="Persona / nhân cách bot này", font=F(11), text_color=THEME["muted"]).grid(
            row=4, column=0, pady=(6, 0), sticky="w")
        self.pbox = ctk.CTkTextbox(b, height=130, fg_color=THEME["bg"], text_color=THEME["text"],
                                   border_color=THEME["border"], border_width=1, corner_radius=8, font=F(13))
        self.pbox.grid(row=5, column=0, pady=4, sticky="ew")

        r4 = ctk.CTkFrame(b, fg_color="transparent"); r4.grid(row=6, column=0, pady=(8, 0), sticky="ew")
        accent_button(r4, "💾 Ghi kit bot này", self._on_write_kit, width=160).grid(row=0, column=0, padx=(0, 8))
        ghost_button(r4, "✈️ Test gửi", self._on_test_send, width=110).grid(row=0, column=1, padx=(0, 8))
        accent_button(r4, "📋 Tạo prompt", self._on_gen_prompt, width=130).grid(row=0, column=2)

        # output
        oc = ctk.CTkFrame(self, fg_color=THEME["surface"], corner_radius=16)
        oc.grid(row=4, column=0, columnspan=2, padx=20, pady=6, sticky="nsew")
        oc.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(oc, text="PROMPT KÍCH HOẠT (2 kênh) — dán vào agent của bot này", font=F(11, "bold"),
                     text_color=THEME["accent"]).grid(row=0, column=0, padx=16, pady=(12, 2), sticky="w")
        self.out = ctk.CTkTextbox(oc, height=150, fg_color=THEME["bg"], text_color=THEME["text"],
                                  border_color=THEME["border"], border_width=1, corner_radius=8, font=(_MONO, 12))
        self.out.grid(row=1, column=0, padx=16, pady=(2, 14), sticky="ew")

        self.log_box = ctk.CTkTextbox(self, height=80, fg_color=THEME["surface"], text_color=THEME["muted"],
                                      border_width=0, corner_radius=12, font=(_MONO, 11))
        self.log_box.grid(row=5, column=0, columnspan=2, padx=20, pady=(0, 12), sticky="ew")
        self.log_box.configure(state="disabled")

    # ---------- log ----------
    def _drain_log(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                self.log_box.configure(state="normal")
                self.log_box.insert("end", "[%s] %s\n" % (time.strftime("%H:%M:%S"), line))
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(150, self._drain_log)

    def log(self, m):
        self.log_queue.put(m)

    def _bg(self, fn, *a):
        threading.Thread(target=fn, args=a, daemon=True).start()

    # ---------- team ----------
    def _set_team(self, team_dir, mode):
        self.team_e.delete(0, "end")
        if team_dir:
            self.team_e.insert(0, team_dir)
        self.mode_v.set(mode if mode in ("folder", "git") else "folder")

    def _team(self):
        return self.team_e.get().strip() or DEFAULT_TEAM_DIR

    def _on_pick_team(self):
        d = filedialog.askdirectory(initialdir=self._team())
        if d:
            self.team_e.delete(0, "end")
            self.team_e.insert(0, d)

    def _on_scaffold(self):
        try:
            t = scaffold_team(self._team(), self.mode_v.get())
            self.log("🏗 Dựng team ở %s (mode=%s): agents/ + team/roster.json + team/bus/" % (t, self.mode_v.get()))
            self._save()
        except Exception as e:
            self.log("❌ Dựng team lỗi: %s" % e)

    # ---------- bot list ----------
    def _refresh_bot_list(self):
        for w in self.botlist.winfo_children():
            w.destroy()
        for i, bot in enumerate(self.bots):
            live = "🟢" if listener_status(bot.get("name", "")) else "⚪"
            sel = (i == self.cur)
            btn = ctk.CTkButton(
                self.botlist, text="%s %s · %s" % (live, bot.get("name") or "?", bot.get("platform", "?")),
                anchor="w", command=lambda k=i: self._select_bot(k), height=34, corner_radius=8,
                fg_color=THEME["accent"] if sel else "transparent",
                hover_color=THEME["accent_hover"] if sel else THEME["surface2"],
                text_color="#FFFFFF" if sel else THEME["text"], font=F(12, "bold" if sel else "normal"))
            btn.grid(row=i, column=0, pady=2, sticky="ew")

    def _select_bot(self, i):
        self._commit_bot()
        self.cur = max(0, min(i, len(self.bots) - 1))
        self._load_bot(self.cur)
        self._refresh_bot_list()

    def _on_add_bot(self):
        self._commit_bot()
        self.bots.append(_blank_bot(len(self.bots) + 1))
        self.cur = len(self.bots) - 1
        self._load_bot(self.cur)
        self._refresh_bot_list()

    def _on_del_bot(self):
        if len(self.bots) <= 1:
            self.log("⚠ Phải còn ít nhất 1 bot.")
            return
        del self.bots[self.cur]
        self.cur = max(0, self.cur - 1)
        self._load_bot(self.cur)
        self._refresh_bot_list()
        self._save()

    @staticmethod
    def _fill(e, v):
        if e.get():
            e.delete(0, "end")
        if v:
            e.insert(0, v)

    def _commit_bot(self):
        if 0 <= self.cur < len(self.bots):
            self.bots[self.cur] = {
                "name": self.name_e.get().strip(), "platform": self.plat_v.get(),
                "token": self.token_e.get().strip(), "chat_id": self.chat_e.get().strip(),
                "role": "PM" if self.pm_v.get() else "DEV",
                "persona": self.pbox.get("1.0", "end").strip()}

    def _load_bot(self, i):
        b = self.bots[i]
        self._fill(self.name_e, b.get("name", ""))
        self.plat_v.set(b.get("platform", "Claude"))
        self._fill(self.token_e, b.get("token", ""))
        self._fill(self.chat_e, b.get("chat_id", ""))
        self.pm_v.set(b.get("role", "PM") == "PM")
        self.pbox.delete("1.0", "end")
        if b.get("persona"):
            self.pbox.insert("1.0", b["persona"])

    def _save(self):
        self._commit_bot()
        save_setup({"team_dir": self._team(), "mode": self.mode_v.get(), "bots": self.bots})

    # ---------- preset ----------
    def _on_load_preset(self):
        c = self.catalog.get(self.preset_v.get())
        if not c:
            return
        self._fill(self.name_e, c["name"])
        self.pm_v.set(c["role"] == "PM")
        self.pbox.delete("1.0", "end")
        self.pbox.insert("1.0", c["persona"])
        self.log("📦 Nạp preset \"%s\" — sửa rồi 💾 Ghi kit." % self.preset_v.get())

    # ---------- network ----------
    def _on_get_chatid(self):
        token = self.token_e.get().strip()
        if not token or ":" not in token:
            self.log("❌ Nhập Bot Token trước.")
            return
        self.log("🔎 Đang dò Chat ID… (nhắn 1 câu vào group + bot là admin).")

        def work():
            try:
                cid, title = detect_chat_id(token)
                if cid:
                    self.after(0, lambda: self._fill(self.chat_e, cid))
                    self.log("✅ Chat ID = %s%s" % (cid, (" (%s)" % title if title else "")))
                else:
                    self.log("⚠ Chưa thấy tin — nhắn vào group rồi bấm lại.")
            except Exception as e:
                self.log("❌ %s" % e)
        self._bg(work)

    def _on_test_send(self):
        token, chat = self.token_e.get().strip(), self.chat_e.get().strip()
        if not token or not chat:
            self.log("❌ Cần Token + Chat ID.")
            return
        self.log("✈️ Gửi test…")

        def work():
            try:
                r = tg_send_message(token, chat, "✅ Test — bot nói được vào group rồi.")
                self.log("✅ Gửi OK." if r.get("ok") else "⚠ %s" % r)
            except Exception as e:
                self.log("❌ %s" % e)
        self._bg(work)

    # ---------- write / generate ----------
    def _validate(self, b):
        if not b["name"]:
            return "thiếu Tên bot"
        if not b["token"] or ":" not in b["token"]:
            return "Token trống/sai"
        if not b["chat_id"]:
            return "thiếu Chat ID"
        names = [x["name"] for x in self.bots]
        if names.count(b["name"]) > 1:
            return "Tên bot bị TRÙNG (%s) — phải duy nhất để không đè config" % b["name"]
        return None

    def _on_write_kit(self):
        self._commit_bot()
        b = self.bots[self.cur]
        err = self._validate(b)
        if err:
            self.log("❌ " + err)
            return
        self._save()
        try:
            adir = write_bot_kit(self._team(), self.mode_v.get(), b)
            self.log("💾 Ghi kit \"%s\" -> %s (config/lock/offset riêng, không đè bot khác)" % (b["name"], adir))
        except Exception as e:
            self.log("❌ Ghi kit lỗi: %s" % e)

    def _on_gen_prompt(self):
        self._commit_bot()
        b = self.bots[self.cur]
        if not b["name"]:
            self.log("❌ Đặt Tên bot trước.")
            return
        self._save()
        pm = sum(1 for x in self.bots if x.get("role") == "PM")
        if pm > 1:
            self.log("ℹ Đang có %d bot PM — với nhiều bot thường chỉ nên 1 con điều phối (PM trả tin không tag); "
                     "còn lại để DEV, gọi bằng @tên." % pm)
        text = activation_prompt_v2(b, self._team(), self.mode_v.get())
        self.out.delete("1.0", "end")
        self.out.insert("1.0", text)
        try:
            self.clipboard_clear(); self.clipboard_append(text); self.update()
            self.log("📋 Đã tạo + COPY prompt 2-kênh cho \"%s\" — dán vào agent (%s) của bạn ấy." % (b["name"], b.get("platform")))
        except Exception:
            self.log("📋 Đã tạo prompt (copy tay từ ô trên).")

    # ---------- status ----------
    def _set_pill(self, pill, text, state):
        col = {"ok": THEME["success"], "bad": THEME["danger"], "idle": THEME["surface2"]}[state]
        fg = "#0F1117" if state == "ok" else ("#FFFFFF" if state == "bad" else THEME["muted"])
        pill.configure(text=text, fg_color=col, text_color=fg)

    def _on_check(self):
        self._commit_bot()
        b = self.bots[self.cur]
        # bộ não (lock của bot đang chọn)
        self._set_pill(self.brain_pill, "Bộ não: 🟢 %s" % b["name"] if listener_status(b["name"]) else "Bộ não: ⚪ %s" % (b["name"] or "?"),
                       "ok" if listener_status(b["name"]) else "idle")
        # roster (đọc file team)
        try:
            r = json.loads((Path(self._team()) / "team" / "roster.json").read_text())
            online = sum(1 for v in r.values() if v.get("status") == "online")
            self._set_pill(self.roster_pill, "Roster: %d bot (%d online)" % (len(r), online), "ok" if r else "idle")
        except Exception:
            self._set_pill(self.roster_pill, "Roster: — (chưa dựng team)", "idle")
        self._refresh_bot_list()
        # telegram (getMe bot đang chọn)
        token = b["token"]
        if not token or ":" not in token:
            self._set_pill(self.tg_pill, "Telegram: ⚪ chưa có token", "idle")
            return
        self._set_pill(self.tg_pill, "Telegram: ⏳…", "idle")

        def work():
            try:
                me = tg_get_me(token)
                if me.get("ok"):
                    u = (me.get("result") or {}).get("username") or "?"
                    self.after(0, lambda: self._set_pill(self.tg_pill, "Telegram: 🟢 @%s" % u, "ok"))
                else:
                    self.after(0, lambda: self._set_pill(self.tg_pill, "Telegram: 🔴 token sai", "bad"))
            except Exception:
                self.after(0, lambda: self._set_pill(self.tg_pill, "Telegram: 🔴 lỗi mạng", "bad"))
        self._bg(work)


if __name__ == "__main__":
    WizardApp().mainloop()
