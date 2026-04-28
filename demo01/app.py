import os
import re
from datetime import datetime, timedelta, timezone
from functools import wraps
from html import escape
from pathlib import Path
from secrets import token_urlsafe

import pymysql
from flask import (
    Flask,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from markupsafe import Markup
from pymysql.cursors import DictCursor
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = BASE_DIR / "schema.sql"
PER_PAGE = 8


HOME_TABS = [
    ("all", "首页"),
    ("featured", "精华"),
    ("candidate", "候选"),
    ("following", "关注"),
    ("news", "新闻"),
]


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("BLOG_SECRET_KEY", "dev-secret-change-me"),
        MYSQL_HOST=os.environ.get("BLOG_MYSQL_HOST", "127.0.0.1"),
        MYSQL_PORT=int(os.environ.get("BLOG_MYSQL_PORT", "3306")),
        MYSQL_USER=os.environ.get("BLOG_MYSQL_USER", "root"),
        MYSQL_PASSWORD=os.environ.get("BLOG_MYSQL_PASSWORD", "123456"),
        MYSQL_DATABASE=os.environ.get("BLOG_MYSQL_DATABASE", "python_blog"),
        MYSQL_CHARSET=os.environ.get("BLOG_MYSQL_CHARSET", "utf8mb4"),
        ADMIN_USERNAME=os.environ.get("BLOG_ADMIN_USERNAME", "admin"),
        ADMIN_PASSWORD=os.environ.get("BLOG_ADMIN_PASSWORD", "admin123"),
        ADMIN_DISPLAY_NAME=os.environ.get("BLOG_ADMIN_DISPLAY_NAME", "博客管理员"),
    )

    app.teardown_appcontext(close_db)
    app.context_processor(inject_template_helpers)
    register_routes(app)

    with app.app_context():
        try:
            ensure_database()
            init_db()
            ensure_schema_migrations()
            ensure_admin_user()
            ensure_seed_data()
        except pymysql.MySQLError as exc:
            raise RuntimeError(
                "无法连接或初始化本地 MySQL。请设置 BLOG_MYSQL_HOST、BLOG_MYSQL_PORT、"
                "BLOG_MYSQL_USER、BLOG_MYSQL_PASSWORD、BLOG_MYSQL_DATABASE 后再启动。"
            ) from exc

    return app


def db_config(include_database=True):
    config = current_app.config
    kwargs = {
        "host": config["MYSQL_HOST"],
        "port": config["MYSQL_PORT"],
        "user": config["MYSQL_USER"],
        "password": config["MYSQL_PASSWORD"],
        "charset": config["MYSQL_CHARSET"],
        "cursorclass": DictCursor,
        "autocommit": False,
    }
    if include_database:
        kwargs["database"] = config["MYSQL_DATABASE"]
    return kwargs


def quote_identifier(identifier):
    if not re.fullmatch(r"[A-Za-z0-9_]+", identifier):
        raise RuntimeError("MySQL database name may only contain letters, numbers, and underscores.")
    return f"`{identifier}`"


def ensure_database():
    database = current_app.config["MYSQL_DATABASE"]
    with pymysql.connect(**db_config(include_database=False)) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS {quote_identifier(database)} "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()


def get_db():
    if "db" not in g:
        g.db = pymysql.connect(**db_config(include_database=True))
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def fetch_one(sql, params=None):
    with get_db().cursor() as cursor:
        cursor.execute(sql, params or ())
        return cursor.fetchone()


def fetch_all(sql, params=None):
    with get_db().cursor() as cursor:
        cursor.execute(sql, params or ())
        return cursor.fetchall()


def execute(sql, params=None):
    with get_db().cursor() as cursor:
        cursor.execute(sql, params or ())
        return cursor.lastrowid


def init_db():
    statements = [part.strip() for part in SCHEMA_PATH.read_text(encoding="utf-8").split(";")]
    for statement in statements:
        if statement:
            execute(statement)
    get_db().commit()


def ensure_schema_migrations():
    if not column_exists("users", "role"):
        execute("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'author' AFTER password_hash")
    get_db().commit()


