# 🧋 Telegram Bot - Hệ thống đặt trà sữa

Bot Telegram chuyên nghiệp cho đặt hàng trà sữa với đầy đủ tính năng quản lý đơn hàng, thanh toán, và thông báo real-time.

## 🤖 Live Demo (Dành cho ban giám khảo)

**Bot Status**: 🟢 Running 24/7 on Render.com  
**Bot Link**: `@your_bot_username` _(Update sau khi deploy)_

**Quick Test:**
1. Mở Telegram → Tìm bot
2. Gửi `/start`
3. Test flow: Chọn món → Customize → Đặt hàng

📖 **[Xem hướng dẫn deploy chi tiết](DEPLOYMENT.md)**

## ✨ Tính năng

### Cho khách hàng:
- 📋 **Menu đa dạng**: Trà sữa, Trà trái cây, Cà phê, Đá xay với nhiều topping
- 🛒 **Giỏ hàng thông minh**: Tự động gộp món giống nhau, dễ dàng chỉnh sửa
- 🎛️ **Tuỳ chỉnh**: Chọn size (M/L), % đường (0-100%), % đá (0-100%)
- 🍓 **Topping phong phú**: Trân châu, thạch, kem tươi, nước cốt dừa,...
- 💳 **Thanh toán linh hoạt**: Thanh toán trước hoặc COD
- 📝 **Ghi chú đơn hàng**: Thêm yêu cầu đặc biệt
- 🔔 **Thông báo real-time**: Cập nhật trạng thái đơn hàng tự động

### Cho admin/chủ quán:
- 📊 **Nhận đơn tự động**: Thông báo ngay khi có đơn mới
- ⚡ **Quản lý trạng thái**: Đã nhận → Đang làm → Hoàn thành
- 💰 **Theo dõi thanh toán**: Phân biệt đơn đã thanh toán và COD
- 🗄️ **Lưu trữ database**: SQLite lưu toàn bộ lịch sử đơn hàng

## 🚀 Cài đặt

