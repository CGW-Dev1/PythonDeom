from flask import Blueprint, render_template

from app.auth import admin_required, current_user, login_required

page_bp = Blueprint("pages", __name__)


@page_bp.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html", user=current_user())


@page_bp.route("/admin")
@admin_required
def admin():
    return render_template("admin.html", user=current_user())
