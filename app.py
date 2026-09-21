import os
from datetime import datetime
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from PIL import Image, ExifTags

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-change-this")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///webgis.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "uploads")
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

CATEGORIES = {
    "Jalan": ["Jalan berlubang", "Permukaan rusak", "Retak", "Genangan", "Trotoar rusak", "Marka jalan rusak"],
    "Penerangan": ["Lampu mati", "Lampu redup", "Tiang lampu rusak", "Kabel/instalasi bermasalah"],
    "Gedung": ["Dinding rusak", "Atap rusak", "Lantai rusak", "Pintu/jendela rusak", "Plafon rusak", "Fasilitas gedung lainnya"],
    "Parkir": ["Marka parkir rusak", "Permukaan parkir rusak", "Rambu parkir rusak", "Penerangan area parkir"],
    "Sanitasi": ["Toilet rusak", "Keran rusak", "Saluran tersumbat", "Kebocoran", "Tempat sampah rusak"],
    "Transportasi": ["Halte rusak", "Rambu transportasi rusak", "Fasilitas shuttle rusak", "Jalur transportasi terganggu"],
}

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    identity = db.Column(db.String(120), unique=True, nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=True)
    name = db.Column(db.String(160), nullable=False)
    role = db.Column(db.String(30), default="user")  # user/operator

    reports = db.relationship("Report", backref="reporter", lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return self.password_hash and check_password_hash(self.password_hash, password)

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    damage_type = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    photo = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(30), default="pending")  # pending/approved/disapproved
    operator_reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def operator_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if current_user.role != "operator":
            flash("Halaman ini khusus operator.", "error")
            return redirect(url_for("map_page"))
        return fn(*args, **kwargs)
    return wrapper

def extract_gps(path):
    """Read GPS EXIF from a photo. Returns (lat, lon) or (None, None)."""
    try:
        img = Image.open(path)
        exif = img.getexif()
        if not exif:
            return None, None
        gps_tag = next((k for k, v in ExifTags.TAGS.items() if v == "GPSInfo"), None)
        gps = exif.get(gps_tag)
        if not gps:
            return None, None

        def dms_to_deg(value):
            parts = [float(x) for x in value]
            return parts[0] + parts[1] / 60 + parts[2] / 3600

        lat = dms_to_deg(gps[2])
        lon = dms_to_deg(gps[4])
        if gps.get(1) == "S":
            lat = -lat
        if gps.get(3) == "W":
            lon = -lon
        return lat, lon
    except Exception:
        return None, None

@app.context_processor
def inject_globals():
    return {"categories": CATEGORIES}

