# 二手房数据可视化大屏系统

基于 Flask + SQLite + Pandas + ECharts 的二手房数据可视化大屏示例项目，覆盖数据导入、清洗、存储、指标计算、图表 API、筛选联动、导出、登录权限和后台维护入口。

> 合规说明：项目默认不内置对商业房产平台的爬虫，也不绕过登录、验证码、反爬或用户协议限制。生产环境请优先使用政府/统计机构公开数据、平台授权接口或已获授权的数据文件。本项目提供 CSV 导入与数据源配置入口，并内置可复现的演示数据用于开发和验收演示。

## 快速启动

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

启动后访问：

- 大屏首页：http://127.0.0.1:5000
- 系统后台：http://127.0.0.1:5000/admin

默认账号：

- 管理员：admin / admin123
- 普通用户：viewer / viewer123

首次启动会自动初始化 SQLite 数据库，并生成一批演示房源数据。数据库文件位于 `instance/housing.db`。

## CSV 导入字段

后台支持上传 CSV，字段可使用中文或英文列名。核心字段示例：

| 中文字段 | 英文字段 |
| --- | --- |
| 房源ID | listing_id |
| 所属城市 | city |
| 所属区域 | district |
| 板块名称 | block |
| 小区名称 | community |
| 户型 | layout |
| 建筑面积 | area |
| 楼层 | floor_level |
| 朝向 | orientation |
| 装修情况 | decoration |
| 建筑年代 | build_year |
| 挂牌总价 | list_total_price |
| 挂牌单价 | list_unit_price |
| 成交总价 | deal_total_price |
| 成交单价 | deal_unit_price |
| 交易状态 | status |
| 挂牌时间 | listing_date |
| 成交时间 | deal_date |
| 交易周期 | transaction_cycle |
| 周边学校 | school |
| 医院 | hospital |
| 商场 | mall |
| 交通站点 | metro_station |

## 主要功能

- 数据管理：CSV 导入、演示数据初始化、采集/导入日志、数据质量统计。
- 数据清洗：字段映射、类型转换、缺失值标注、异常面积/价格过滤、重复房源去重。
- 可视化：核心指标、区域热力、户型分布、价格/面积区间、装修分布、价格走势、供需走势、调价趋势、热门小区、配套价值、楼层朝向分析。
- 交互：城市/区域/价格/户型/面积/时间/关键词筛选，图表点击联动，自动刷新，全屏切换。
- 导出：明细 CSV、明细 Excel、统计 CSV。
- 管理：登录认证、角色权限、数据维护后台、系统配置接口预留。

## 目录结构

```text
app/
  __init__.py          Flask 应用工厂
  auth.py              登录、权限装饰器
  db.py                SQLite 连接与初始化
  routes.py            页面路由
  api.py               API 路由
  services/
    analytics.py       指标和图表聚合
    ingestion.py       导入、清洗、演示数据生成
    export.py          CSV/Excel 导出
  static/
    css/dashboard.css
    js/dashboard.js
    js/admin.js
  templates/
    dashboard.html
    login.html
    admin.html
schema.sql             数据库表结构
run.py                 启动入口
requirements.txt       Python 依赖
```

## 生产落地建议

- 将 SQLite 替换为 MySQL/PostgreSQL，并迁移索引、备份、恢复策略。
- 对接授权数据源或官方公开数据接口，把数据源接入逻辑放在 `app/services/ingestion.py`。
- 为接口增加更严格的审计日志、速率限制、HTTPS、数据库加密和备份任务。
- 使用 Nginx + Gunicorn/uWSGI 部署，并将定时任务拆到独立 Worker 或任务平台。
