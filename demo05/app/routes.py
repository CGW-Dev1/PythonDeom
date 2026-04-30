from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .database import db
from .models import Listing, User
from .services.analytics import generate_all_charts, get_analytics_payload
from .services.crawler_runner import crawl_to_database, import_sample_data


main_bp = Blueprint("main", __name__)


@main_bp.context_processor
def inject_user():
    user = None
    user_id = session.get("user_id")
    if user_id:
        user = User.query.get(user_id)
    return {"current_user": user}


@main_bp.route("/")
def index():
    return render_template("index.html")


@main_bp.route("/listings")
def listings_page():
    return render_template("listings.html")


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session["user_id"] = user.id
            flash("登录成功。", "success")
            return redirect(url_for("main.index"))
        flash("用户名或密码错误。", "error")
    return render_template("login.html")


@main_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(username) < 3:
            flash("用户名至少需要 3 个字符。", "error")
        elif len(password) < 6:
            flash("密码至少需要 6 个字符。", "error")
        elif password != confirm_password:
            flash("两次输入的密码不一致。", "error")
        elif User.query.filter_by(username=username).first():
            flash("用户名已存在。", "error")
        else:
            user = User(username=username)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            session["user_id"] = user.id
            flash("注册成功。", "success")
            return redirect(url_for("main.index"))
    return render_template("register.html")


@main_bp.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("已退出登录。", "success")
    return redirect(url_for("main.index"))


@main_bp.route("/api/listings")
def api_listings():
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = request.args.get("per_page", current_app.config["PAGE_SIZE"], type=int)
    per_page = min(max(per_page, 5), 100)

    query = Listing.query
    district = request.args.get("district", "").strip()
    house_type = request.args.get("house_type", "").strip()
    min_price = request.args.get("min_price", type=float)
    max_price = request.args.get("max_price", type=float)

    if district:
        query = query.filter(Listing.district == district)
    if house_type:
        query = query.filter(Listing.house_type == house_type)
    if min_price is not None:
        query = query.filter(Listing.rent_price >= min_price)
    if max_price is not None:
        query = query.filter(Listing.rent_price <= max_price)

    pagination = query.order_by(Listing.id.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )
    return jsonify(
        {
            "items": [item.to_dict() for item in pagination.items],
            "page": page,
            "pages": pagination.pages,
            "per_page": per_page,
            "total": pagination.total,
        }
    )


@main_bp.route("/api/districts")
def api_districts():
    rows = db.session.query(Listing.district).distinct().order_by(Listing.district).all()
    return jsonify([row[0] for row in rows])


@main_bp.route("/api/house-types")
def api_house_types():
    rows = db.session.query(Listing.house_type).distinct().order_by(Listing.house_type).all()
    return jsonify([row[0] for row in rows])


@main_bp.route("/api/stats")
def api_stats():
    return jsonify(get_analytics_payload())


@main_bp.route("/api/charts")
def api_charts():
    charts = generate_all_charts(
        current_app.config["CHART_OUTPUT_DIR"],
        current_app.config["CHART_URL_PREFIX"],
    )
    return jsonify(charts)


@main_bp.route("/api/crawl", methods=["POST"])
def api_crawl():
    data = request.get_json(silent=True) or request.form
    platform = data.get("platform", "sample")
    city = data.get("city", "bj")
    max_pages = int(data.get("max_pages", 3))

    if platform == "sample":
        result = import_sample_data(clear=False)
    else:
        platforms = [platform] if isinstance(platform, str) else list(platform)
        result = crawl_to_database(platforms=platforms, city=city, max_pages=max_pages)
    return jsonify(result)