@app.route("/")
def index():
    return redirect(url_for("map_page"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identity = request.form.get("identity", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter((User.identity == identity) | (User.email == identity)).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            return redirect(url_for("operator_dashboard" if user.role == "operator" else "map_page"))
        flash("NIM/email atau password tidak sesuai.", "error")
    return render_template("login.html", sso_enabled=os.getenv("SSO_ENABLED", "false").lower() == "true")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        nim = request.form.get("nim", "").strip()
        email = request.form.get("email", "").strip().lower()
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "")
        if not nim or not email or not name or not password:
            flash("Semua field wajib diisi.", "error")
            return render_template("register.html")
        if User.query.filter((User.identity == nim) | (User.email == email)).first():
            flash("NIM atau email sudah terdaftar.", "error")
            return render_template("register.html")
        user = User(identity=nim, email=email, name=name, role="user")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("Akun berhasil dibuat. Silakan masuk.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/auth/sso")
def sso_login():
    # Generic OIDC hook. Configure with Authlib in a real UNDIP SSO environment.
    if os.getenv("SSO_ENABLED", "false").lower() != "true":
        flash("SSO belum dikonfigurasi. Isi variabel SSO_* pada .env.", "error")
        return redirect(url_for("login"))
    flash("Endpoint SSO siap diintegrasikan dengan IdP UNDIP melalui OpenID Connect.", "info")
    return redirect(url_for("login"))

@app.route("/map")
@login_required
def map_page():
    approved = Report.query.filter_by(status="approved").order_by(Report.created_at.desc()).all()
    latest = Report.query.order_by(Report.created_at.desc()).limit(6).all()
    return render_template("map.html", approved=approved, latest=latest)

@app.route("/report/new", methods=["GET", "POST"])
@login_required
def new_report():
    if request.method == "POST":
        category = request.form.get("category")
        damage_type = request.form.get("damage_type")
        description = request.form.get("description", "").strip()
        title = request.form.get("title", "").strip()
        lat_raw = request.form.get("latitude", "").strip()
        lon_raw = request.form.get("longitude", "").strip()

        if category not in CATEGORIES or damage_type not in CATEGORIES[category]:
            flash("Kategori atau jenis kerusakan tidak valid.", "error")
            return render_template("report_form.html")
        try:
            lat, lon = float(lat_raw), float(lon_raw)
        except ValueError:
            flash("Titik lokasi belum dipilih.", "error")
            return render_template("report_form.html")

        photo_name = None
        photo = request.files.get("photo")
        if photo and photo.filename:
            ext = os.path.splitext(photo.filename)[1].lower()
            if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
                flash("Format foto harus JPG, JPEG, PNG, atau WEBP.", "error")
                return render_template("report_form.html")
            photo_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{secure_filename(photo.filename)}"
            path = os.path.join(app.config["UPLOAD_FOLDER"], photo_name)
            photo.save(path)

        report = Report(
            title=title or f"{category} - {damage_type}",
            category=category,
            damage_type=damage_type,
            description=description,
            latitude=lat,
            longitude=lon,
            photo=photo_name,
            user_id=current_user.id,
        )
        db.session.add(report)
        db.session.commit()
        flash("Laporan dikirim dan menunggu verifikasi operator.", "success")
        return redirect(url_for("history"))
    return render_template("report_form.html")

@app.route("/report/extract-gps", methods=["POST"])
@login_required
def extract_photo_gps():
    photo = request.files.get("photo")
    if not photo or not photo.filename:
        return jsonify({"ok": False, "message": "Foto belum dipilih."}), 400
    temp = os.path.join(app.config["UPLOAD_FOLDER"], f"_temp_{datetime.utcnow().timestamp()}.jpg")
    try:
        photo.save(temp)
        lat, lon = extract_gps(temp)
        if lat is None:
            return jsonify({"ok": False, "message": "Foto tidak memiliki metadata GPS/EXIF."})
        return jsonify({"ok": True, "latitude": lat, "longitude": lon})
    finally:
        if os.path.exists(temp):
            os.remove(temp)

@app.route("/history")
@login_required
def history():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "")
    status = request.args.get("status", "")
    query = Report.query
    if current_user.role != "operator":
        query = query.filter_by(user_id=current_user.id)
    if q:
        query = query.filter(
            db.or_(Report.title.ilike(f"%{q}%"),
                   Report.description.ilike(f"%{q}%"),
                   Report.damage_type.ilike(f"%{q}%"))
        )
    if category in CATEGORIES:
        query = query.filter_by(category=category)
    if status in ["pending", "approved", "disapproved"]:
        query = query.filter_by(status=status)
    reports = query.order_by(Report.created_at.desc()).all()
    return render_template("history.html", reports=reports, q=q, selected_category=category, selected_status=status)

@app.route("/report/<int:report_id>")
@login_required
def report_detail(report_id):
    report = db.get_or_404(Report, report_id)
    if report.status != "approved" and report.user_id != current_user.id and current_user.role != "operator":
        flash("Laporan belum tersedia untuk publik.", "error")
        return redirect(url_for("map_page"))
    return render_template("report_detail.html", report=report)

@app.route("/operator")
@operator_required
def operator_dashboard():
    pending = Report.query.filter_by(status="pending").order_by(Report.created_at.asc()).all()
    stats = {
        "pending": Report.query.filter_by(status="pending").count(),
        "approved": Report.query.filter_by(status="approved").count(),
        "disapproved": Report.query.filter_by(status="disapproved").count(),
        "total": Report.query.count(),
    }
    return render_template("operator.html", pending=pending, stats=stats)

@app.route("/operator/review/<int:report_id>", methods=["POST"])
@operator_required
def review_report(report_id):
    report = db.get_or_404(Report, report_id)
    decision = request.form.get("decision")
    reason = request.form.get("reason", "").strip()
    if decision not in ["approved", "disapproved"]:
        flash("Keputusan tidak valid.", "error")
        return redirect(url_for("operator_dashboard"))
    if decision == "disapproved" and not reason:
        flash("Alasan wajib diisi saat laporan di-disapprove.", "error")
        return redirect(url_for("operator_dashboard"))
    report.status = decision
    report.operator_reason = reason or "Laporan telah diverifikasi dan disetujui."
    report.reviewed_at = datetime.utcnow()
    db.session.commit()
    flash(f"Laporan #{report.id} berhasil {'disetujui' if decision == 'approved' else 'ditolak'}.", "success")
    return redirect(url_for("operator_dashboard"))

@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    # Only authenticated users can access uploaded report photos.
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/api/categories")
def api_categories():
    return jsonify(CATEGORIES)

def seed():
    with app.app_context():
        db.create_all()

        operator_email = os.getenv(
            "OPERATOR_EMAIL",
            "operator@undip.ac.id"
        ).lower()

        operator_password = os.getenv(
            "OPERATOR_PASSWORD",
            "operator123"
        )

        # Cek operator berdasarkan identity ATAU email
        op = User.query.filter(
            (User.identity == "OPERATOR") |
            (User.email == operator_email)
        ).first()

        if not op:
            op = User(
                identity="OPERATOR",
                email=operator_email,
                name="Operator DEEPS",
                role="operator"
            )
            op.set_password(operator_password)
            db.session.add(op)

        # User demo
        if not User.query.filter_by(identity="240001").first():
            u = User(
                identity="240001",
                email="240001@students.undip.ac.id",
                name="Mahasiswa Demo",
                role="user"
            )
            u.set_password("mahasiswa123")
            db.session.add(u)

        db.session.commit()


if __name__ == "__main__":
    seed()
    app.run(debug=True)
