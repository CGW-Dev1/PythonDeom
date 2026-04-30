from pathlib import Path

from .config import Config


def create_app(config_object=None):
    from flask import Flask

    from .database import db

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object or Config)

    Path(app.config["CHART_OUTPUT_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["LOG_DIR"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)

    from .routes import main_bp

    app.register_blueprint(main_bp)
    register_cli_commands(app)

    with app.app_context():
        db.create_all()

    return app


def register_cli_commands(app):
    import click

    from .services.analytics import generate_all_charts
    from .services.crawler_runner import crawl_to_database, import_sample_data

    @app.cli.command("seed")
    @click.option("--clear", is_flag=True, help="先清空房源表，再导入演示数据。")
    def seed_command(clear):
        """导入演示房源数据。"""
        result = import_sample_data(clear=clear)
        click.echo(f"导入完成：新增 {result['inserted']} 条，跳过 {result['skipped']} 条。")

    @app.cli.command("crawl")
    @click.option("--platform", default="sample", help="sample、58 或 fang。")
    @click.option("--city", default="bj", help="城市简写，例如 bj、sh、gz、sz。")
    @click.option("--pages", default=3, type=int, help="爬取页数。")
    def crawl_command(platform, city, pages):
        """启动一次房源采集并入库。"""
        if platform == "sample":
            result = import_sample_data(clear=False)
        else:
            result = crawl_to_database(platforms=[platform], city=city, max_pages=pages)
        click.echo(result)

    @app.cli.command("charts")
    def charts_command():
        """重新生成 Matplotlib 图表。"""
        result = generate_all_charts(
            app.config["CHART_OUTPUT_DIR"],
            app.config["CHART_URL_PREFIX"],
        )
        click.echo(result)