### Yêu cầu:
- Python 3.8+
- Telegram Bot Token (từ [@BotFather](https://t.me/BotFather))

### Bước 1: Clone repository
```bash
git clone <repository-url>
cd TELEBOT
```

### Bước 2: Cài đặt dependencies
```bash
pip install -r requirements.txt
```

### Bước 3: Cấu hình environment
Tạo file `.env` trong thư mục gốc:
```env
BOT_TOKEN=your_telegram_bot_token_here
ADMIN_IDS=123456789,987654321
```

**Lấy Bot Token:**
1. Mở Telegram, tìm [@BotFather](https://t.me/BotFather)
2. Gửi `/newbot` và làm theo hướng dẫn
3. Copy token và paste vào `.env`

**Lấy Admin ID:**
1. Chạy bot (xem bước 4)
2. Gửi `/myid` cho bot trong Telegram
3. Copy user_id và thêm vào `ADMIN_IDS` trong `.env`

### Bước 4: Chạy bot
```bash
python bot.py
```

Khi thấy `✅ Bot running (polling)... Press Ctrl+C to stop.` là thành công!

### Bước 5: Setup admin notifications
1. Tạo group chat hoặc dùng chat cá nhân
2. Thêm bot vào group (hoặc gửi tin nhắn cho bot)
3. Gửi lệnh `/set_mom` trong chat đó
4. Bot sẽ gửi tất cả đơn hàng mới vào chat này

## 📖 Hướng dẫn sử dụng

### Khách hàng:
1. **Bắt đầu**: Gửi `/start` cho bot
2. **Chọn danh mục**: Chọn loại đồ uống (Trà Sữa, Cà Phê,...)
3. **Chọn món**: Chọn món từ menu
4. **Tuỳ chỉnh**: Chọn size, đường, đá, topping
5. **Nhập số lượng**: Gõ số lượng muốn đặt
6. **Quản lý giỏ hàng**:
   - ➕ Thêm món: Đặt thêm món khác
   - ✏️ Sửa giỏ: Tăng/giảm/xoá món
   - ✅ Thanh toán: Chuyển sang bước thanh toán
7. **Chọn thanh toán**: Thanh toán trước hoặc COD
8. **Nhập ghi chú**: Thêm yêu cầu (hoặc gõ `-` để bỏ qua)
9. **Xác nhận**: Bấm "✅ Xác nhận đặt hàng"
10. **Nhận mã đơn**: Lưu mã đơn để tra cứu

### Admin:
1. **Nhận thông báo**: Bot tự động gửi đơn mới
2. **Cập nhật trạng thái**: Bấm nút trên đơn:
   - ✅ Đã nhận
   - 🧋 Đang làm
   - 🟢 Xong
3. **Khách tự động nhận thông báo** khi trạng thái thay đổi

## 📁 Cấu trúc dự án

```
TELEBOT/
├── bot.py              # File chính chứa toàn bộ logic bot
├── Menu.csv            # Dữ liệu menu (danh mục, món, giá)
├── requirements.txt    # Python dependencies
├── .env                # Environment variables (không commit)
├── .env.example        # Template cho .env
├── .gitignore          # Git ignore rules
├── bot.log             # Log file (tự động tạo)
├── orders.db           # SQLite database (tự động tạo)
└── README.md           # Tài liệu này
```

## 🔧 Cấu hình Menu

Chỉnh sửa `Menu.csv` để thêm/sửa món:

```csv
category,item_id,name,description,price_m,price_l,available
Trà Sữa,TS01,Trà Sữa Trân Châu Đen,Trà sữa thơm béo với trân châu đen,35000,45000,true
Topping,TOP01,Trân Châu Đen,Trân châu đen dai ngon,5000,5000,true
```

**Lưu ý:**
- `available` = `true` để hiển thị, `false` để ẩn
- Topping phải có category chứa từ "topping"
- Giá topping lấy từ cột `price_m`

## 🗄️ Database Schema

### Table: `orders`
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| order_code | TEXT | Mã đơn (TS-20260301-001) |
| customer_id | INTEGER | Telegram user ID |
| customer_chat_id | INTEGER | Chat ID để gửi thông báo |
| customer_username | TEXT | Telegram username |
| note | TEXT | Ghi chú khách hàng |
| total | INTEGER | Tổng tiền (VNĐ) |
| status | TEXT | received/making/done |
| payment_method | TEXT | pay_now/pay_later |
| payment_status | TEXT | pending/paid/cod |
| created_at | TEXT | Thời gian tạo |

### Table: `order_items`
Chi tiết từng món trong đơn hàng

### Table: `settings`
Lưu cấu hình (mom_chat_id, order sequence,...)

## 📝 Logging

Bot ghi log vào 2 nơi:
- **Console**: Hiển thị real-time khi chạy
- **bot.log**: File log đầy đủ để debug

Format log:
```
2026-03-01 10:30:45 - __main__ - INFO - User 123456789 (@username) started bot
2026-03-01 10:31:20 - __main__ - INFO - Creating order TS-20260301-001 for user 123456789
```

## 🛡️ Error Handling

- ✅ Global error handler bắt tất cả exceptions
- ✅ Validate user input (số lượng, state transitions)
- ✅ Graceful shutdown với Ctrl+C
- ✅ Log chi tiết mọi lỗi vào `bot.log`

## 🔒 Bảo mật

- ⚠️ **Không commit file `.env`** (đã có trong `.gitignore`)
- ⚠️ Chỉ admin được dùng `/set_mom` và thay đổi trạng thái đơn
- ✅ Validate admin qua `ADMIN_IDS` trong `.env`

## 📊 Tech Stack

- **Framework**: [aiogram 3.x](https://aiogram.dev/) - Modern Telegram Bot framework
- **Database**: [aiosqlite](https://github.com/omnilib/aiosqlite) - Async SQLite
- **State Management**: FSM (Finite State Machine) với aiogram
- **Async**: Full asyncio support

## 🐛 Troubleshooting

### Bot không response:
1. Kiểm tra `BOT_TOKEN` trong `.env` đúng chưa
2. Xem log trong `bot.log` hoặc console
3. Đảm bảo bot đang chạy (`python bot.py`)

### Không nhận được thông báo admin:
1. Chạy `/set_mom` trong chat muốn nhận thông báo
2. Kiểm tra `ADMIN_IDS` trong `.env` có user ID của bạn
3. Xem log: `grep "admin" bot.log`

### Lỗi database:
1. Xoá file `orders.db` (mất data!)
2. Chạy lại bot để tạo database mới

### Menu không hiển thị:
1. Kiểm tra `Menu.csv` format đúng
2. Đảm bảo `available=true`
3. Xem log khi bot khởi động

## 📞 Liên hệ & Hỗ trợ

- **GitHub Issues**: [Link to issues]
- **Telegram**: @your_telegram_username

## 📄 License

MIT License - Free to use and modify

---

Made with ❤️ for Casso Entry Test - March 2026
