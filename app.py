
import os
from datetime import datetime
from functools import wraps

from dotenv import load_dotenv
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    send_from_directory,
)
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from PIL import Image, ExifTags
from sqlalchemy import inspect, text


# =========================================================
# ENVIRONMENT
# =========================================================

load_dotenv()


# =========================================================
# FLASK CONFIGURATION
# =========================================================

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv(
    "SECRET_KEY",
    "dev-change-this"
)

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL"
)

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["UPLOAD_FOLDER"] = os.path.join(
    app.root_path,
    "uploads"
)

app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

os.makedirs(
    app.config["UPLOAD_FOLDER"],
    exist_ok=True
)


# =========================================================
# DATABASE
# =========================================================

db = SQLAlchemy(app)


# =========================================================
# LOGIN MANAGER
# =========================================================

login_manager = LoginManager(app)
login_manager.login_view = "login"


# =========================================================
# CATEGORY
# =========================================================

CATEGORIES = {
    "Jalan": [
        "Jalan berlubang",
        "Permukaan rusak",
        "Retak",
        "Genangan",
        "Trotoar rusak",
        "Marka jalan rusak",
    ],

    "Penerangan": [
        "Lampu mati",
        "Lampu redup",
        "Tiang lampu rusak",
        "Kabel/instalasi bermasalah",
    ],

    "Gedung": [
        "Dinding rusak",
        "Atap rusak",
        "Lantai rusak",
        "Pintu/jendela rusak",
        "Plafon rusak",
        "Fasilitas gedung lainnya",
    ],

    "Parkir": [
        "Marka parkir rusak",
        "Permukaan parkir rusak",
        "Rambu parkir rusak",
        "Penerangan area parkir",
    ],

    "Sanitasi": [
        "Toilet rusak",
        "Keran rusak",
        "Saluran tersumbat",
        "Kebocoran",
        "Tempat sampah rusak",
    ],

    "Transportasi": [
        "Halte rusak",
        "Rambu transportasi rusak",
        "Fasilitas shuttle rusak",
        "Jalur transportasi terganggu",
    ],
}


# =========================================================
# USER MODEL
# =========================================================

