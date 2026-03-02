import asyncio
import csv
import logging
import os
import re
import html
import sys
import signal
import platform
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional

import aiosqlite
from dotenv import load_dotenv
from aiohttp import web, ClientSession, ClientTimeout

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, ErrorEvent
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

# ---------- Logging Setup ----------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


# ---------- Config ----------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = set(
    int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.strip().isdigit()
)

DB_PATH = "orders.db"
MENU_PATH = "Menu.csv"

PM = "Markdown"


def vnd(n: int) -> str:
    """Format number to Vietnamese dong currency (e.g., 35.000đ)."""
    return f"{n:,}".replace(",", ".") + "đ"


# ---------- Load menu ----------
def load_menu(menu_csv_path: str):
    """
    Load menu từ CSV file.
    
    Args:
        menu_csv_path: Đường dẫn đến file Menu.csv
        
    Returns:
        Tuple[Dict, Dict]: (categories, items) dictionary
        
    Expect columns:
        category,item_id,name,description,price_m,price_l,available
    """
    logger.info(f"Loading menu from {menu_csv_path}...")
    if not os.path.exists(menu_csv_path):
        logger.error(f"Menu file not found: {menu_csv_path}")
        raise FileNotFoundError(f"Không tìm thấy {menu_csv_path} trong thư mục hiện tại.")

    categories: Dict[str, List[str]] = {}
    items: Dict[str, Dict[str, Any]] = {}

    def parse_price(x: str) -> int:
        x = (x or "").strip()
        if not x:
            return 0
        digits = re.sub(r"[^\d]", "", x)  # handles: 5.000đ / 5,000 / 5000
        return int(digits) if digits else 0

    with open(menu_csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            avail = str(row.get("available", "")).strip().lower()
            if avail not in ("1", "true", "yes", "y", "t"):
                continue

            cat = (row.get("category") or "Khác").strip()
            item_id = (row.get("item_id") or "").strip()
            name = (row.get("name") or "").strip()
            if not item_id or not name:
                continue

            desc = (row.get("description") or "").strip()
            price_m = parse_price(row.get("price_m", "0"))
            price_l = parse_price(row.get("price_l", "0")) or price_m

            items[item_id] = {
                "item_id": item_id,
                "name": name,
                "desc": desc,
                "price_m": price_m,
                "price_l": price_l,
                "category": cat,
            }
            categories.setdefault(cat, []).append(item_id)

    logger.info(f"Menu loaded: {len(categories)} categories, {len(items)} items")
    return categories, items


CATEGORIES_RAW, ITEMS = load_menu(MENU_PATH)


def is_topping_category(cat_name: str) -> bool:
    """Check if category name contains 'topping'."""
    return "topping" in (cat_name or "").strip().lower()


# ----- Build topping catalog from Menu.csv -----
TOPPING_CATS = [cat for cat in CATEGORIES_RAW.keys() if is_topping_category(cat)]

TOPPING_ITEM_IDS: List[str] = []
for cat in TOPPING_CATS:
    TOPPING_ITEM_IDS.extend(CATEGORIES_RAW.get(cat, []))

# Deduplicate but keep order
_seen = set()
TOPPING_ITEM_IDS = [x for x in TOPPING_ITEM_IDS if not (x in _seen or _seen.add(x))]

TOPPING_ITEMS: Dict[str, Dict[str, Any]] = {}
for tid in TOPPING_ITEM_IDS:
    it = ITEMS.get(tid)
    if not it:
        continue
    TOPPING_ITEMS[tid] = {
        "item_id": tid,
        "name": it["name"],
        "price": int(it.get("price_m", 0)),  # topping price from price_m
    }

# MAIN categories exclude topping categories 
CATEGORIES = {cat: ids for cat, ids in CATEGORIES_RAW.items() if cat not in TOPPING_CATS}


# ---------- DB ----------
async def _ensure_column(db: aiosqlite.Connection, table: str, column: str, col_type: str):
    """Ensure database column exists, add if missing."""
    cur = await db.execute(f"PRAGMA table_info({table})")
    rows = await cur.fetchall()
    cols = {r[1] for r in rows}
    if column not in cols:
        logger.info(f"Adding column {column} to table {table}")
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


async def init_db():
    """Initialize database tables and migrations."""
    logger.info(f"Initializing database: {DB_PATH}")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_code TEXT UNIQUE,
            customer_id INTEGER,
            customer_username TEXT,
            note TEXT,
            total INTEGER,
            created_at TEXT
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_code TEXT,
            item_id TEXT,
            item_name TEXT,
            size TEXT,
            sugar TEXT,
            ice TEXT,
            toppings TEXT,
            qty INTEGER,
            unit_price INTEGER,
            line_total INTEGER
        )
        """)

        # migrations
        await _ensure_column(db, "orders", "customer_chat_id", "INTEGER")
        await _ensure_column(db, "orders", "status", "TEXT")  # received/making/done

        # payment columns
        await _ensure_column(db, "orders", "payment_method", "TEXT")   # pay_now / pay_later
        await _ensure_column(db, "orders", "payment_status", "TEXT")   # pending / paid / cod

        await db.commit()
    logger.info("Database initialized successfully")


async def get_setting(key: str) -> Optional[str]:
    """Get setting value from database by key."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else None


