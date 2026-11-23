"""SaveShelf - Ứng dụng báo giá sốc thực phẩm cận date cho người mua gần bạn.

Chạy:  python app.py   ->  http://127.0.0.1:5000
"""
import math
import os
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (Flask, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("SAVESHELF_DB", os.path.join(BASE_DIR, "saveshelf.db"))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "doi-khoa-bi-mat-nay-khi-trien-khai")

CATEGORIES = ["Rau củ quả", "Thịt cá", "Sữa & trứng", "Bánh mì & bánh ngọt",
              "Đồ uống", "Đồ khô & đóng gói", "Đồ ăn chế biến sẵn", "Khác"]
MAX_DAYS_WINDOW = 7          # "cận date" = còn tối đa 7 ngày
MIN_DISCOUNT = 10            # cửa hàng phải giảm tối thiểu 10%


# ----------------------------------------------------------------- Database
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS stores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    address TEXT NOT NULL,
    phone TEXT,
    lat REAL NOT NULL,
    lng REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    original_price INTEGER NOT NULL,
    discount_percent INTEGER NOT NULL,
    expiry_date TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
"""


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(SCHEMA)
    db.commit()
    db.close()


def seed_demo():
    """Dữ liệu mẫu quanh Quận 1, TP.HCM (chỉ chạy khi DB trống)."""
    db = sqlite3.connect(DB_PATH)
    if db.execute("SELECT COUNT(*) FROM stores").fetchone()[0]:
        db.close()
        return
    pw = generate_password_hash("123456")
    stores = [
        ("Tiệm Bánh Hoa Sữa", "hoasua@demo.vn", "12 Nguyễn Huệ, Quận 1", "0901234567", 10.7742, 106.7030),
        ("Siêu thị mini Bình An", "binhan@demo.vn", "45 Lê Lợi, Quận 1", "0902345678", 10.7731, 106.6988),
        ("Cửa hàng Rau Sạch Xanh", "rauxanh@demo.vn", "88 Pasteur, Quận 3", "0903456789", 10.7835, 106.6951),
        ("Sữa & Trứng Gia Đình", "suatrung@demo.vn", "20 Hai Bà Trưng, Quận 1", "0904567890", 10.7889, 106.7007),
    ]
    for s in stores:
        db.execute("INSERT INTO stores(name,email,password_hash,address,phone,lat,lng) VALUES(?,?,?,?,?,?,?)",
                   (s[0], s[1], pw, s[2], s[3], s[4], s[5]))
    today = date.today()
    now = datetime.now().isoformat(timespec="seconds")
    items = [
        (1, "Bánh mì sandwich nguyên cám", "Bánh mì & bánh ngọt", 32000, 50, 0, 15),
        (1, "Bánh su kem (hộp 6)", "Bánh mì & bánh ngọt", 60000, 40, 1, 10),
        (2, "Sữa tươi tiệt trùng 1L", "Sữa & trứng", 35000, 30, 3, 40),
        (2, "Xúc xích heo (gói 500g)", "Thịt cá", 78000, 35, 2, 20),
        (2, "Mì ý Barilla 500g", "Đồ khô & đóng gói", 52000, 25, 6, 30),
        (3, "Cải bó xôi (500g)", "Rau củ quả", 40000, 45, 1, 12),
        (3, "Cà chua bi hộp 300g", "Rau củ quả", 30000, 30, 2, 25),
        (4, "Trứng gà ta (vỉ 10)", "Sữa & trứng", 48000, 20, 5, 18),
        (4, "Sữa chua uống men sống (lốc 4)", "Sữa & trứng", 28000, 40, 2, 35),
    ]
    for sid, name, cat, price, disc, days, qty in items:
        db.execute("""INSERT INTO items(store_id,name,category,original_price,discount_percent,
                      expiry_date,quantity,created_at) VALUES(?,?,?,?,?,?,?,?)""",
                   (sid, name, cat, price, disc, (today + timedelta(days=days)).isoformat(), qty, now))
    db.commit()
    db.close()


# ------------------------------------------------------------------ Helpers
def haversine_km(lat1, lng1, lat2, lng2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def suggest_discount(days_left):
    """Gợi ý mức giảm giá dựa trên số ngày còn lại."""
    if days_left <= 0:
        return 60
    if days_left == 1:
        return 50
    if days_left <= 3:
        return 30
    return 20


def sale_price(original, percent):
    # làm tròn xuống hàng trăm đồng cho dễ thanh toán
    return max(0, int(original * (100 - percent) / 100) // 100 * 100)


@app.template_filter("vnd")
def vnd(value):
    return f"{int(value):,}".replace(",", ".") + "₫"


@app.template_filter("ngay")
def ngay(iso):
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")


def days_left_label(d):
    if d < 0:
        return "Đã hết hạn"
    if d == 0:
        return "Hết hạn hôm nay"
    if d == 1:
        return "Còn 1 ngày"
    return f"Còn {d} ngày"


def row_to_deal(row, lat=None, lng=None):
    exp = datetime.strptime(row["expiry_date"], "%Y-%m-%d").date()
    left = (exp - date.today()).days
    deal = {
        "id": row["id"],
        "name": row["name"],
        "category": row["category"],
        "store_id": row["store_id"],
        "store_name": row["store_name"],
        "address": row["address"],
        "phone": row["phone"],
        "lat": row["lat"],
        "lng": row["lng"],
        "original_price": row["original_price"],
        "discount_percent": row["discount_percent"],
        "sale_price": sale_price(row["original_price"], row["discount_percent"]),
        "expiry_date": row["expiry_date"],
        "days_left": left,
        "days_label": days_left_label(left),
        "quantity": row["quantity"],
    }
    if lat is not None and lng is not None:
        deal["distance_km"] = round(haversine_km(lat, lng, row["lat"], row["lng"]), 2)
    return deal


def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if not session.get("store_id"):
            flash("Vui lòng đăng nhập cửa hàng.", "warn")
            return redirect(url_for("store_login"))
        return view(*a, **kw)
    return wrapped


def parse_float(name):
    try:
        return float(request.args.get(name, ""))
    except ValueError:
        return None


# ------------------------------------------------------------ Shopper views
@app.route("/")
def index():
    return render_template("index.html", categories=CATEGORIES, max_days=MAX_DAYS_WINDOW)


@app.route("/api/deals")
def api_deals():
    """Danh sách ưu đãi quanh vị trí người mua.

    Tham số: lat, lng, radius (km, mặc định 3), days (tối đa ngày còn lại),
             category (tùy chọn), sort = distance | discount | expiry
    """
    lat, lng = parse_float("lat"), parse_float("lng")
    if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return jsonify(error="Thiếu hoặc sai tọa độ (lat, lng)."), 400
    try:
        radius = min(max(float(request.args.get("radius", 3)), 0.2), 50)
        days = min(max(int(request.args.get("days", MAX_DAYS_WINDOW)), 0), 30)
    except ValueError:
        return jsonify(error="Tham số không hợp lệ."), 400
    category = request.args.get("category", "").strip()
    sort = request.args.get("sort", "distance")

    rows = get_db().execute(
        """SELECT i.*, s.name AS store_name, s.address, s.phone, s.lat, s.lng
           FROM items i JOIN stores s ON s.id = i.store_id
           WHERE i.quantity > 0 AND i.expiry_date >= ? AND i.expiry_date <= ?""",
        (date.today().isoformat(), (date.today() + timedelta(days=days)).isoformat()),
    ).fetchall()

    deals = [row_to_deal(r, lat, lng) for r in rows]
    deals = [d for d in deals if d["distance_km"] <= radius
             and (not category or d["category"] == category)]
    keys = {
        "distance": lambda d: (d["distance_km"], d["days_left"]),
        "discount": lambda d: (-d["discount_percent"], d["distance_km"]),
        "expiry": lambda d: (d["days_left"], d["distance_km"]),
    }
    deals.sort(key=keys.get(sort, keys["distance"]))
    return jsonify(deals=deals, radius=radius, count=len(deals),
                   generated_at=datetime.now().isoformat(timespec="seconds"))


@app.route("/api/suggest-discount")
def api_suggest():
    try:
        d = datetime.strptime(request.args.get("expiry", ""), "%Y-%m-%d").date()
    except ValueError:
        return jsonify(error="Ngày không hợp lệ"), 400
    return jsonify(percent=suggest_discount((d - date.today()).days))


# ------------------------------------------------------------- Store views
@app.route("/cua-hang/dang-ky", methods=["GET", "POST"])
def store_register():
    if request.method == "POST":
        f = request.form
        name, email = f.get("name", "").strip(), f.get("email", "").strip().lower()
        address, phone = f.get("address", "").strip(), f.get("phone", "").strip()
        password = f.get("password", "")
        try:
            lat, lng = float(f.get("lat", "")), float(f.get("lng", ""))
        except ValueError:
            lat = lng = None
        if not (name and email and address and len(password) >= 6):
            flash("Vui lòng điền đủ thông tin (mật khẩu tối thiểu 6 ký tự).", "error")
        elif lat is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
            flash("Hãy chọn vị trí cửa hàng trên bản đồ.", "error")
        else:
            try:
                db = get_db()
                cur = db.execute(
                    "INSERT INTO stores(name,email,password_hash,address,phone,lat,lng) VALUES(?,?,?,?,?,?,?)",
                    (name, email, generate_password_hash(password), address, phone, lat, lng))
                db.commit()
                session["store_id"] = cur.lastrowid
                flash("Đăng ký thành công! Hãy đăng sản phẩm cận date đầu tiên.", "ok")
                return redirect(url_for("dashboard"))
            except sqlite3.IntegrityError:
                flash("Email này đã được đăng ký.", "error")
    return render_template("register.html")


@app.route("/cua-hang/dang-nhap", methods=["GET", "POST"])
def store_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        row = get_db().execute("SELECT * FROM stores WHERE email=?", (email,)).fetchone()
        if row and check_password_hash(row["password_hash"], request.form.get("password", "")):
            session["store_id"] = row["id"]
            return redirect(url_for("dashboard"))
        flash("Email hoặc mật khẩu không đúng.", "error")
    return render_template("login.html")


@app.route("/cua-hang/dang-xuat")
def store_logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/cua-hang", methods=["GET", "POST"])
@login_required
def dashboard():
    db = get_db()
    store = db.execute("SELECT * FROM stores WHERE id=?", (session["store_id"],)).fetchone()
    if store is None:
        session.clear()
        return redirect(url_for("store_login"))

    if request.method == "POST":
        f = request.form
        name, category = f.get("name", "").strip(), f.get("category", "")
        try:
            price = int(f.get("original_price", ""))
            qty = int(f.get("quantity", ""))
            expiry = datetime.strptime(f.get("expiry_date", ""), "%Y-%m-%d").date()
            left = (expiry - date.today()).days
            percent = int(f.get("discount_percent") or suggest_discount(left))
        except ValueError:
            flash("Dữ liệu không hợp lệ, vui lòng kiểm tra lại.", "error")
            return redirect(url_for("dashboard"))
        if not name or category not in CATEGORIES or price <= 0 or qty <= 0:
            flash("Vui lòng nhập đủ tên, nhóm hàng, giá và số lượng hợp lệ.", "error")
        elif left < 0:
            flash("Không thể đăng sản phẩm đã hết hạn.", "error")
        elif left > MAX_DAYS_WINDOW:
            flash(f"Chỉ đăng sản phẩm còn tối đa {MAX_DAYS_WINDOW} ngày hạn sử dụng.", "error")
        elif not (MIN_DISCOUNT <= percent <= 90):
            flash(f"Mức giảm giá phải từ {MIN_DISCOUNT}% đến 90%.", "error")
        else:
            db.execute("""INSERT INTO items(store_id,name,category,original_price,discount_percent,
                          expiry_date,quantity,created_at) VALUES(?,?,?,?,?,?,?,?)""",
                       (store["id"], name, category, price, percent, expiry.isoformat(), qty,
                        datetime.now().isoformat(timespec="seconds")))
            db.commit()
            flash(f"Đã đăng “{name}” giảm {percent}%. Người mua quanh đây sẽ nhận thông báo.", "ok")
        return redirect(url_for("dashboard"))

    rows = db.execute(
        """SELECT i.*, s.name AS store_name, s.address, s.phone, s.lat, s.lng
           FROM items i JOIN stores s ON s.id = i.store_id
           WHERE i.store_id=? ORDER BY i.expiry_date""", (store["id"],)).fetchall()
    items = [row_to_deal(r) for r in rows]
    return render_template("dashboard.html", store=store, items=items, categories=CATEGORIES,
                           max_days=MAX_DAYS_WINDOW, min_discount=MIN_DISCOUNT,
                           today=date.today().isoformat(),
                           max_date=(date.today() + timedelta(days=MAX_DAYS_WINDOW)).isoformat())


@app.route("/cua-hang/san-pham/<int:item_id>/cap-nhat", methods=["POST"])
@login_required
def item_update(item_id):
    db = get_db()
    action = request.form.get("action")
    if action == "soldout":
        db.execute("UPDATE items SET quantity=0 WHERE id=? AND store_id=?", (item_id, session["store_id"]))
        flash("Đã đánh dấu hết hàng.", "ok")
    elif action == "delete":
        db.execute("DELETE FROM items WHERE id=? AND store_id=?", (item_id, session["store_id"]))
        flash("Đã xóa sản phẩm.", "ok")
    db.commit()
    return redirect(url_for("dashboard"))


# --------------------------------------------------------------------- Main
init_db()
seed_demo()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=bool(os.environ.get("DEBUG")))
