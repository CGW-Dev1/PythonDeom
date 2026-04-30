# 系统设计文档

## 总体架构

系统采用分层结构：

- 爬虫层：`app/crawlers` 中按平台封装 Selenium 采集逻辑。
- 清洗层：`RentDataCleaner` 统一租金、面积、户型、朝向格式，并剔除异常数据。
- 存储层：`Listing`、`User` 两个 SQLAlchemy 模型，默认 SQLite，支持 MySQL。
- 分析层：`analytics.py` 使用 Pandas 聚合统计，使用 Matplotlib 输出 PNG 图表。
- Web 层：Flask 提供页面、查询接口、统计接口和采集入口。

## 数据流程

1. Selenium 打开租房平台列表页并解析卡片文本。
2. 原始记录传入清洗器，完成字段标准化、范围校验和去重。
3. 入库时使用 `raw_hash` 进行唯一约束，避免重复房源。
4. Web 端通过 AJAX 获取房源列表、统计数据和图表地址。
5. Matplotlib 将统计图保存到 `app/static/generated`，页面直接展示图片。

## 模块扩展

新增租房平台时：

1. 在 `app/crawlers` 新增一个继承 `BaseSeleniumRentCrawler` 的类。
2. 实现 `build_url()` 与 `parse_current_page()`。
3. 在 `app/services/crawler_runner.py` 的 `CRAWLER_REGISTRY` 注册平台标识。

## 数据约束

- 租金范围：200 到 100000 元/月。
- 面积范围：5 到 500 平方米。
- 单价上限：1200 元/㎡/月。
- 去重维度：区域、小区、户型、面积、租金。

## 安全设计

- 用户密码使用 Werkzeug 哈希存储。
- 查询接口使用 ORM 参数构造，避免 SQL 注入。
- 爬虫结果统一清洗后入库，减少脏数据影响统计结果。
