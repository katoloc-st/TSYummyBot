# 🚀 Hướng dẫn Deploy Bot lên Server Miễn Phí

## 🎯 Tổng quan

Có nhiều platforms free để deploy Telegram bot. Đây là so sánh:

| Platform | Free Tier | Always-on | Cần CC | Khó |
|----------|-----------|-----------|--------|-----|
| **Render.com** | ✅ 750h/tháng | ✅ | ❌ | ⭐⭐ |
| Railway.app | ✅ $5 credit | ✅ | ✅ | ⭐⭐ |
| Fly.io | ✅ Limited | ✅ | ✅ | ⭐⭐⭐ |
| PythonAnywhere | ✅ Limited | ❌ Sleep | ❌ | ⭐⭐⭐ |

**Recommended: Render.com** - Không cần credit card, setup dễ nhất!

---

## 📋 Chuẩn bị trước khi deploy

### 1. Tạo GitHub Repository

```bash
# Khởi tạo git (nếu chưa có)
git init

# Add tất cả files
git add .

# Commit
git commit -m "Initial commit - Telegram bot ready for deployment"

# Tạo repo trên GitHub
# Vào https://github.com/new
# Tạo repo mới (ví dụ: telegram-bot-trasua)

# Push lên GitHub
git remote add origin https://github.com/YOUR_USERNAME/telegram-bot-trasua.git
git branch -M main
git push -u origin main
```

### 2. Lấy Bot Token từ BotFather

1. Mở Telegram → Tìm **@BotFather**
2. Gửi `/newbot` hoặc `/mybots` nếu đã có bot
3. Copy **Bot Token** (ví dụ: `1234567890:ABCdefGHIjklMN...`)
4. **LƯU Ý**: Bot token này dùng để config trên Render

### 3. Lấy Admin ID

```bash
# Chạy bot local tạm
python bot.py

# Gửi /myid cho bot trong Telegram
# Copy user_id (ví dụ: 123456789)
```

---

## 🟢 Option 1: Deploy lên Render.com (RECOMMENDED)

### Step 1: Tạo tài khoản Render

1. Vào https://render.com
2. Click **Sign Up** → Đăng ký bằng GitHub
3. Authorize Render truy cập GitHub repos của bạn

### Step 2: Tạo Web Service

1. Vào Dashboard → Click **New +** → Chọn **Web Service**
2. Connect repository:
   - Chọn repo `telegram-bot-trasua` (hoặc tên repo bạn đặt)
   - Click **Connect**

### Step 3: Configure Service

**Basic Settings:**
- **Name**: `telegram-bot-trasua` (hoặc tên bạn thích)
- **Region**: `Singapore` (gần VN nhất) hoặc `Oregon`
- **Branch**: `main`
- **Root Directory**: để trống
- **Runtime**: `Python 3`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `python bot.py`

**Instance Type:**
- Chọn **Free** (0$/month)

### Step 4: Add Environment Variables

Scroll xuống phần **Environment Variables**, thêm:

| Key | Value |
|-----|-------|
| `BOT_TOKEN` | `1234567890:ABC...` (token từ BotFather) |
| `ADMIN_IDS` | `123456789` (user ID của bạn) |
| `PYTHON_VERSION` | `3.11.0` |

**Lưu ý**: Click **Add** sau mỗi biến!

### Step 5: Deploy

1. Click **Create Web Service**
2. Đợi 2-5 phút để build & deploy
3. Xem logs để kiểm tra:
   ```
   ✅ Bot running (polling)... Press Ctrl+C to stop.
   ```

### Step 6: Test Bot

1. Mở Telegram → Tìm bot của bạn
2. Gửi `/start`
3. Thử đặt hàng
4. Kiểm tra admin notifications

### ✅ DONE! Bot đã chạy 24/7 trên cloud!

**URL logs**: `https://dashboard.render.com/web/YOUR_SERVICE_NAME/logs`

---

## 🔵 Option 2: Deploy lên Railway.app

### Step 1: Tạo tài khoản

1. Vào https://railway.app
2. Click **Start a New Project**
3. Login bằng GitHub

### Step 2: Deploy from GitHub

1. Click **New Project**
2. Chọn **Deploy from GitHub repo**
3. Chọn repo `telegram-bot-trasua`
4. Railway tự động detect Python project

### Step 3: Add Environment Variables

1. Click vào service vừa tạo
2. Vào tab **Variables**
3. Thêm:
   - `BOT_TOKEN`: token từ BotFather
   - `ADMIN_IDS`: user ID của bạn

### Step 4: Deploy

Railway tự động deploy. Xem logs trong tab **Deployments**.

**Lưu ý**: Railway cho $5 credit/tháng free, hết credit bot sẽ dừng.

---

## 🟣 Option 3: Deploy lên Fly.io

### Step 1: Install Fly CLI

```bash
# Windows (PowerShell)
iwr https://fly.io/install.ps1 -useb | iex

# Verify
fly version
```

### Step 2: Login & Init

```bash
# Login
fly auth login

# Initialize app
fly launch

# Chọn:
# - App name: telegram-bot-trasua
# - Region: Singapore
# - Database: No
```