def column_exists(table, column):
    row = fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
        """,
        (table, column),
    )
    return row["count"] > 0


def ensure_admin_user():
    username = current_app.config["ADMIN_USERNAME"]
    password = current_app.config["ADMIN_PASSWORD"]
    display_name = current_app.config["ADMIN_DISPLAY_NAME"]
    existing = fetch_one("SELECT id FROM users WHERE username = %s", (username,))
    if existing:
        execute(
            "UPDATE users SET role = 'admin', display_name = %s WHERE id = %s",
            (display_name, existing["id"]),
        )
        get_db().commit()
        return
    execute(
        """
        INSERT INTO users (username, display_name, password_hash, role, bio, avatar_color)
        VALUES (%s, %s, %s, 'admin', %s, %s)
        """,
        (
            username,
            display_name,
            generate_password_hash(password),
            "管理文章、评论和站点内容。",
            "#146c5f",
        ),
    )
    get_db().commit()


def ensure_seed_data():
    count = fetch_one("SELECT COUNT(*) AS count FROM posts")["count"]
    if count:
        return

    admin = fetch_one("SELECT id FROM users WHERE username = %s", (current_app.config["ADMIN_USERNAME"],))
    authors = {
        "admin": admin["id"],
        "backend": ensure_demo_user("backend_notes", "后端笔记", "#2f5d8c", "关注 Python、服务端工程和数据库。"),
        "frontend": ensure_demo_user("frontend_lab", "前端实验室", "#9a4d24", "记录界面设计、交互体验和工程实践。"),
    }
    categories = {
        name: ensure_category(name, slug)
        for name, slug in [
            ("后端开发", "backend"),
            ("前端设计", "frontend"),
            ("数据库", "database"),
            ("人工智能", "ai"),
            ("架构", "architecture"),
            ("生活随笔", "life"),
            ("新闻", "news"),
        ]
    }

    posts = [
        {
            "author": "backend",
            "category": "后端开发",
            "title": "用 Flask 打造可维护的个人博客平台",
            "summary": "从路由、模板、数据库到后台管理，梳理一个博客系统应有的工程骨架。",
            "content": "一个博客系统不只是展示文章，它还需要稳定的数据结构、清晰的后台入口和可持续扩展的页面组织。\n\n这个项目使用 Flask 负责 Web 层，MySQL 负责持久化存储。文章、评论、作者、分类和统计数据都在数据库里维护，后续可以继续接入上传、权限和全文检索。\n\n设计时最重要的是先把内容流跑顺：列表页负责发现，详情页负责阅读，后台负责生产内容。",
            "tags": "Python, Flask, MySQL",
            "featured": 1,
            "views": 1480,
            "recommends": 76,
            "hours_ago": 5,
        },
        {
            "author": "frontend",
            "category": "前端设计",
            "title": "门户式博客首页的信息密度怎么拿捏",
            "summary": "首页既要能扫读，又不能堆成一堵墙，布局的关键是主次关系。",
            "content": "门户式博客首页通常有三块核心区域：导航、文章流和侧边栏。\n\n导航帮助用户切换频道，文章流承载主要阅读行为，侧边栏提供排行榜、分类、标签和最近评论。三者一起工作，用户才能快速判断这里是否有值得继续看的内容。\n\n这个版本把首页从单列卡片升级成两栏布局，并加入分类、统计、推荐和排行。",
            "tags": "前端, UI, 信息架构",
            "featured": 1,
            "views": 936,
            "recommends": 54,
            "hours_ago": 9,
        },
        {
            "author": "backend",
            "category": "数据库",
            "title": "SQLite 到 MySQL：本地开发数据库切换记录",
            "summary": "当数据需要更接近真实部署环境时，MySQL 会比文件数据库更适合演示后台系统。",
            "content": "SQLite 非常适合入门和单文件演示，但如果要模拟多人博客平台，本地 MySQL 更符合实际开发习惯。\n\n切换时要注意三件事：占位符从问号变成百分号语法，自增主键和文本字段类型需要改成 MySQL 方言，应用启动时最好能自动创建库和表。\n\n本项目使用 PyMySQL 直连本地 MySQL，并通过环境变量配置账号、密码和数据库名。",
            "tags": "MySQL, SQLite, 数据库",
            "featured": 0,
            "views": 725,
            "recommends": 38,
            "hours_ago": 14,
        },
        {
            "author": "admin",
            "category": "架构",
            "title": "博客系统后台需要哪些最小功能",
            "summary": "文章管理、评论管理、发布状态和内容统计，是后台能用起来的底线。",
            "content": "后台不一定一开始就复杂，但必须覆盖最常用的编辑流程。\n\n管理员需要能创建文章、编辑文章、保存草稿、标记推荐、选择分类，并且能看见评论数量和更新时间。评论区则需要基础的审核与删除能力。\n\n这些能力并不花哨，却决定了系统是否可以长期维护。",
            "tags": "后台, 架构, 内容管理",
            "featured": 1,
            "views": 1142,
            "recommends": 69,
            "hours_ago": 22,
        },
        {
            "author": "frontend",
            "category": "人工智能",
            "title": "把 AI 辅助写作接进博客的几个边界",
            "summary": "AI 可以辅助选题、摘要和校对，但作者视角仍然是内容的核心。",
            "content": "博客的价值来自持续的个人经验沉淀。AI 可以帮助整理提纲、检查错别字、生成摘要，但不应该替代作者的判断。\n\n更好的方式是把 AI 看成编辑助手：它能提示遗漏、压缩表达、生成不同标题版本，最终发布什么仍由作者决定。\n\n未来这个项目可以加入草稿辅助摘要和标签建议功能。",
            "tags": "AI, 写作, 博客",
            "featured": 0,
            "views": 588,
            "recommends": 25,
            "hours_ago": 30,
        },
        {
            "author": "backend",
            "category": "新闻",
            "title": "站点更新：MySQL 版本的博客系统上线",
            "summary": "数据层已经切换到 MySQL，首页也升级为博客门户式布局。",
            "content": "本次更新把原来的轻量博客改造成更接近技术社区首页的结构。\n\n你现在可以在首页看到分类导航、文章统计、推荐排行和标签集合。后台文章表单也新增了分类和推荐开关。\n\n下一步可以继续加入用户注册、图片上传、文章归档和全文搜索。",
            "tags": "新闻, 更新, MySQL",
            "featured": 1,
            "views": 1620,
            "recommends": 91,
            "hours_ago": 2,
        },
        {
            "author": "admin",
            "category": "生活随笔",
            "title": "写博客这件小事，贵在能回头看见自己",
            "summary": "技术博客不只是记录方案，也是记录当时做判断的上下文。",
            "content": "很多问题在解决之后会变得理所当然，但当时踩过的坑、取舍和上下文很快就会消失。\n\n博客的好处是把这些思考保存下来。几个月之后回头看，文章会提醒你当初为什么这样设计，也会暴露哪些判断已经过时。\n\n这也是我喜欢把项目做成博客系统的原因：它天然鼓励整理和复盘。",
            "tags": "随笔, 复盘, 成长",
            "featured": 0,
            "views": 403,
            "recommends": 18,
            "hours_ago": 40,
        },
        {
            "author": "frontend",
            "category": "前端设计",
            "title": "技术社区的侧边栏应该放什么",
            "summary": "排行榜、分类、标签和最新评论，比装饰性内容更能帮助用户继续探索。",
            "content": "侧边栏的价值在于提供下一步行动。\n\n如果用户正在阅读文章，侧边栏可以展示同类分类、热门推荐和最近评论。用户不需要理解复杂规则，只要看到清晰的标题和数字，就能继续浏览。\n\n因此侧边栏不应该喧宾夺主，而要稳定、克制、可扫读。",
            "tags": "侧边栏, 设计, 社区",
            "featured": 0,
            "views": 812,
            "recommends": 47,
            "hours_ago": 52,
        },
    ]

    for item in posts:
        insert_seed_post(item, authors, categories)

    first_post = fetch_one("SELECT id FROM posts ORDER BY id LIMIT 1")
    if first_post:
        execute(
            "INSERT INTO comments (post_id, author, body, is_approved) VALUES (%s, %s, %s, 1)",
            (first_post["id"], "读者小林", "首页和后台都比上一版完整很多，适合作为课程项目继续扩展。"),
        )
        execute(
            "INSERT INTO comments (post_id, author, body, is_approved) VALUES (%s, %s, %s, 1)",
            (first_post["id"], "码上见", "MySQL 配置说明很实用，后续可以加一个部署文档。"),
        )

    get_db().commit()


def ensure_demo_user(username, display_name, color, bio):
    row = fetch_one("SELECT id FROM users WHERE username = %s", (username,))
    if row:
        return row["id"]
    user_id = execute(
        """
        INSERT INTO users (username, display_name, password_hash, role, bio, avatar_color)
        VALUES (%s, %s, %s, 'author', %s, %s)
        """,
        (username, display_name, generate_password_hash(token_urlsafe(18)), bio, color),
    )
    return user_id


def ensure_category(name, slug):
    row = fetch_one("SELECT id FROM categories WHERE slug = %s", (slug,))
    if row:
        return row["id"]
    return execute("INSERT INTO categories (name, slug) VALUES (%s, %s)", (name, slug))


def insert_seed_post(item, authors, categories):
    created_at = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
    created_at = created_at - timedelta(hours=item["hours_ago"])
    execute(
        """
        INSERT INTO posts
            (user_id, category_id, title, slug, summary, content, tags, is_published,
             is_featured, view_count, recommend_count, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 1, %s, %s, %s, %s, %s)
        """,
        (
            authors[item["author"]],
            categories[item["category"]],
            item["title"],
            unique_slug(slugify(item["title"])),
            item["summary"],
            item["content"],
            normalize_tags(item["tags"]),
            item["featured"],
            item["views"],
            item["recommends"],
            created_at,
            created_at,
        ),
    )


def register_routes(app):
    @app.route("/")
    def index():
        filters = parse_listing_filters()
        listing = get_post_listing(filters)
        sidebar = get_sidebar_data()
        return render_template(
            "index.html",
            posts=listing["posts"],
            total=listing["total"],
            pages=listing["pages"],
            filters=filters,
            tabs=HOME_TABS,
            sidebar=sidebar,
            categories=get_categories(),
        )

    @app.route("/category/<slug>")
    def category(slug):
        category_row = fetch_one("SELECT * FROM categories WHERE slug = %s", (slug,))
        if category_row is None:
            abort(404)
        filters = parse_listing_filters()
        filters["category"] = slug
        listing = get_post_listing(filters)
        sidebar = get_sidebar_data()
        return render_template(
            "index.html",
            posts=listing["posts"],
            total=listing["total"],
            pages=listing["pages"],
            filters=filters,
            tabs=HOME_TABS,
            sidebar=sidebar,
            categories=get_categories(),
            current_category=category_row,
        )

    @app.route("/author/<username>")
    def author(username):
        author_row = fetch_one("SELECT * FROM users WHERE username = %s", (username,))
        if author_row is None:
            abort(404)
        filters = parse_listing_filters()
        filters["author"] = username
        listing = get_post_listing(filters)
        return render_template(
            "author.html",
            author=author_row,
            posts=listing["posts"],
            total=listing["total"],
            pages=listing["pages"],
            filters=filters,
            sidebar=get_sidebar_data(),
        )

    @app.route("/post/<slug>", methods=("GET", "POST"))
    def post_detail(slug):
        post = fetch_one(
            """
            SELECT p.*, u.username, u.display_name, u.bio, u.avatar_color,
                   c.name AS category_name, c.slug AS category_slug,
                   (SELECT COUNT(*) FROM comments cm
                    WHERE cm.post_id = p.id AND cm.is_approved = 1) AS comment_count
            FROM posts p
            JOIN users u ON u.id = p.user_id
            LEFT JOIN categories c ON c.id = p.category_id
            WHERE p.slug = %s AND p.is_published = 1
            """,
            (slug,),
        )
        if post is None:
            abort(404)

        if request.method == "POST":
            validate_csrf()
            author_name = request.form.get("author", "").strip()
            body = request.form.get("body", "").strip()
            if not author_name or not body:
                flash("请填写昵称和评论内容。", "error")
            elif len(author_name) > 40:
                flash("昵称不能超过 40 个字符。", "error")
            else:
                execute(
                    "INSERT INTO comments (post_id, author, body, is_approved) VALUES (%s, %s, %s, 1)",
                    (post["id"], author_name, body),
                )
                get_db().commit()
                flash("评论发布成功。", "success")
                return redirect(url_for("post_detail", slug=slug) + "#comments")

        execute("UPDATE posts SET view_count = view_count + 1 WHERE id = %s", (post["id"],))
        get_db().commit()
        post["view_count"] += 1

        comments = fetch_all(
            """
            SELECT * FROM comments
            WHERE post_id = %s AND is_approved = 1
            ORDER BY created_at DESC
            """,
            (post["id"],),
        )
        related_posts = fetch_all(
            """
            SELECT id, title, slug
            FROM posts
            WHERE is_published = 1 AND id <> %s AND category_id <=> %s
            ORDER BY recommend_count DESC, created_at DESC
            LIMIT 5
            """,
            (post["id"], post["category_id"]),
        )
        return render_template(
            "post_detail.html",
            post=post,
            comments=comments,
            related_posts=related_posts,
            sidebar=get_sidebar_data(),
        )

    @app.route("/post/<int:post_id>/recommend", methods=("POST",))
    def recommend_post(post_id):
        validate_csrf()
        post = fetch_one("SELECT slug FROM posts WHERE id = %s AND is_published = 1", (post_id,))
        if post is None:
            abort(404)
        execute("UPDATE posts SET recommend_count = recommend_count + 1 WHERE id = %s", (post_id,))
        get_db().commit()
        flash("已推荐这篇文章。", "success")
        return redirect(url_for("post_detail", slug=post["slug"]))

    @app.route("/register", methods=("GET", "POST"))
    def register():
        if request.method == "POST":
            validate_csrf()
            username = request.form.get("username", "").strip()
            display_name = request.form.get("display_name", "").strip()
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")
            bio = request.form.get("bio", "").strip()
            avatar_color = request.form.get("avatar_color", "#1d6fb8").strip()

            if not valid_username(username):
                flash("用户名只能包含字母、数字和下划线，长度 3-30 位。", "error")
            elif len(display_name) < 2 or len(display_name) > 30:
                flash("昵称长度需要在 2-30 个字符之间。", "error")
            elif len(password) < 6:
                flash("密码至少需要 6 位。", "error")
            elif password != confirm_password:
                flash("两次输入的密码不一致。", "error")
            elif fetch_one("SELECT id FROM users WHERE username = %s", (username,)):
                flash("这个用户名已经被占用。", "error")
            else:
                user_id = execute(
                    """
                    INSERT INTO users
                        (username, display_name, password_hash, role, bio, avatar_color)
                    VALUES (%s, %s, %s, 'author', %s, %s)
                    """,
                    (
                        username,
                        display_name,
                        generate_password_hash(password),
                        bio[:255],
                        normalize_avatar_color(avatar_color),
                    ),
                )
                get_db().commit()
                session.clear()
                session["user_id"] = user_id
                session["username"] = username
                session["display_name"] = display_name
                session["role"] = "author"
                flash("注册成功，欢迎来到 PyBlog 园地。", "success")
                return redirect(url_for("dashboard"))

        return render_template("register.html")

    @app.route("/admin/login", methods=("GET", "POST"))
    def login():
        if request.method == "POST":
            validate_csrf()
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user = fetch_one("SELECT * FROM users WHERE username = %s", (username,))
            if user and check_password_hash(user["password_hash"], password):
                session.clear()
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                session["display_name"] = user["display_name"]
                session["role"] = user.get("role", "author")
                flash("登录成功。", "success")
                return redirect(url_for("dashboard"))
            flash("用户名或密码不正确。", "error")
        return render_template("login.html")

    @app.route("/profile", methods=("GET", "POST"))
    @login_required
    def profile():
        user = fetch_one("SELECT * FROM users WHERE id = %s", (session["user_id"],))
        if user is None:
            session.clear()
            flash("账号不存在，请重新登录。", "error")
            return redirect(url_for("login"))

        if request.method == "POST":
            validate_csrf()
            display_name = request.form.get("display_name", "").strip()
            bio = request.form.get("bio", "").strip()
            avatar_color = normalize_avatar_color(request.form.get("avatar_color", "#1d6fb8"))
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")

            if len(display_name) < 2 or len(display_name) > 30:
                flash("昵称长度需要在 2-30 个字符之间。", "error")
            elif new_password and not check_password_hash(user["password_hash"], current_password):
                flash("修改密码前请填写正确的当前密码。", "error")
            elif new_password and len(new_password) < 6:
                flash("新密码至少需要 6 位。", "error")
            elif new_password and new_password != confirm_password:
                flash("两次输入的新密码不一致。", "error")
            else:
                if new_password:
                    execute(
                        """
                        UPDATE users
                        SET display_name = %s, bio = %s, avatar_color = %s, password_hash = %s
                        WHERE id = %s
                        """,
                        (
                            display_name,
                            bio[:255],
                            avatar_color,
                            generate_password_hash(new_password),
                            session["user_id"],
                        ),
                    )
                else:
                    execute(
                        "UPDATE users SET display_name = %s, bio = %s, avatar_color = %s WHERE id = %s",
                        (display_name, bio[:255], avatar_color, session["user_id"]),
                    )
                get_db().commit()
                session["display_name"] = display_name
                flash("个人资料已更新。", "success")
                return redirect(url_for("profile"))

        return render_template("profile.html", user=user)

    @app.route("/admin/logout", methods=("POST",))
    @login_required
    def logout():
        validate_csrf()
        session.clear()
        flash("已退出登录。", "success")
        return redirect(url_for("index"))

    @app.route("/admin")
    @login_required
    def dashboard():
        stats = get_admin_stats()
        where = ""
        params = []
        if not is_admin():
            where = "WHERE p.user_id = %s"
            params.append(session["user_id"])
        posts = fetch_all(
            f"""
            SELECT p.*, c.name AS category_name,
                   (SELECT COUNT(*) FROM comments cm WHERE cm.post_id = p.id) AS comment_count
            FROM posts p
            LEFT JOIN categories c ON c.id = p.category_id
            {where}
            ORDER BY p.updated_at DESC
            """,
            params,
        )
        return render_template("dashboard.html", posts=posts, stats=stats)

    @app.route("/admin/comments")
    @login_required
    def admin_comments():
        where = ""
        params = []
        if not is_admin():
            where = "WHERE p.user_id = %s"
            params.append(session["user_id"])
        comments = fetch_all(
            f"""
            SELECT cm.*, p.title AS post_title, p.slug AS post_slug
            FROM comments cm
            JOIN posts p ON p.id = cm.post_id
            {where}
            ORDER BY cm.created_at DESC
            LIMIT 80
            """,
            params,
        )
        return render_template("comments_admin.html", comments=comments)

    @app.route("/admin/comments/<int:comment_id>/toggle", methods=("POST",))
    @login_required
    def toggle_comment(comment_id):
        validate_csrf()
        if get_comment_for_management(comment_id) is None:
            abort(404)
        execute(
            "UPDATE comments SET is_approved = IF(is_approved = 1, 0, 1) WHERE id = %s",
            (comment_id,),
        )
        get_db().commit()
        flash("评论状态已更新。", "success")
        return redirect(url_for("admin_comments"))

    @app.route("/admin/comments/<int:comment_id>/delete", methods=("POST",))
    @login_required
    def delete_comment(comment_id):
        validate_csrf()
        if get_comment_for_management(comment_id) is None:
            abort(404)
        execute("DELETE FROM comments WHERE id = %s", (comment_id,))
        get_db().commit()
        flash("评论已删除。", "success")
        return redirect(url_for("admin_comments"))

    @app.route("/admin/posts/new", methods=("GET", "POST"))
    @login_required
    def create_post():
        if request.method == "POST":
            return save_post()
        post = empty_post()
        return render_template(
            "post_form.html", post=post, action="新建文章", categories=get_categories()
        )

    @app.route("/admin/posts/<int:post_id>/edit", methods=("GET", "POST"))
    @login_required
    def edit_post(post_id):
        post = fetch_one("SELECT * FROM posts WHERE id = %s", (post_id,))
        if post is None or not can_manage_post(post):
            abort(404)
        if request.method == "POST":
            return save_post(post_id=post_id)
        return render_template(
            "post_form.html", post=post, action="编辑文章", categories=get_categories()
        )

    @app.route("/admin/posts/<int:post_id>/delete", methods=("POST",))
    @login_required
    def delete_post(post_id):
        validate_csrf()
        post = fetch_one("SELECT * FROM posts WHERE id = %s", (post_id,))
        if post is None or not can_manage_post(post):
            abort(404)
        execute("DELETE FROM posts WHERE id = %s", (post_id,))
        get_db().commit()
        flash("文章已删除。", "success")
        return redirect(url_for("dashboard"))

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("error.html", code=404, message="页面不存在"), 404

    @app.errorhandler(400)
    def bad_request(_error):
        return render_template("error.html", code=400, message="请求无效"), 400


def parse_listing_filters():
    page = request.args.get("page", "1")
    try:
        page = max(1, int(page))
    except ValueError:
        page = 1
    tab = request.args.get("tab", "all")
    if tab not in {key for key, _label in HOME_TABS}:
        tab = "all"
    return {
        "q": request.args.get("q", "").strip(),
        "tag": request.args.get("tag", "").strip(),
        "tab": tab,
        "page": page,
        "category": request.args.get("category", "").strip(),
        "author": request.args.get("author", "").strip(),
    }


def get_post_listing(filters):
    where = ["p.is_published = 1"]
    params = []
    if filters["q"]:
        where.append("(p.title LIKE %s OR p.summary LIKE %s OR p.content LIKE %s)")
        needle = f"%{filters['q']}%"
        params.extend([needle, needle, needle])
    if filters["tag"]:
        where.append("p.tags LIKE %s")
        params.append(f"%{filters['tag']}%")
    if filters["category"]:
        where.append("c.slug = %s")
        params.append(filters["category"])
    if filters["author"]:
        where.append("u.username = %s")
        params.append(filters["author"])
    if filters["tab"] == "featured":
        where.append("p.is_featured = 1")
    elif filters["tab"] == "news":
        where.append("c.slug = 'news'")
    elif filters["tab"] == "following":
        where.append("p.recommend_count >= 30")

    order_by = {
        "all": "p.created_at DESC",
        "featured": "p.recommend_count DESC, p.created_at DESC",
        "candidate": "comment_count DESC, p.created_at DESC",
        "following": "p.recommend_count DESC, p.view_count DESC",
        "news": "p.created_at DESC",
    }[filters["tab"]]

    base_from = """
        FROM posts p
        JOIN users u ON u.id = p.user_id
        LEFT JOIN categories c ON c.id = p.category_id
        WHERE {where_sql}
    """.format(where_sql=" AND ".join(where))

    total = fetch_one(f"SELECT COUNT(*) AS count {base_from}", params)["count"]
    offset = (filters["page"] - 1) * PER_PAGE
    posts = fetch_all(
        f"""
        SELECT p.*, u.username, u.display_name, u.avatar_color,
               c.name AS category_name, c.slug AS category_slug,
               (SELECT COUNT(*) FROM comments cm
                WHERE cm.post_id = p.id AND cm.is_approved = 1) AS comment_count
        {base_from}
        ORDER BY {order_by}
        LIMIT %s OFFSET %s
        """,
        params + [PER_PAGE, offset],
    )
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    return {"posts": posts, "total": total, "pages": pages}


def get_sidebar_data():
    return {
        "featured": fetch_all(
            """
            SELECT title, slug, recommend_count
            FROM posts
            WHERE is_published = 1
            ORDER BY recommend_count DESC, created_at DESC
            LIMIT 8
            """
        ),
        "most_read": fetch_all(
            """
            SELECT title, slug, view_count
            FROM posts
            WHERE is_published = 1
            ORDER BY view_count DESC, created_at DESC
            LIMIT 8
            """
        ),
        "recent_comments": fetch_all(
            """
            SELECT cm.author, cm.body, p.title AS post_title, p.slug AS post_slug
            FROM comments cm
            JOIN posts p ON p.id = cm.post_id
            WHERE cm.is_approved = 1 AND p.is_published = 1
            ORDER BY cm.created_at DESC
            LIMIT 5
            """
        ),
        "tags": get_all_tags(),
        "categories": get_categories_with_counts(),
    }


def get_admin_stats():
    if is_admin():
        return {
            "posts": fetch_one("SELECT COUNT(*) AS count FROM posts")["count"],
            "published": fetch_one("SELECT COUNT(*) AS count FROM posts WHERE is_published = 1")["count"],
            "comments": fetch_one("SELECT COUNT(*) AS count FROM comments")["count"],
            "views": fetch_one("SELECT COALESCE(SUM(view_count), 0) AS count FROM posts")["count"],
        }
    params = (session["user_id"],)
    return {
        "posts": fetch_one("SELECT COUNT(*) AS count FROM posts WHERE user_id = %s", params)["count"],
        "published": fetch_one(
            "SELECT COUNT(*) AS count FROM posts WHERE user_id = %s AND is_published = 1",
            params,
        )["count"],
        "comments": fetch_one(
            """
            SELECT COUNT(*) AS count
            FROM comments cm
            JOIN posts p ON p.id = cm.post_id
            WHERE p.user_id = %s
            """,
            params,
        )["count"],
        "views": fetch_one("SELECT COALESCE(SUM(view_count), 0) AS count FROM posts WHERE user_id = %s", params)["count"],
    }


def is_admin():
    return session.get("role") == "admin"


def can_manage_post(post):
    return is_admin() or post["user_id"] == session.get("user_id")


def get_comment_for_management(comment_id):
    params = [comment_id]
    owner_check = ""
    if not is_admin():
        owner_check = "AND p.user_id = %s"
        params.append(session["user_id"])
    return fetch_one(
        f"""
        SELECT cm.id
        FROM comments cm
        JOIN posts p ON p.id = cm.post_id
        WHERE cm.id = %s {owner_check}
        """,
        params,
    )


def valid_username(username):
    return bool(re.fullmatch(r"[A-Za-z0-9_]{3,30}", username))


def normalize_avatar_color(value):
    value = value.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return value.lower()
    return "#1d6fb8"


def save_post(post_id=None):
    validate_csrf()
    if post_id:
        existing = fetch_one("SELECT * FROM posts WHERE id = %s", (post_id,))
        if existing is None or not can_manage_post(existing):
            abort(404)

    title = request.form.get("title", "").strip()
    summary = request.form.get("summary", "").strip()
    content = request.form.get("content", "").strip()
    tags = normalize_tags(request.form.get("tags", ""))
    category_id = request.form.get("category_id") or None
    is_published = 1 if request.form.get("is_published") == "on" else 0
    is_featured = 1 if request.form.get("is_featured") == "on" else 0

    if not title or not content:
        flash("标题和正文不能为空。", "error")
        post = form_post(post_id, title, summary, content, tags, category_id, is_published, is_featured)
        return render_template(
            "post_form.html",
            post=post,
            action="编辑文章" if post_id else "新建文章",
            categories=get_categories(),
        )

    db = get_db()
    base_slug = slugify(title)
    slug = unique_slug(base_slug, post_id)
    summary = summary or summarize(content)

    if post_id:
        execute(
            """
            UPDATE posts
            SET title = %s, slug = %s, summary = %s, content = %s, tags = %s,
                category_id = %s, is_published = %s, is_featured = %s
            WHERE id = %s
            """,
            (title, slug, summary, content, tags, category_id, is_published, is_featured, post_id),
        )
        flash("文章已更新。", "success")
    else:
        execute(
            """
            INSERT INTO posts
                (user_id, category_id, title, slug, summary, content, tags,
                 is_published, is_featured, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            """,
            (
                session["user_id"],
                category_id,
                title,
                slug,
                summary,
                content,
                tags,
                is_published,
                is_featured,
            ),
        )
        flash("文章已创建。", "success")
    db.commit()
    return redirect(url_for("dashboard"))


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if session.get("user_id") is None:
            flash("请先登录后台。", "error")
            return redirect(url_for("login"))
        return view(**kwargs)

    return wrapped_view


def inject_template_helpers():
    return {
        "csrf_token": csrf_token,
        "format_date": format_date,
        "render_content": render_content,
        "split_tags": split_tags,
        "active_query": active_query,
        "truncate_text": truncate_text,
        "is_admin": is_admin,
    }


def csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def validate_csrf():
    token = session.get("_csrf_token")
    submitted = request.form.get("_csrf_token")
    if not token or not submitted or token != submitted:
        abort(400)


def slugify(value):
    value = value.strip().lower()
    value = re.sub(r"[^\w\u4e00-\u9fff]+", "-", value, flags=re.UNICODE)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "post"


def unique_slug(base_slug, current_post_id=None):
    slug = base_slug
    counter = 2
    while True:
        row = fetch_one("SELECT id FROM posts WHERE slug = %s", (slug,))
        if row is None or row["id"] == current_post_id:
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1


def normalize_tags(raw_tags):
    seen = []
    for tag in re.split(r"[,，\s]+", raw_tags.strip()):
        clean = tag.strip()
        if clean and clean not in seen:
            seen.append(clean)
    return ", ".join(seen)


def split_tags(raw_tags):
    if not raw_tags:
        return []
    return [tag.strip() for tag in raw_tags.split(",") if tag.strip()]


def get_all_tags():
    rows = fetch_all("SELECT tags FROM posts WHERE is_published = 1")
    tags = []
    for row in rows:
        for tag in split_tags(row["tags"]):
            if tag not in tags:
                tags.append(tag)
    return sorted(tags, key=str.lower)


def get_categories():
    return fetch_all("SELECT * FROM categories ORDER BY sort_order ASC, name ASC")


def get_categories_with_counts():
    return fetch_all(
        """
        SELECT c.*, COUNT(p.id) AS post_count
        FROM categories c
        LEFT JOIN posts p ON p.category_id = c.id AND p.is_published = 1
        GROUP BY c.id
        ORDER BY c.sort_order ASC, c.name ASC
        """
    )


def render_content(content):
    paragraphs = []
    for block in content.split("\n\n"):
        lines = [escape(line) for line in block.strip().splitlines()]
        if lines:
            paragraphs.append(f"<p>{'<br>'.join(lines)}</p>")
    return Markup("\n".join(paragraphs))


def format_date(value):
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return str(value)


def active_query(**updates):
    args = request.args.to_dict()
    for key, value in updates.items():
        if value is None or value == "":
            args.pop(key, None)
        else:
            args[key] = value
    if "page" not in updates:
        args.pop("page", None)
    return args


def summarize(content, length=140):
    clean = re.sub(r"\s+", " ", content).strip()
    return truncate_text(clean, length)


def truncate_text(value, length=80):
    if not value:
        return ""
    return value if len(value) <= length else value[:length].rstrip() + "..."


def empty_post():
    return {
        "id": None,
        "title": "",
        "summary": "",
        "content": "",
        "tags": "",
        "category_id": None,
        "is_published": 1,
        "is_featured": 0,
    }


def form_post(post_id, title, summary, content, tags, category_id, is_published, is_featured):
    return {
        "id": post_id,
        "title": title,
        "summary": summary,
        "content": content,
        "tags": tags,
        "category_id": category_id,
        "is_published": is_published,
        "is_featured": is_featured,
    }


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