async def set_setting(key: str, value: str):
    """Set or update setting value in database."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        await db.commit()


async def next_order_code() -> str:
    """Generate unique order code with format: TS-YYYYMMDD-XXX."""
    d = datetime.now().strftime("%Y%m%d")
    key = f"seq_{d}"
    current = await get_setting(key)
    seq = int(current) + 1 if (current and current.isdigit()) else 1
    await set_setting(key, str(seq))
    return f"TS-{d}-{seq:03d}"


async def save_order(
    order_code: str,
    customer_id: int,
    customer_chat_id: int,
    customer_username: str,
    note: str,
    total: int,
    cart: List[Dict[str, Any]],
    payment_method: str,
    payment_status: str,
    status: str = "received",
):
    """Save order to database."""
    logger.info(f"Saving order {order_code} for user {customer_id} (@{customer_username})")
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO orders(
                order_code,customer_id,customer_chat_id,customer_username,note,total,created_at,status,
                payment_method,payment_status
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                order_code,
                customer_id,
                customer_chat_id,
                customer_username,
                note,
                total,
                created_at,
                status,
                payment_method,
                payment_status,
            ),
        )
        for line in cart:
            await db.execute(
                """INSERT INTO order_items(
                    order_code,item_id,item_name,size,sugar,ice,toppings,qty,unit_price,line_total
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    order_code,
                    line["item_id"],
                    line["item_name"],
                    line["size"],
                    line["sugar"],
                    line["ice"],
                    ",".join(line["toppings_names"]),
                    line["qty"],
                    line["unit_price"],
                    line["line_total"],
                ),
            )
        await db.commit()
    logger.info(f"Order {order_code} saved successfully (Total: {total}đ)")


async def set_order_status(order_code: str, status: str):
    """Update order status in database."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE orders SET status=? WHERE order_code=?", (status, order_code))
        await db.commit()


async def get_order_customer_chat(order_code: str) -> Optional[int]:
    """Get customer chat_id for an order to send notifications."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT customer_chat_id FROM orders WHERE order_code=?", (order_code,))
        row = await cur.fetchone()
        if not row or row[0] is None:
            return None
        return int(row[0])


# ---------- FSM ----------
class OrderFSM(StatesGroup):
    choose_category = State()
    choose_item = State()
    choose_size = State()
    choose_sugar = State()
    choose_ice = State()
    choose_toppings = State()
    enter_qty = State()

    choose_payment = State()  # NEW

    enter_note = State()
    confirm = State()


# ---------- Keyboards ----------
def kb_categories():
    """Build inline keyboard for category selection."""
    b = InlineKeyboardBuilder()
    for cat in CATEGORIES.keys():
        b.button(text=cat, callback_data=f"cat:{cat}")
    b.adjust(2)
    return b.as_markup()


def kb_items(cat: str):
    b = InlineKeyboardBuilder()
    for item_id in CATEGORIES.get(cat, []):
        it = ITEMS[item_id]
        b.button(text=f"{it['name']} (M {vnd(it['price_m'])})", callback_data=f"item:{item_id}")
    b.button(text="⬅️ Quay lại", callback_data="back:categories")
    b.adjust(1)
    return b.as_markup()


def kb_sizes(item_id: str):
    it = ITEMS[item_id]
    b = InlineKeyboardBuilder()
    b.button(text=f"Size M - {vnd(it['price_m'])}", callback_data="size:M")
    b.button(text=f"Size L - {vnd(it['price_l'])}", callback_data="size:L")
    b.button(text="⬅️ Quay lại", callback_data="back:items")
    b.adjust(1)
    return b.as_markup()


def kb_percent(prefix: str):
    b = InlineKeyboardBuilder()
    for p in ["0%", "30%", "50%", "70%", "100%"]:
        b.button(text=p, callback_data=f"{prefix}:{p}")
    b.button(text="⬅️ Quay lại", callback_data="back:prev")
    b.adjust(3, 2, 1)
    return b.as_markup()


def kb_toppings(selected_ids: set[str]):
    b = InlineKeyboardBuilder()
    if not TOPPING_ITEM_IDS:
        b.button(text="Không có topping trong menu", callback_data="top:done")
        b.adjust(1)
        return b.as_markup()

    for tid in TOPPING_ITEM_IDS:
        t = TOPPING_ITEMS.get(tid)
        if not t:
            continue
        mark = "✅ " if tid in selected_ids else ""
        b.button(text=f"{mark}{t['name']} (+{vnd(int(t['price']))})", callback_data=f"top:{tid}")

    b.button(text="Xong topping", callback_data="top:done")
    b.button(text="⬅️ Quay lại", callback_data="back:prev")
    b.adjust(1)
    return b.as_markup()


def kb_cart():
    b = InlineKeyboardBuilder()
    b.button(text="➕ Thêm món", callback_data="cart:add")
    b.button(text="✅ Thanh toán", callback_data="cart:checkout")
    b.button(text="✏️ Sửa giỏ hàng", callback_data="cart:edit")
    b.button(text="❌ Huỷ đơn", callback_data="cart:cancel")
    b.adjust(3, 1)
    return b.as_markup()


def kb_payment_choice():
    b = InlineKeyboardBuilder()
    b.button(text="💳 Thanh toán trước", callback_data="pay:now")
    b.button(text="💵 Thanh toán sau", callback_data="pay:later")
    b.button(text="⬅️ Quay lại giỏ", callback_data="pay:back_cart")
    b.adjust(2, 1)
    return b.as_markup()