### Step 3: Set Secrets

```bash
fly secrets set BOT_TOKEN="1234567890:ABC..."
fly secrets set ADMIN_IDS="123456789"
```

### Step 4: Deploy

```bash
fly deploy
```

### Step 5: Check logs

```bash
fly logs
```

---

## 📊 So sánh các options

### Render.com ⭐⭐⭐⭐⭐
**Ưu điểm:**
- ✅ Không cần credit card
- ✅ 750h free/tháng (đủ chạy 24/7)
- ✅ Auto-restart khi crash
- ✅ UI đẹp, logs tốt
- ✅ Deploy từ GitHub tự động

**Nhược điểm:**
- ⚠️ Có thể bị sleep sau 15 phút inactive (nhưng bot polling thì OK)

### Railway.app ⭐⭐⭐⭐
**Ưu điểm:**
- ✅ $5 credit free/tháng
- ✅ Không bị sleep
- ✅ Deploy cực nhanh

**Nhược điểm:**
- ⚠️ Cần credit card để verify (dù không charge)
- ⚠️ Hết credit thì dừng

### Fly.io ⭐⭐⭐
**Ưu điểm:**
- ✅ Free tier ổn định
- ✅ Nhiều region

**Nhược điểm:**
- ⚠️ Cần credit card
- ⚠️ CLI phức tạp hơn
- ⚠️ Config dài dòng

---

## 🔧 Troubleshooting

### Bot không start sau khi deploy

**Check logs** trên platform:
- Render: Dashboard → Service → Logs
- Railway: Project → Deployments → Logs
- Fly: `fly logs`

**Common issues:**

1. **Thiếu BOT_TOKEN**
   ```
   RuntimeError: Thiếu BOT_TOKEN trong .env
   ```
   → Kiểm tra Environment Variables đã set đúng chưa

2. **Invalid token**
   ```
   Unauthorized: Invalid token
   ```
   → Token sai hoặc bot bị delete. Tạo bot mới từ @BotFather

3. **Module not found**
   ```
   ModuleNotFoundError: No module named 'aiogram'
   ```
   → Kiểm tra `requirements.txt` có đầy đủ dependencies

### Bot chạy nhưng không response

1. **Check bot status**: Gửi message cho bot
2. **Check logs**: Xem có nhận được updates không
3. **Restart service**: Render → Settings → Manual Deploy

### Database bị mất sau deploy

⚠️ **Lưu ý**: SQLite file (`orders.db`) sẽ bị mất mỗi lần redeploy trên Render/Railway.

**Giải pháp:**

**Option A**: Dùng PostgreSQL (recommended cho production)
```bash
# Thêm vào requirements.txt
asyncpg
```

**Option B**: Backup database định kỳ
```python
# Thêm vào bot.py
async def backup_db():
    # Upload database lên cloud storage
    pass
```

**Option C**: Chấp nhận (OK cho test/demo)

---

## 📝 Checklist trước khi submit cho ban giám khảo

- [ ] Bot đang chạy 24/7 trên server
- [ ] Test đầy đủ flow: start → chọn món → thanh toán → nhận đơn
- [ ] Test admin notifications
- [ ] Logs không có error
- [ ] README.md có link bot và hướng dẫn sử dụng
- [ ] GitHub repo public và clean
- [ ] .env không bị commit (check .gitignore)
- [ ] Video demo hoặc screenshots (optional nhưng plus point)

---

## 🎯 Gửi cho ban giám khảo

### 1. Update README.md

Thêm vào đầu README.md:

```markdown
## 🤖 Live Demo

**Bot đang chạy tại**: [@your_bot_username](https://t.me/your_bot_username)

**Để test:**
1. Mở link trên
2. Gửi `/start`
3. Bắt đầu đặt hàng

**Admin demo**: Liên hệ @your_telegram để được thêm vào admin group
```

### 2. Gửi thông tin

Email/form cho ban giám khảo:
```
✅ GitHub Repository: https://github.com/username/telegram-bot-trasua
✅ Live Bot: @your_bot_username
✅ Tech Stack: Python, aiogram 3.x, SQLite, Render.com
✅ Status: Running 24/7
```

### 3. Test trước khi gửi

```bash
# Test toàn bộ flow
1. /start → Chọn món → Thêm topping → Đặt hàng
2. Test edit cart
3. Test payment options
4. Test admin notifications
5. Test status update
```

---

## 💡 Tips để ghi điểm

1. **Uptime monitoring**: Thêm healthcheck
2. **Error notifications**: Bot gửi error về admin
3. **Analytics**: Track số đơn, revenue
4. **Video demo**: Record màn hình demo bot
5. **Documentation**: README chi tiết như hiện tại

---

## 🆘 Cần hỗ trợ?

Nếu gặp vấn đề khi deploy:
1. Check logs trên platform
2. Google error message
3. Check Render/Railway community forums
4. Ask ChatGPT với error log đầy đủ

---

**Good luck với entry test! 🚀**

Made with ❤️ for Casso Entry Test - March 2026
