# 基于 Python 爬虫的房租数据分析系统

本项目实现了房源采集、数据清洗入库、租金统计分析、Matplotlib 图表生成、Flask Web 展示、用户注册登录和房源筛选查询。

## 技术栈

- Python 3.8+
- Flask + Flask-SQLAlchemy
- Selenium + ChromeDriver
- Pandas + Matplotlib
- MySQL 5.7/8.0（默认也支持 SQLite 便于本地演示）
- HTML + CSS + JavaScript

## 快速运行

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

浏览器访问：`http://127.0.0.1:5000`

首次打开后可以点击“导入演示数据”，系统会生成统计表和图表。默认数据库文件为 `rent_analysis.db`。

## 使用 MySQL

1. 在 MySQL 中执行 `sql/schema_mysql.sql`。
2. 复制 `.env.example` 为 `.env`。
3. 修改 `DATABASE_URL`：

```env
DATABASE_URL=mysql+pymysql://root:password@127.0.0.1:3306/rent_analysis?charset=utf8mb4
```

4. 重新启动 `python run.py`。

## 常用命令

```powershell
# 导入演示数据
flask --app run seed

# 清空后重新导入演示数据
flask --app run seed --clear

# 采集 58 同城北京租房数据，采集 3 页
flask --app run crawl --platform 58 --city bj --pages 3

# 采集房天下北京租房数据
flask --app run crawl --platform fang --city bj --pages 3

# 重新生成统计图表
flask --app run charts
```

## 目录说明

```text
app/
  crawlers/              Selenium 平台爬虫适配器
  services/              清洗、分析、采集入库服务
  static/                CSS、JS、生成图表
  templates/             Flask 页面模板
  models.py              用户表、房源表模型
  routes.py              页面路由与 API
sql/schema_mysql.sql     MySQL 建表脚本
docs/design.md           设计文档
docs/user_guide.md       使用说明
requirements.txt         依赖清单
```

## 合规说明

爬虫模块内置随机等待、浏览器模拟和异常日志记录。实际采集前应遵守目标网站 robots 协议和服务条款，控制采集频率，仅用于学习、研究或已获授权的数据分析场景。