def kb_confirm():
    b = InlineKeyboardBuilder()
    b.button(text="✅ Xác nhận đặt hàng", callback_data="ok:confirm")
    b.button(text="⬅️ Sửa giỏ", callback_data="ok:back_to_cart")
    b.button(text="❌ Huỷ", callback_data="ok:cancel")
    b.adjust(1)
    return b.as_markup()


def kb_after_done():
    b = InlineKeyboardBuilder()
    b.button(text="🛒 Đặt thêm", callback_data="new:start")
    b.adjust(1)
    return b.as_markup()


def kb_mom_status(order_code: str):
    b = InlineKeyboardBuilder()
    b.button(text="✅ Đã nhận", callback_data=f"st:received:{order_code}")
    b.button(text="🧋 Đang làm", callback_data=f"st:making:{order_code}")
    b.button(text="🟢 Xong", callback_data=f"st:done:{order_code}")
    b.adjust(3)
    return b.as_markup()


def kb_edit_cart_list(cart: List[Dict[str, Any]]):
    b = InlineKeyboardBuilder()
    for i, x in enumerate(cart, 1):
        b.button(text=f"{i}) {x['item_name']} x{x['qty']}", callback_data=f"edit:item:{i}")
    b.button(text="⬅️ Quay lại giỏ", callback_data="edit:back_cart")
    b.adjust(1)
    return b.as_markup()


def kb_edit_cart_item(line_no: int):
    b = InlineKeyboardBuilder()
    b.button(text="➖ Giảm", callback_data=f"edit:dec:{line_no}")
    b.button(text="➕ Tăng", callback_data=f"edit:inc:{line_no}")
    b.button(text="🗑 Xoá món", callback_data=f"edit:del:{line_no}")
    b.button(text="⬅️ Quay lại danh sách", callback_data="edit:back_list")
    b.adjust(3, 1)
    return b.as_markup()


# ---------- Pricing ----------
def calc_line(item_id: str, size: str, toppings_ids: List[str], qty: int) -> Tuple[int, int]:
    """Calculate unit price and line total for cart item.
    
    Args:
        item_id: Menu item ID
        size: 'M' or 'L'
        toppings_ids: List of topping IDs
        qty: Quantity
        
    Returns:
        Tuple[int, int]: (unit_price, line_total)
    """
    it = ITEMS[item_id]
    base = it["price_m"] if size == "M" else it["price_l"]

    top_price = 0
    for tid in toppings_ids:
        t = TOPPING_ITEMS.get(tid)
        if t:
            top_price += int(t["price"])

    unit = int(base) + int(top_price)
    return unit, unit * qty


def render_cart(cart: List[Dict[str, Any]]) -> Tuple[str, int]:
    """Render cart display text with total price.
    
    Returns:
        Tuple[str, int]: (formatted_text, total_price)
    """
    if not cart:
        return "🛒 Giỏ hàng trống.", 0
    lines = ["🛒 *Giỏ hàng*:"]
    total = 0
    for i, x in enumerate(cart, 1):
        tops = ", ".join(x["toppings_names"]) if x["toppings_names"] else "Không"
        lines.append(
            f"{i}) *{x['item_name']}* x{x['qty']}\n"
            f"   Size: {x['size']} | Đường: {x['sugar']} | Đá: {x['ice']}\n"
            f"   Topping: {tops}\n"
            f"   {vnd(x['line_total'])}"
        )
        total += x["line_total"]
    lines.append(f"\n*Tổng*: {vnd(total)}")
    return "\n".join(lines), total


# ---------- Cart merge helpers ----------
def cart_key(item_id: str, size: str, sugar: str, ice: str, toppings_ids: List[str]) -> Tuple:
    """Generate unique key for cart item to detect duplicates."""
    return (item_id, size, sugar, ice, tuple(sorted(toppings_ids)))


def merge_or_append_cart(cart: List[Dict[str, Any]], new_item: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], bool, int]:
    """Merge new item with existing cart line if same config, or append new line.
    
    Returns:
        Tuple: (updated_cart, was_merged, line_number)
    """
    nk = cart_key(
        new_item["item_id"],
        new_item["size"],
        new_item["sugar"],
        new_item["ice"],
        new_item["toppings_ids"],
    )

    for idx, line in enumerate(cart):
        lk = cart_key(
            line["item_id"],
            line["size"],
            line["sugar"],
            line["ice"],
            line["toppings_ids"],
        )
        if lk == nk:
            line["qty"] += new_item["qty"]
            line["unit_price"] = new_item["unit_price"]
            line["line_total"] = line["unit_price"] * line["qty"]
            return cart, True, idx + 1

    cart.append(new_item)
    return cart, False, len(cart)


# ---------- Edit cart views ----------
def render_edit_list_text(cart: List[Dict[str, Any]]) -> str:
    cart_text, _ = render_cart(cart)
    return f"✏️ *Sửa giỏ hàng*\n\nChọn món cần sửa:\n\n{cart_text}"


def render_edit_item_text(cart: List[Dict[str, Any]], line_no: int) -> str:
    cart_text, _ = render_cart(cart)
    if line_no < 1 or line_no > len(cart):
        return f"✏️ *Sửa giỏ hàng*\n\n{cart_text}\n\n(Không tìm thấy món.)"
    x = cart[line_no - 1]
    tops = ", ".join(x["toppings_names"]) if x["toppings_names"] else "Không"
    return (
        f"✏️ *Sửa giỏ hàng*\n\n"
        f"{cart_text}\n\n"
        f"Đang sửa: *#{line_no} {x['item_name']}*\n"
        f"Size: {x['size']} | Đường: {x['sugar']} | Đá: {x['ice']}\n"
        f"Topping: {tops}\n"
        f"Số lượng: *{x['qty']}*\n"
        f"Đơn giá: *{vnd(x['unit_price'])}*\n"
        f"Thành tiền: *{vnd(x['line_total'])}*"
    )


