# 商品比价工具

这是一个基于 Flask 的 Python 商品比价网站，实现了需求文档中的核心流程：

- 商品分类展示、切换、新增、编辑、删除
- 单个或批量商品网址采集
- 同一分类下按价格从低到高自动排序
- 手动刷新当前分类价格
- 清空当前分类采集记录
- 爬虫超时时间、批量上限、平台开关配置
- 采集成功率、平均响应时间、采集日志查看

## 运行环境

- Python 3.8+
- Windows、macOS、Linux 均可运行

## 安装依赖

```bash
pip install -r requirements.txt
```

如需更快的 HTML 解析，可额外安装 `lxml`。项目未强制依赖它，未安装时会自动使用 Python 内置解析器。

## 启动项目

```bash
python app.py
```

启动后访问：

```text
http://127.0.0.1:5001
```

## 使用说明

1. 打开首页，选择商品分类。
2. 在输入框中粘贴商品网址，多个网址可换行输入。
3. 点击“获取价格”，系统会自动采集价格并按低价优先展示。
4. 可点击“刷新价格”重新采集当前分类全部商品价格。
5. 可点击“清空记录”清理当前分类数据。
6. 点击右上角“管理”，可维护分类、调整爬虫配置并查看采集日志。

## 数据说明

项目使用内存保存当前浏览器会话中的采集记录，不需要数据库。服务重启或浏览器会话结束后，采集记录会清空。

## 爬虫说明

当前实现使用 `requests + BeautifulSoup` 进行公开页面采集，支持 JSON-LD、meta 标签、常见价格节点和价格文本正则解析。淘宝、京东、拼多多等平台可能存在动态加载、登录校验或反爬策略，真实生产环境可在 `PriceCrawler` 中扩展 Selenium、Playwright、平台专用接口或代理池。

## API 概览

- `GET /api/categories`：获取分类列表
- `POST /api/categories`：新增分类
- `PUT /api/categories/<category_id>`：编辑分类
- `DELETE /api/categories/<category_id>`：删除分类
- `GET /api/categories/<category_id>/items`：获取当前分类比价记录
- `POST /api/categories/<category_id>/collect`：采集一个或多个网址价格
- `POST /api/categories/<category_id>/refresh`：刷新当前分类全部价格
- `DELETE /api/categories/<category_id>/items`：清空当前分类记录
- `GET /api/config`：获取爬虫配置
- `PUT /api/config`：更新爬虫配置
- `GET /api/metrics`：查看采集监控数据
