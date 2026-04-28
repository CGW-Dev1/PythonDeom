# PyBlog 园地

一个基于 Flask + MySQL 的博客社区系统。首页参考博客园的信息组织方式，包含频道导航、文章流、分类、标签、推荐排行、阅读排行、最新评论、作者主页和后台内容管理。

## 功能

- 门户式首页：顶部导航、频道 Tab、分类入口、文章信息流、右侧排行和标签
- 文章系统：分类、标签、摘要、正文、发布/草稿、精华标记
- 互动数据：阅读数、推荐数、评论数、文章推荐按钮
- 作者页：按作者查看公开文章
- 用户系统：注册、登录、个人资料修改、头像颜色和个人简介
- 评论系统：文章评论、后台显示/隐藏/删除评论
- 后台管理：文章新建、编辑、删除、统计概览
- MySQL 持久化：启动时自动创建数据库、表和演示数据
- 视觉背景：`static/images/anime-background.png` 作为半透明二次元风格背景图

## 数据存储

数据存在本地 MySQL：

- 默认数据库：`python_blog`
- 表：`users`、`categories`、`posts`、`comments`
- 表结构：`schema.sql`

默认连接配置：

```powershell
BLOG_MYSQL_HOST=127.0.0.1
BLOG_MYSQL_PORT=3306
BLOG_MYSQL_USER=root
BLOG_MYSQL_PASSWORD=123456
BLOG_MYSQL_DATABASE=python_blog
```

如果你的 MySQL `root` 不是空密码，请先设置环境变量。

## 运行

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt

$env:BLOG_MYSQL_HOST="127.0.0.1"
$env:BLOG_MYSQL_PORT="3306"
$env:BLOG_MYSQL_USER="root"
$env:BLOG_MYSQL_PASSWORD="123456"
$env:BLOG_MYSQL_DATABASE="python_blog"

.\.venv\Scripts\python -m flask --app app run --host 127.0.0.1 --port 5000
```

打开 `http://127.0.0.1:5000`。

默认后台账号：

- 用户名：`admin`
- 密码：`admin123`

普通用户可以通过首页右上角“注册”创建账号。注册用户默认是作者，只能管理自己的文章和自己文章下的评论；管理员可以管理全部内容。

## 常用配置

```powershell
$env:BLOG_SECRET_KEY="replace-with-a-random-secret"
$env:BLOG_ADMIN_USERNAME="admin"
$env:BLOG_ADMIN_PASSWORD="change-me"
$env:BLOG_ADMIN_DISPLAY_NAME="博客管理员"
```

首次启动会创建管理员账号和演示数据。如果已经创建过管理员账号，修改 `BLOG_ADMIN_PASSWORD` 不会自动覆盖旧密码；可以在 MySQL 中删除 `python_blog` 数据库后重新启动，或手动更新 `users.password_hash`。

## MySQL 建库权限

应用启动时会执行：

```sql
CREATE DATABASE IF NOT EXISTS python_blog CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

因此 MySQL 用户需要有创建数据库和建表权限。如果你想使用权限更小的账号，可以先手动创建数据库，再给该账号授权。