def payment_labels(method: str, status: str) -> str:
    if method == "pay_now":
        if status == "paid":
            return "💳 Thanh toán trước (đã thanh toán)"
        return "💳 Thanh toán trước (chưa thanh toán)"
    return "💵 Thanh toán sau (thu tiền khi nhận)"


# ---------- Handlers ----------
router = Router()


@router.message(CommandStart())
async def start(m: Message, state: FSMContext):
    """Handle /start command - begin order flow."""
    logger.info(f"User {m.from_user.id} (@{m.from_user.username}) started bot")
    await state.clear()
    await state.update_data(cart=[], confirmed=False)
    await m.answer("Chào bạn 👋\nMời bạn chọn danh mục để bắt đầu đặt hàng:", reply_markup=kb_categories())
    await state.set_state(OrderFSM.choose_category)


@router.message(Command("myid"))
async def myid(m: Message):
    await m.answer(f"user_id: {m.from_user.id}\nchat_id: {m.chat.id}\nusername: @{m.from_user.username or '(none)'}")


@router.message(Command("set_mom"))
async def set_mom(m: Message):
    """Set current chat as admin notification channel."""
    if ADMIN_IDS and m.from_user.id not in ADMIN_IDS:
        logger.warning(f"Unauthorized /set_mom attempt by user {m.from_user.id}")
        await m.answer("Bạn không có quyền dùng lệnh này.")
        return
    await set_setting("mom_chat_id", str(m.chat.id))
    logger.info(f"Admin chat set to {m.chat.id} by user {m.from_user.id}")
    await m.answer("✅ Đã set chat này làm nơi nhận đơn của mẹ/admin.")


