# 🚀 Quick Deploy Guide

## Nhanh nhất: Render.com (5 phút)

### 1. Push code lên GitHub
```bash
git init
git add .
git commit -m "Ready for deployment"
git remote add origin https://github.com/USERNAME/REPO.git
git push -u origin main
```

### 2. Deploy trên Render
1. Vào https://render.com → Sign up bằng GitHub
2. New → Web Service → Connect repo
3. Settings:
   - **Build**: `pip install -r requirements.txt`
   - **Start**: `python bot.py`
   - **Instance**: Free
4. Environment Variables:
   - `BOT_TOKEN` = (từ @BotFather)
   - `ADMIN_IDS` = (user ID từ /myid)
5. Create Web Service → Đợi 3-5 phút

### 3. Test
- Mở bot trong Telegram
- Gửi `/start`
- ✅ DONE!

## Chi tiết đầy đủ
Xem file [DEPLOYMENT.md](DEPLOYMENT.md)

## Platforms khác
- Railway.app: Giống Render, cần credit card
- Fly.io: Dùng CLI, phức tạp hơn
- PythonAnywhere: Bị sleep, không recommended

## Troubleshooting
**Bot không chạy?**
→ Check logs trên Render Dashboard
→ Verify BOT_TOKEN đúng chưa

**Bot không response?**
→ Check bot chưa bị revoke token
→ Restart service trên Render