class User(UserMixin, db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    identity = db.Column(
        db.String(120),
        unique=True,
        nullable=False
    )

    email = db.Column(
        db.String(160),
        unique=True,
        nullable=True
    )

    password_hash = db.Column(
        db.String(255),
        nullable=True
    )

    name = db.Column(
        db.String(160),
        nullable=False
    )

    role = db.Column(
        db.String(30),
        default="user"
    )

    reports = db.relationship(
        "Report",
        backref="reporter",
        lazy=True
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(
            password
        )

    def check_password(self, password):
        return (
            self.password_hash
            and check_password_hash(
                self.password_hash,
                password
            )
        )


# =========================================================
# REPORT MODEL
# =========================================================

class Report(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    title = db.Column(
        db.String(180),
        nullable=False
    )

    category = db.Column(
        db.String(50),
        nullable=False
    )

    damage_type = db.Column(
        db.String(120),
        nullable=False
    )

    description = db.Column(
        db.Text,
        nullable=False
    )

    latitude = db.Column(
        db.Float,
        nullable=False
    )

    longitude = db.Column(
        db.Float,
        nullable=False
    )

    # =====================================================
    # FOTO LAPORAN AWAL
    # =====================================================

    photo = db.Column(
        db.String(255),
        nullable=True
    )

    # =====================================================
    # FOTO HASIL PERBAIKAN
    # =====================================================

    completion_photo = db.Column(
        db.String(255),
        nullable=True
    )

    # =====================================================
    # STATUS
    #
    # pending     = laporan baru
    # processing  = laporan disetujui dan sedang diproses
    # completed   = perbaikan selesai
    # disapproved = laporan ditolak
    # =====================================================

    status = db.Column(
        db.String(30),
        default="pending"
    )

    # =====================================================
    # KETERANGAN OPERATOR
    # =====================================================

    operator_reason = db.Column(
        db.Text,
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    reviewed_at = db.Column(
        db.DateTime,
        nullable=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )


# =========================================================
# LOGIN USER
# =========================================================

@login_manager.user_loader
def load_user(user_id):

    return db.session.get(
        User,
        int(user_id)
    )


# =========================================================
# OPERATOR DECORATOR
# =========================================================

def operator_required(fn):

    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):

        if current_user.role != "operator":

            flash(
                "Halaman ini khusus operator.",
                "error"
            )

            return redirect(
                url_for("map_page")
            )

        return fn(
            *args,
            **kwargs
        )

    return wrapper


# =========================================================
# EXTRACT GPS FROM PHOTO
# =========================================================

def extract_gps(path):
    """
    Membaca GPS EXIF dari foto.
    Mengembalikan (latitude, longitude)
    atau (None, None).
    """

    try:

        img = Image.open(path)

        exif = img.getexif()

        if not exif:
            return None, None

        gps_tag = next(
            (
                k
                for k, v in ExifTags.TAGS.items()
                if v == "GPSInfo"
            ),
            None
        )

        gps = exif.get(gps_tag)

        if not gps:
            return None, None

        def dms_to_deg(value):

            parts = [
                float(x)
                for x in value
            ]

            return (
                parts[0]
                + parts[1] / 60
                + parts[2] / 3600
            )

        lat = dms_to_deg(
            gps[2]
        )

        lon = dms_to_deg(
            gps[4]
        )

        if gps.get(1) == "S":
            lat = -lat

        if gps.get(3) == "W":
            lon = -lon

        return lat, lon

    except Exception:

        return None, None


# =========================================================
# GLOBAL TEMPLATE DATA
# =========================================================

@app.context_processor
def inject_globals():

    return {
        "categories": CATEGORIES
    }


# =========================================================
# DATABASE SCHEMA UPDATE
# =========================================================

def ensure_schema():

    """
    Memastikan database lama mempunyai kolom
    completion_photo.

    Fungsi ini juga mengubah status lama:
        approved -> processing

    sehingga database versi lama tetap kompatibel.
    """

    try:

        inspector = inspect(db.engine)

        tables = inspector.get_table_names()

        # -----------------------------------------------
        # Jika tabel report belum ada
        # -----------------------------------------------

        if "report" not in tables:

            db.create_all()

            return

        columns = [
            column["name"]
            for column in inspector.get_columns(
                "report"
            )
        ]

        # -----------------------------------------------
        # Tambahkan completion_photo jika belum ada
        # -----------------------------------------------

        if "completion_photo" not in columns:

            with db.engine.begin() as connection:

                connection.execute(
                    text(
                        """
                        ALTER TABLE report
                        ADD COLUMN completion_photo VARCHAR(255)
                        """
                    )
                )

        # -----------------------------------------------
        # Migrasi status lama
        #
        # approved pada versi lama dianggap sebagai
        # laporan yang sudah disetujui dan sedang diproses.
        # -----------------------------------------------

        with db.engine.begin() as connection:

            connection.execute(
                text(
                    """
                    UPDATE report
                    SET status = 'processing'
                    WHERE status = 'approved'
                    """
                )
            )

    except Exception as e:

        print(
            "Peringatan saat memastikan schema database:",
            e
        )


# =========================================================
# HOME
# =========================================================

@app.route("/")
def index():

    return redirect(
        url_for("map_page")
    )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        identity = request.form.get(
            "identity",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        user = User.query.filter(
            (User.identity == identity)
            |
            (User.email == identity)
        ).first()

        if user and user.check_password(
            password
        ):

            login_user(
                user,
                remember=True
            )

            if user.role == "operator":

                return redirect(
                    url_for(
                        "operator_dashboard"
                    )
                )

            return redirect(
                url_for("map_page")
            )

        flash(
            "NIM/email atau password tidak sesuai.",
            "error"
        )

    return render_template(
        "login.html",
        sso_enabled=(
            os.getenv(
                "SSO_ENABLED",
                "false"
            ).lower() == "true"
        )
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
@login_required
def logout():

    logout_user()

    return redirect(
        url_for("login")
    )


# =========================================================
# REGISTER
# =========================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "POST":

        nim = request.form.get(
            "nim",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        name = request.form.get(
            "name",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if not nim or not email or not name or not password:

            flash(
                "Semua field wajib diisi.",
                "error"
            )

            return render_template(
                "register.html"
            )

        existing = User.query.filter(
            (User.identity == nim)
            |
            (User.email == email)
        ).first()

        if existing:

            flash(
                "NIM atau email sudah terdaftar.",
                "error"
            )

            return render_template(
                "register.html"
            )

        user = User(
            identity=nim,
            email=email,
            name=name,
            role="user"
        )

        user.set_password(
            password
        )

        db.session.add(user)

        db.session.commit()

        flash(
            "Akun berhasil dibuat. Silakan masuk.",
            "success"
        )

        return redirect(
            url_for("login")
        )

    return render_template(
        "register.html"
    )


# =========================================================
# SSO
# =========================================================

@app.route("/auth/sso")
def sso_login():

    if os.getenv(
        "SSO_ENABLED",
        "false"
    ).lower() != "true":

        flash(
            "SSO belum dikonfigurasi. Isi variabel SSO_* pada .env.",
            "error"
        )

        return redirect(
            url_for("login")
        )

    flash(
        "Endpoint SSO siap diintegrasikan dengan IdP UNDIP melalui OpenID Connect.",
        "info"
    )

    return redirect(
        url_for("login")
    )


# =========================================================
# MAP
# =========================================================

@app.route("/map")
@login_required
def map_page():

    # Hanya laporan yang sudah disetujui yang
    # ditampilkan sebagai laporan aktif di peta.
    approved = Report.query.filter(
        Report.status.in_(
            [
                "processing",
                "completed"
            ]
        )
    ).order_by(
        Report.created_at.desc()
    ).all()

    latest = Report.query.order_by(
        Report.created_at.desc()
    ).limit(6).all()

    return render_template(
        "map.html",
        approved=approved,
        latest=latest
    )


# =========================================================
# CREATE REPORT
# =========================================================

@app.route(
    "/report/new",
    methods=["GET", "POST"]
)
@login_required
def new_report():

    if request.method == "POST":

        category = request.form.get(
            "category"
        )

        damage_type = request.form.get(
            "damage_type"
        )

        description = request.form.get(
            "description",
            ""
        ).strip()

        title = request.form.get(
            "title",
            ""
        ).strip()

        lat_raw = request.form.get(
            "latitude",
            ""
        ).strip()

        lon_raw = request.form.get(
            "longitude",
            ""
        ).strip()

        # -----------------------------------------------
        # Validasi kategori
        # -----------------------------------------------

        if (
            category not in CATEGORIES
            or damage_type not in CATEGORIES[category]
        ):

            flash(
                "Kategori atau jenis kerusakan tidak valid.",
                "error"
            )

            return render_template(
                "report_form.html"
            )

        # -----------------------------------------------
        # Validasi koordinat
        # -----------------------------------------------

        try:

            lat = float(lat_raw)
            lon = float(lon_raw)

        except ValueError:

            flash(
                "Titik lokasi belum dipilih.",
                "error"
            )

            return render_template(
                "report_form.html"
            )

        # -----------------------------------------------
        # Upload foto awal
        # -----------------------------------------------

        photo_name = None

        photo = request.files.get(
            "photo"
        )

        if photo and photo.filename:

            ext = os.path.splitext(
                photo.filename
            )[1].lower()

            allowed_extensions = [
                ".jpg",
                ".jpeg",
                ".png",
                ".webp"
            ]

            if ext not in allowed_extensions:

                flash(
                    "Format foto harus JPG, JPEG, PNG, atau WEBP.",
                    "error"
                )

                return render_template(
                    "report_form.html"
                )

            photo_name = (
                f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_"
                f"{secure_filename(photo.filename)}"
            )

            path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                photo_name
            )

            photo.save(path)

        # -----------------------------------------------
        # Buat laporan
        # -----------------------------------------------

        report = Report(
            title=(
                title
                or f"{category} - {damage_type}"
            ),
            category=category,
            damage_type=damage_type,
            description=description,
            latitude=lat,
            longitude=lon,
            photo=photo_name,
            status="pending",
            user_id=current_user.id,
        )

        db.session.add(report)

        db.session.commit()

        flash(
            "Laporan dikirim dan menunggu verifikasi operator.",
            "success"
        )

        return redirect(
            url_for("history")
        )

    return render_template(
        "report_form.html"
    )


# =========================================================
# EXTRACT PHOTO GPS
# =========================================================

@app.route(
    "/report/extract-gps",
    methods=["POST"]
)
@login_required
def extract_photo_gps():

    photo = request.files.get(
        "photo"
    )

    if not photo or not photo.filename:

        return jsonify(
            {
                "ok": False,
                "message": "Foto belum dipilih."
            }
        ), 400

    temp = os.path.join(
        app.config["UPLOAD_FOLDER"],
        f"_temp_{datetime.utcnow().timestamp()}.jpg"
    )

    try:

        photo.save(temp)

        lat, lon = extract_gps(
            temp
        )

        if lat is None:

            return jsonify(
                {
                    "ok": False,
                    "message": "Foto tidak memiliki metadata GPS/EXIF."
                }
            )

        return jsonify(
            {
                "ok": True,
                "latitude": lat,
                "longitude": lon
            }
        )

    finally:

        if os.path.exists(temp):

            os.remove(temp)


# =========================================================
# HISTORY
# =========================================================

@app.route("/history")
@login_required
def history():

    q = request.args.get(
        "q",
        ""
    ).strip()

    category = request.args.get(
        "category",
        ""
    )

    status = request.args.get(
        "status",
        ""
    )

    query = Report.query

    # User biasa hanya melihat laporan miliknya
    if current_user.role != "operator":

        query = query.filter_by(
            user_id=current_user.id
        )

    # Search
    if q:

        query = query.filter(
            db.or_(
                Report.title.ilike(
                    f"%{q}%"
                ),

                Report.description.ilike(
                    f"%{q}%"
                ),

                Report.damage_type.ilike(
                    f"%{q}%"
                )
            )
        )

    # Filter kategori
    if category in CATEGORIES:

        query = query.filter_by(
            category=category
        )

    # Filter status
    valid_statuses = [
        "pending",
        "processing",
        "completed",
        "disapproved"
    ]

    if status in valid_statuses:

        query = query.filter_by(
            status=status
        )

    reports = query.order_by(
        Report.created_at.desc()
    ).all()

    return render_template(
        "history.html",
        reports=reports,
        q=q,
        selected_category=category,
        selected_status=status
    )


# =========================================================
# REPORT DETAIL
# =========================================================

@app.route(
    "/report/<int:report_id>"
)
@login_required
def report_detail(report_id):

    report = db.get_or_404(
        Report,
        report_id
    )

    # User hanya boleh melihat laporan miliknya.
    # Operator boleh melihat semua.
    # Laporan yang sedang diproses dan selesai juga
    # dapat ditampilkan.
    if (
        report.user_id != current_user.id
        and current_user.role != "operator"
    ):

        flash(
            "Anda tidak memiliki akses ke laporan ini.",
            "error"
        )

        return redirect(
            url_for("map_page")
        )

    return render_template(
        "report_detail.html",
        report=report
    )


# =========================================================
# OPERATOR DASHBOARD
# =========================================================

@app.route("/operator")
@operator_required
def operator_dashboard():

    # -----------------------------------------------
    # Menunggu verifikasi
    # -----------------------------------------------

    pending = Report.query.filter_by(
        status="pending"
    ).order_by(
        Report.created_at.asc()
    ).all()

    # -----------------------------------------------
    # Sedang diproses
    # -----------------------------------------------

    processing = Report.query.filter_by(
        status="processing"
    ).order_by(
        Report.created_at.asc()
    ).all()

    # -----------------------------------------------
    # Sudah selesai
    # -----------------------------------------------

    completed = Report.query.filter_by(
        status="completed"
    ).order_by(
        Report.created_at.desc()
    ).all()

    # -----------------------------------------------
    # Ditolak
    # -----------------------------------------------

    disapproved = Report.query.filter_by(
        status="disapproved"
    ).order_by(
        Report.created_at.desc()
    ).all()

    # -----------------------------------------------
    # Statistik
    # -----------------------------------------------

    stats = {

        "pending": Report.query.filter_by(
            status="pending"
        ).count(),

        "processing": Report.query.filter_by(
            status="processing"
        ).count(),

        "completed": Report.query.filter_by(
            status="completed"
        ).count(),

        "disapproved": Report.query.filter_by(
            status="disapproved"
        ).count(),

        "total": Report.query.count(),
    }

    return render_template(
        "operator.html",

        pending=pending,

        processing=processing,

        completed=completed,

        disapproved=disapproved,

        stats=stats
    )


# =========================================================
# OPERATOR REVIEW
# =========================================================

@app.route(
    "/operator/review/<int:report_id>",
    methods=["POST"]
)
@operator_required
def review_report(report_id):

    report = db.get_or_404(
        Report,
        report_id
    )

    decision = request.form.get(
        "decision"
    )

    reason = request.form.get(
        "reason",
        ""
    ).strip()

    # -----------------------------------------------
    # Validasi keputusan
    # -----------------------------------------------

    if decision not in [
        "approved",
        "disapproved"
    ]:

        flash(
            "Keputusan tidak valid.",
            "error"
        )

        return redirect(
            url_for("operator_dashboard")
        )

    # =================================================
    # DITOLAK
    # =================================================

    if decision == "disapproved":

        if not reason:

            flash(
                "Alasan wajib diisi saat laporan ditolak.",
                "error"
            )

            return redirect(
                url_for("operator_dashboard")
            )

        report.status = "disapproved"

        report.operator_reason = reason

        report.reviewed_at = datetime.utcnow()

        db.session.commit()

        flash(
            f"Laporan #{report.id} berhasil ditolak.",
            "success"
        )

        return redirect(
            url_for("operator_dashboard")
        )

    # =================================================
    # DISETUJUI DAN MASUK PROSES
    # =================================================

    if decision == "approved":

        # Status approved TIDAK digunakan lagi.
        # Setelah operator menyetujui, laporan langsung
        # masuk tahap processing.

        report.status = "processing"

        report.operator_reason = (
            reason
            or "Laporan telah diverifikasi dan sedang diproses."
        )

        report.reviewed_at = datetime.utcnow()

        db.session.commit()

        flash(
            f"Laporan #{report.id} masuk tahap diproses.",
            "success"
        )

        return redirect(
            url_for("operator_dashboard")
        )


# =========================================================
# OPERATOR MENYELESAIKAN LAPORAN
# =========================================================

@app.route(
    "/operator/complete/<int:report_id>",
    methods=["POST"]
)
@operator_required
def complete_report(report_id):

    report = db.get_or_404(
        Report,
        report_id
    )

    # -----------------------------------------------
    # Hanya processing yang boleh diselesaikan
    # -----------------------------------------------

    if report.status != "processing":

        flash(
            "Laporan hanya dapat diselesaikan ketika sedang diproses.",
            "error"
        )

        return redirect(
            url_for("operator_dashboard")
        )

    # -----------------------------------------------
    # Ambil keterangan
    # -----------------------------------------------

    reason = request.form.get(
        "reason",
        ""
    ).strip()

    # -----------------------------------------------
    # Ambil foto hasil perbaikan
    # -----------------------------------------------

    completion_photo = request.files.get(
        "completion_photo"
    )

    if (
        not completion_photo
        or not completion_photo.filename
    ):

        flash(
            "Foto hasil perbaikan wajib diunggah.",
            "error"
        )

        return redirect(
            url_for("operator_dashboard")
        )

    # -----------------------------------------------
    # Validasi format foto
    # -----------------------------------------------

    ext = os.path.splitext(
        completion_photo.filename
    )[1].lower()

    allowed_extensions = [
        ".jpg",
        ".jpeg",
        ".png",
        ".webp"
    ]

    if ext not in allowed_extensions:

        flash(
            "Format foto harus JPG, JPEG, PNG, atau WEBP.",
            "error"
        )

        return redirect(
            url_for("operator_dashboard")
        )

    # -----------------------------------------------
    # Buat nama file hasil perbaikan
    # -----------------------------------------------

    completion_filename = (
        f"completion_"
        f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_"
        f"{secure_filename(completion_photo.filename)}"
    )

    completion_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        completion_filename
    )

    completion_photo.save(
        completion_path
    )

    # -----------------------------------------------
    # Update laporan
    # -----------------------------------------------

    report.completion_photo = (
        completion_filename
    )

    report.status = "completed"

    report.operator_reason = (
        reason
        or "Perbaikan fasilitas telah selesai."
    )

    report.reviewed_at = datetime.utcnow()

    db.session.commit()

    flash(
        f"Laporan #{report.id} berhasil diselesaikan.",
        "success"
    )

    return redirect(
        url_for("operator_dashboard")
    )


# =========================================================
# UPLOADS
# =========================================================

@app.route(
    "/uploads/<path:filename>"
)
@login_required
def uploaded_file(filename):

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename
    )


# =========================================================
# API CATEGORIES
# =========================================================

@app.route("/api/categories")
def api_categories():

    return jsonify(
        CATEGORIES
    )


# =========================================================
# SEED DATABASE
# =========================================================

def seed():

    with app.app_context():

        # Buat tabel jika belum ada
        db.create_all()

        # Pastikan schema database lama diperbarui
        ensure_schema()

        # -------------------------------------------
        # Operator
        # -------------------------------------------

        operator_email = os.getenv(
            "OPERATOR_EMAIL",
            "operator@undip.ac.id"
        ).lower()

        operator_password = os.getenv(
            "OPERATOR_PASSWORD",
            "operator123"
        )

        op = User.query.filter_by(
            email=operator_email
        ).first()

        if not op:

            op = User(
                identity="OPERATOR",
                email=operator_email,
                name="Operator DEEPS",
                role="operator"
            )

            op.set_password(
                operator_password
            )

            db.session.add(op)

        # -------------------------------------------
        # Mahasiswa demo
        # -------------------------------------------

        demo_user = User.query.filter_by(
            identity="240001"
        ).first()

        if not demo_user:

            demo_user = User(
                identity="240001",
                email="240001@students.undip.ac.id",
                name="Mahasiswa Demo",
                role="user"
            )

            demo_user.set_password(
                "mahasiswa123"
            )

            db.session.add(
                demo_user
            )

        db.session.commit()


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    seed()

    app.run(
        debug=True
    )