@router.callback_query(F.data == "new:start")
async def new_start(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.update_data(cart=[], confirmed=False)
    await c.message.edit_text("Mời bạn chọn danh mục để bắt đầu đặt hàng:", reply_markup=kb_categories())
    await state.set_state(OrderFSM.choose_category)
    await c.answer()


@router.callback_query(F.data.startswith("cat:"))
async def pick_category(c: CallbackQuery, state: FSMContext):
    cat = c.data.split(":", 1)[1]
    await state.update_data(category=cat)
    await c.message.edit_text(f"Bạn chọn: *{cat}*\nChọn món:", reply_markup=kb_items(cat), parse_mode=PM)
    await state.set_state(OrderFSM.choose_item)
    await c.answer()


@router.callback_query(F.data == "back:categories")
async def back_categories(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Mời bạn chọn danh mục:", reply_markup=kb_categories())
    await state.set_state(OrderFSM.choose_category)
    await c.answer()


@router.callback_query(F.data.startswith("item:"))
async def pick_item(c: CallbackQuery, state: FSMContext):
    item_id = c.data.split(":", 1)[1]
    it = ITEMS[item_id]
    await state.update_data(item_id=item_id)

    # ✅ THÊM MÔ TẢ NGAY DƯỚI TÊN Ở MÀN CHỌN SIZE
    desc = (it.get("desc") or "").strip()
    name_html = html.escape(it["name"])
    txt = f"Bạn chọn: <b>{name_html}</b>"
    if desc:
        txt += f"\n{html.escape(desc)}"
    txt += "\nChọn size:"

    await c.message.edit_text(txt, reply_markup=kb_sizes(item_id), parse_mode="HTML")
    await state.set_state(OrderFSM.choose_size)
    await c.answer()


@router.callback_query(F.data == "back:items")
async def back_items(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cat = data.get("category")
    await c.message.edit_text("Chọn món:", reply_markup=kb_items(cat))
    await state.set_state(OrderFSM.choose_item)
    await c.answer()


@router.callback_query(F.data.startswith("size:"))
async def pick_size(c: CallbackQuery, state: FSMContext):
    size = c.data.split(":", 1)[1]
    await state.update_data(size=size)
    await c.message.edit_text("Chọn % đường:", reply_markup=kb_percent("sugar"))
    await state.set_state(OrderFSM.choose_sugar)
    await c.answer()


@router.callback_query(F.data.startswith("sugar:"))
async def pick_sugar(c: CallbackQuery, state: FSMContext):
    sugar = c.data.split(":", 1)[1]
    await state.update_data(sugar=sugar)
    await c.message.edit_text("Chọn % đá:", reply_markup=kb_percent("ice"))
    await state.set_state(OrderFSM.choose_ice)
    await c.answer()


@router.callback_query(F.data.startswith("ice:"))
async def pick_ice(c: CallbackQuery, state: FSMContext):
    ice = c.data.split(":", 1)[1]
    await state.update_data(ice=ice, toppings=set())
    await c.message.edit_text("Chọn topping (bấm để bật/tắt):", reply_markup=kb_toppings(set()))
    await state.set_state(OrderFSM.choose_toppings)
    await c.answer()


@router.callback_query(F.data.startswith("top:"))
async def pick_topping(c: CallbackQuery, state: FSMContext):
    tid = c.data.split(":", 1)[1]
    data = await state.get_data()
    selected: set[str] = set(data.get("toppings", set()))

    if tid == "done":
        await c.message.edit_text("Nhập *số lượng* (chỉ nhập số, ví dụ: 1):", parse_mode=PM)
        await state.set_state(OrderFSM.enter_qty)
        await c.answer()
        return

    if tid in selected:
        selected.remove(tid)
    else:
        selected.add(tid)

    await state.update_data(toppings=selected)
    await c.message.edit_reply_markup(reply_markup=kb_toppings(selected))
    await c.answer("OK")


@router.callback_query(F.data == "back:prev")
async def back_prev(c: CallbackQuery, state: FSMContext):
    st = await state.get_state()
    if st == OrderFSM.choose_sugar.state:
        await c.message.edit_text("Chọn size:", reply_markup=kb_sizes((await state.get_data())["item_id"]))
        await state.set_state(OrderFSM.choose_size)
    elif st == OrderFSM.choose_ice.state:
        await c.message.edit_text("Chọn % đường:", reply_markup=kb_percent("sugar"))
        await state.set_state(OrderFSM.choose_sugar)
    elif st == OrderFSM.choose_toppings.state:
        await c.message.edit_text("Chọn % đá:", reply_markup=kb_percent("ice"))
        await state.set_state(OrderFSM.choose_ice)
    else:
        await c.message.edit_text("Mời bạn chọn danh mục:", reply_markup=kb_categories())
        await state.set_state(OrderFSM.choose_category)
    await c.answer()


@router.message(OrderFSM.enter_qty)
async def enter_qty(m: Message, state: FSMContext):
    txt = (m.text or "").strip()
    if not txt.isdigit() or int(txt) <= 0:
        await m.answer("Số lượng không hợp lệ. Hãy nhập số nguyên dương (ví dụ 1, 2, 3).")
        return

    qty = int(txt)
    data = await state.get_data()

    item_id = data["item_id"]
    size = data["size"]
    sugar = data["sugar"]
    ice = data["ice"]
    toppings_ids = sorted(list(data.get("toppings", set())))
    toppings_names = [TOPPING_ITEMS[tid]["name"] for tid in toppings_ids if tid in TOPPING_ITEMS]

    unit_price, line_total = calc_line(item_id, size, toppings_ids, qty)

    cart: List[Dict[str, Any]] = data.get("cart", [])
    new_line = {
        "item_id": item_id,
        "item_name": ITEMS[item_id]["name"],
        "size": size,
        "sugar": sugar,
        "ice": ice,
        "toppings_ids": toppings_ids,
        "toppings_names": toppings_names,
        "qty": qty,
        "unit_price": unit_price,
        "line_total": line_total,
    }

    cart, merged, line_no = merge_or_append_cart(cart, new_line)
    await state.update_data(cart=cart)

    if merged:
        await m.answer(f"✅ Đã gộp vào dòng *#{line_no}* (cộng thêm *{qty}*).", parse_mode=PM)
    else:
        await m.answer(f"✅ Đã thêm món mới vào giỏ (dòng *#{line_no}*).", parse_mode=PM)

    cart_text, _ = render_cart(cart)
    await m.answer(cart_text, parse_mode=PM, reply_markup=kb_cart())
    await state.set_state(OrderFSM.confirm)


@router.callback_query(F.data == "cart:add")
async def cart_add(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Mời bạn chọn danh mục để thêm món:", reply_markup=kb_categories())
    await state.set_state(OrderFSM.choose_category)
    await c.answer()


@router.callback_query(F.data == "cart:checkout")
async def cart_checkout(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cart: List[Dict[str, Any]] = data.get("cart", [])
    if not cart:
        await c.answer("Giỏ hàng trống!", show_alert=True)
        return

    await state.update_data(payment_method=None, payment_status=None)
    await c.message.edit_text("Chọn hình thức thanh toán:", reply_markup=kb_payment_choice())
    await state.set_state(OrderFSM.choose_payment)
    await c.answer()


@router.callback_query(F.data == "pay:back_cart")
async def pay_back_cart(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cart_text, _ = render_cart(data.get("cart", []))
    await c.message.edit_text(cart_text, parse_mode=PM, reply_markup=kb_cart())
    await state.set_state(OrderFSM.confirm)
    await c.answer()


@router.callback_query(F.data == "pay:now")
async def pay_now(c: CallbackQuery, state: FSMContext):
    await state.update_data(payment_method="pay_now", payment_status="pending")
    await c.message.edit_text(
        "💳 Bạn chọn *thanh toán trước*.\n"
        "➡️ Sau khi bấm *Xác nhận đặt hàng*, bot sẽ chuyển sang trang thanh toán (giả lập).\n\n"
        "Nhập *ghi chú* (gõ '-' nếu không có):",
        parse_mode=PM,
    )
    await state.set_state(OrderFSM.enter_note)
    await c.answer("OK")


@router.callback_query(F.data == "pay:later")
async def pay_later(c: CallbackQuery, state: FSMContext):
    await state.update_data(payment_method="pay_later", payment_status="cod")
    await c.message.edit_text(
        "💵 Bạn chọn *thanh toán sau* (thu tiền khi nhận).\n\nNhập *ghi chú* (gõ '-' nếu không có):",
        parse_mode=PM,
    )
    await state.set_state(OrderFSM.enter_note)
    await c.answer("OK")


@router.callback_query(F.data == "cart:cancel")
async def cart_cancel(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.edit_text("❌ Đã huỷ đơn. Gõ /start để đặt lại.")
    await c.answer()


@router.callback_query(F.data == "cart:edit")
async def cart_edit(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cart: List[Dict[str, Any]] = data.get("cart", [])
    if not cart:
        await c.answer("Giỏ hàng trống!", show_alert=True)
        return

    await state.update_data(editing_line=None)
    await c.message.edit_text(
        render_edit_list_text(cart),
        parse_mode=PM,
        reply_markup=kb_edit_cart_list(cart),
    )
    await c.answer()


@router.callback_query(F.data == "edit:back_cart")
async def edit_back_cart(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cart: List[Dict[str, Any]] = data.get("cart", [])
    cart_text, _ = render_cart(cart)
    await c.message.edit_text(cart_text, parse_mode=PM, reply_markup=kb_cart())
    await c.answer()


@router.callback_query(F.data == "edit:back_list")
async def edit_back_list(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cart: List[Dict[str, Any]] = data.get("cart", [])
    if not cart:
        await c.message.edit_text("🛒 Giỏ hàng trống.", reply_markup=kb_categories())
        await state.set_state(OrderFSM.choose_category)
        await c.answer()
        return

    await state.update_data(editing_line=None)
    await c.message.edit_text(
        render_edit_list_text(cart),
        parse_mode=PM,
        reply_markup=kb_edit_cart_list(cart),
    )
    await c.answer()


@router.callback_query(F.data.startswith("edit:item:"))
async def edit_pick_item(c: CallbackQuery, state: FSMContext):
    try:
        line_no = int(c.data.split(":")[-1])  # 1-based
    except ValueError:
        await c.answer("Không hợp lệ.", show_alert=True)
        return

    data = await state.get_data()
    cart: List[Dict[str, Any]] = data.get("cart", [])
    if not cart:
        await c.answer("Giỏ hàng trống!", show_alert=True)
        return

    if line_no < 1 or line_no > len(cart):
        await c.answer("Món không tồn tại.", show_alert=True)
        return

    await state.update_data(editing_line=line_no)
    await c.message.edit_text(
        render_edit_item_text(cart, line_no),
        parse_mode=PM,
        reply_markup=kb_edit_cart_item(line_no),
    )
    await c.answer()


async def _apply_edit_and_refresh(c: CallbackQuery, state: FSMContext, new_line_no: Optional[int], toast: str):
    data = await state.get_data()
    cart: List[Dict[str, Any]] = data.get("cart", [])

    if not cart:
        await state.update_data(editing_line=None)
        await c.message.edit_text("🛒 Giỏ hàng trống.", reply_markup=kb_categories())
        await state.set_state(OrderFSM.choose_category)
        await c.answer(toast)
        return

    if new_line_no is None:
        await state.update_data(editing_line=None)
        await c.message.edit_text(
            render_edit_list_text(cart),
            parse_mode=PM,
            reply_markup=kb_edit_cart_list(cart),
        )
        await c.answer(toast)
        return

    if new_line_no < 1:
        new_line_no = 1
    if new_line_no > len(cart):
        new_line_no = len(cart)

    await state.update_data(editing_line=new_line_no)
    await c.message.edit_text(
        render_edit_item_text(cart, new_line_no),
        parse_mode=PM,
        reply_markup=kb_edit_cart_item(new_line_no),
    )
    await c.answer(toast)


@router.callback_query(F.data.startswith("edit:inc:"))
async def edit_inc(c: CallbackQuery, state: FSMContext):
    try:
        line_no = int(c.data.split(":")[-1])
    except ValueError:
        await c.answer("Không hợp lệ.", show_alert=True)
        return

    data = await state.get_data()
    cart: List[Dict[str, Any]] = data.get("cart", [])
    if not cart or line_no < 1 or line_no > len(cart):
        await c.answer("Món không tồn tại.", show_alert=True)
        return

    line = cart[line_no - 1]
    line["qty"] += 1
    line["line_total"] = line["unit_price"] * line["qty"]

    await state.update_data(cart=cart)
    await _apply_edit_and_refresh(c, state, line_no, "Đã tăng")


@router.callback_query(F.data.startswith("edit:dec:"))
async def edit_dec(c: CallbackQuery, state: FSMContext):
    try:
        line_no = int(c.data.split(":")[-1])
    except ValueError:
        await c.answer("Không hợp lệ.", show_alert=True)
        return

    data = await state.get_data()
    cart: List[Dict[str, Any]] = data.get("cart", [])
    if not cart or line_no < 1 or line_no > len(cart):
        await c.answer("Món không tồn tại.", show_alert=True)
        return

    line = cart[line_no - 1]
    if line["qty"] <= 1:
        cart.pop(line_no - 1)
        await state.update_data(cart=cart)
        await _apply_edit_and_refresh(c, state, None, "Đã xoá (qty về 0)")
        return

    line["qty"] -= 1
    line["line_total"] = line["unit_price"] * line["qty"]
    await state.update_data(cart=cart)
    await _apply_edit_and_refresh(c, state, line_no, "Đã giảm")


@router.callback_query(F.data.startswith("edit:del:"))
async def edit_del(c: CallbackQuery, state: FSMContext):
    try:
        line_no = int(c.data.split(":")[-1])
    except ValueError:
        await c.answer("Không hợp lệ.", show_alert=True)
        return

    data = await state.get_data()
    cart: List[Dict[str, Any]] = data.get("cart", [])
    if not cart or line_no < 1 or line_no > len(cart):
        await c.answer("Món không tồn tại.", show_alert=True)
        return

    cart.pop(line_no - 1)
    await state.update_data(cart=cart)
    await _apply_edit_and_refresh(c, state, None, "Đã xoá món")


@router.message(OrderFSM.enter_note)
async def enter_note(m: Message, state: FSMContext):
    note = (m.text or "").strip()
    if note == "-":
        note = ""
    await state.update_data(note=note)

    data = await state.get_data()
    cart = data.get("cart", [])
    cart_text, _ = render_cart(cart)

    pay_method = data.get("payment_method") or "pay_later"
    pay_status = data.get("payment_status") or "cod"
    pay_text = payment_labels(pay_method, pay_status)

    msg = cart_text + f"\n\n*Thanh toán*: {pay_text}\nGhi chú: {note or 'Không'}\n\nBấm xác nhận để đặt hàng."
    await m.answer(msg, parse_mode=PM, reply_markup=kb_confirm())
    await state.set_state(OrderFSM.confirm)


@router.callback_query(F.data == "ok:back_to_cart")
async def ok_back_to_cart(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cart_text, _ = render_cart(data.get("cart", []))
    await c.message.edit_text(cart_text, parse_mode=PM, reply_markup=kb_cart())
    await state.set_state(OrderFSM.confirm)
    await c.answer()


@router.callback_query(F.data == "ok:cancel")
async def ok_cancel(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.edit_text("❌ Đã huỷ đơn. Gõ /start để đặt lại.")
    await c.answer()


@router.callback_query(F.data == "ok:confirm")
async def ok_confirm(c: CallbackQuery, state: FSMContext, bot: Bot):
    """Confirm order and save to database."""
    data = await state.get_data()

    if data.get("confirmed"):
        await c.answer("Đơn đã được tạo rồi.", show_alert=True)
        return
    await state.update_data(confirmed=True)

    cart = data.get("cart", [])
    if not cart:
        logger.warning(f"User {c.from_user.id} tried to confirm empty cart")
        await c.answer("Giỏ hàng trống!", show_alert=True)
        await state.update_data(confirmed=False)
        return

    cart_text, total = render_cart(cart)
    note = data.get("note", "")

    pay_method = data.get("payment_method") or "pay_later"
    pay_status = data.get("payment_status") or "cod"

    # giả lập thanh toán tại bước xác nhận nếu pay_now
    if pay_method == "pay_now":
        try:
            await c.message.edit_text("💳 Đang chuyển sang trang thanh toán (giả lập)...")
            await asyncio.sleep(1)
            await c.message.edit_text("✅ Thanh toán thành công (giả lập). Đang tạo đơn...")
            await asyncio.sleep(0.5)
        except Exception:
            pass
        pay_status = "paid"

    pay_text = payment_labels(pay_method, pay_status)

    order_code = await next_order_code()
    username = c.from_user.username or ""
    customer_chat_id = c.message.chat.id

    logger.info(f"Creating order {order_code} for user {c.from_user.id}")
    await save_order(
        order_code=order_code,
        customer_id=c.from_user.id,
        customer_chat_id=customer_chat_id,
        customer_username=username,
        note=note,
        total=total,
        cart=cart,
        payment_method=pay_method,
        payment_status=pay_status,
        status="received",
    )

    await c.message.edit_text(
        f"✅ Đặt hàng thành công!\nMã đơn: *{order_code}*\n\n{cart_text}\n\n*Thanh toán*: {pay_text}\nGhi chú: {note or 'Không'}",
        parse_mode=PM,
        reply_markup=kb_after_done(),
    )

    mom_chat_id = await get_setting("mom_chat_id")
    summary = (
        f"🧾 *ĐƠN MỚI* - {order_code}\n"
        f"Khách: @{username or '(no username)'} (id {c.from_user.id})\n\n"
        f"{cart_text}\n\n"
        f"*Tổng*: {vnd(total)}\n"
        f"*Thanh toán*: {pay_text}\n"
        f"Ghi chú: {note or 'Không'}"
    )

    target_chat = int(mom_chat_id) if mom_chat_id and mom_chat_id.isdigit() else None
    if target_chat:
        logger.info(f"Sending order {order_code} notification to admin chat {target_chat}")
        await bot.send_message(target_chat, summary, parse_mode=PM, reply_markup=kb_mom_status(order_code))
    elif ADMIN_IDS:
        admin_id = next(iter(ADMIN_IDS))
        logger.info(f"Sending order {order_code} notification to admin {admin_id}")
        await bot.send_message(admin_id, summary, parse_mode=PM, reply_markup=kb_mom_status(order_code))

    await state.clear()
    await c.answer("OK")


@router.callback_query(F.data.startswith("st:"))
async def mom_set_status(c: CallbackQuery, bot: Bot):
    """Admin handler to update order status."""
    try:
        _, status, order_code = c.data.split(":", 2)
    except ValueError:
        logger.error(f"Invalid status callback data: {c.data}")
        await c.answer("Dữ liệu không hợp lệ.", show_alert=True)
        return

    if ADMIN_IDS and c.from_user.id not in ADMIN_IDS:
        logger.warning(f"Unauthorized status change attempt by user {c.from_user.id}")
        await c.answer("Bạn không có quyền.", show_alert=True)
        return

    status_map = {
        "received": "✅ Đã nhận",
        "making": "🧋 Đang làm",
        "done": "🟢 Xong",
    }
    if status not in status_map:
        await c.answer("Trạng thái không hợp lệ.", show_alert=True)
        return

    # Answer callback immediately to avoid timeout
    await c.answer("Đang cập nhật...")

    logger.info(f"Admin {c.from_user.id} changed order {order_code} status to {status}")
    await set_order_status(order_code, status)

    try:
        new_text = c.message.text + f"\n\n*Cập nhật*: {status_map[status]}"
        await c.message.edit_text(new_text, parse_mode=PM, reply_markup=kb_mom_status(order_code))
    except Exception as e:
        logger.error(f"Failed to edit status message: {e}")

    customer_chat_id = await get_order_customer_chat(order_code)
    if customer_chat_id:
        try:
            await bot.send_message(customer_chat_id, f"{status_map[status]} cho đơn *{order_code}*", parse_mode=PM)
            logger.info(f"Status notification sent to customer chat {customer_chat_id}")
        except Exception as e:
            logger.error(f"Failed to send status notification to customer: {e}")


async def error_handler(event: ErrorEvent):
    """Global error handler for bot."""
    logger.error(f"Update {event.update} caused error: {event.exception}", exc_info=event.exception)


async def health_check(request):
    """Health check endpoint for Render."""
    logger.debug(f"Health check from {request.remote}")
    return web.Response(text="Bot is running!", status=200, headers={'Content-Type': 'text/plain'})


async def run_bot():
    """Run the Telegram bot polling."""
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN not found in environment variables")
        raise RuntimeError("BOT_TOKEN not found in .env")

    await init_db()

    bot = Bot(BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    dp.errors.register(error_handler)

    logger.info(f"Bot started successfully. Admin IDs: {ADMIN_IDS if ADMIN_IDS else 'None'}")
    logger.info("Bot is now polling for updates...")
    
    await dp.start_polling(bot)


async def keep_alive():
    """Ping own service every 14 minutes to prevent Render free tier spin down."""
    await asyncio.sleep(60)  # Wait 1 minute after startup
    
    # Render sets RENDER_EXTERNAL_URL automatically
    service_url = os.getenv('RENDER_EXTERNAL_URL')
    
    if not service_url:
        logger.warning("RENDER_EXTERNAL_URL not set, keep-alive disabled (OK for local dev)")
        return
    
    logger.info(f"Keep-alive task started, will ping {service_url}/health every 14 minutes")
    
    timeout = ClientTimeout(total=10)
    
    while True:
        try:
            async with ClientSession(timeout=timeout) as session:
                async with session.get(f"{service_url}/health") as resp:
                    if resp.status == 200:
                        logger.info("✅ Keep-alive ping successful")
                    else:
                        logger.warning(f"⚠️ Keep-alive ping returned {resp.status}")
        except Exception as e:
            logger.error(f"❌ Keep-alive ping failed: {e}")
        
        # Wait 14 minutes before next ping (Render timeout is 15 min)
        await asyncio.sleep(14 * 60)


async def run_web_server():
    """Run HTTP server for Render health checks."""
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    
    port = int(os.getenv('PORT', 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"✅ HTTP server started on 0.0.0.0:{port}")
    print(f"✅ HTTP server listening on port {port}")
    
    # Keep the server running forever
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info("Web server stopping...")
        await runner.cleanup()


async def main():
    """Main function to start both bot and web server."""
    logger.info("="*50)
    logger.info("Starting Telegram Bot + Web Server + Keep-Alive...")
    
    # Start web server FIRST (critical for Render health check)
    web_task = asyncio.create_task(run_web_server())
    
    # Wait to ensure web server is ready
    await asyncio.sleep(2)
    
    # Start keep-alive ping task (prevents Render spin down)
    keepalive_task = asyncio.create_task(keep_alive())
    
    # Then start bot polling
    bot_task = asyncio.create_task(run_bot())
    
    # Keep all running
    try:
        await asyncio.gather(web_task, keepalive_task, bot_task, return_exceptions=True)
    except asyncio.CancelledError:
        logger.info("Main tasks cancelled, cleaning up...")
        web_task.cancel()
        keepalive_task.cancel()
        bot_task.cancel()
        await asyncio.gather(web_task, keepalive_task, bot_task, return_exceptions=True)


if __name__ == "__main__":
    print("✅ Bot + Web Server starting... Press Ctrl+C to stop.")
    
    # Platform-specific signal handling
    if platform.system() == 'Windows':
        # Windows: Use standard signal handling
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            sys.exit(0)
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        try:
            asyncio.run(main())
        except (KeyboardInterrupt, SystemExit):
            logger.info("Bot stopped gracefully")
            print("\n⛔ Bot stopped gracefully.")
        except Exception as e:
            logger.critical(f"Bot crashed: {e}", exc_info=True)
            sys.exit(1)
    else:
        # Unix/Linux (Render): Use asyncio signal handlers
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        def signal_handler(signum):
            logger.info(f"Received signal {signum}, shutting down gracefully...")
            for task in asyncio.all_tasks(loop):
                task.cancel()
            loop.stop()
        
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))
        
        try:
            loop.run_until_complete(main())
        except (KeyboardInterrupt, SystemExit):
            logger.info("Bot stopped gracefully")
            print("\n⛔ Bot stopped gracefully.")
        except Exception as e:
            logger.critical(f"Bot crashed: {e}", exc_info=True)
            sys.exit(1)
        finally:
            loop.close()