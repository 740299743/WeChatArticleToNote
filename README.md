# 微信文章转笔记（WeChatArticleToNote）

把微信公众号文章一键转成**可编辑、带图片**的笔记。粘贴文章链接，自动抓取正文 + 全部图片（本地化），支持在线编辑、复制（带图 / Markdown）、导出 HTML / Markdown。

> 解决的核心痛点：市面上多数工具从公众号"复制"只能拿到文字、图片会丢。本工具把图片真正抓取下来并本地化，图文完整可编辑。

## 功能特性

- **粘贴链接一键抓取**：标题、作者、正文、图片一次拿到
- **图片本地化**：破防盗链，1080p 高清图 + GIF 动图全保留
- **在线富文本编辑**：加粗、斜体、标题、引用、清除格式
- **复制（带图）**：图文写入剪贴板，粘贴到公众号编辑器 / Word / 印象笔记 / 语雀等富文本环境
- **复制 Markdown**：文字转 Markdown，图片 base64 内嵌
- **导出 HTML / Markdown**：下载为文件

## 核心原理（为什么能抓到图）

公众号文章有"三道防护"，这是本项目的关键：

1. **验证码风控**：服务端 requests / curl 直连 `mp.weixin.qq.com/s` 会被重定向到验证页（`wappoc_appmsgcaptcha`）。→ 用**真实浏览器（headless Chrome）+ 移动端微信 UA** 绕过。
2. **图片懒加载**：正文图片真实地址藏在 `data-src` 属性里，`src` 是 1×1 占位 svg。→ 解析时取 `data-src` / `data-original`。
3. **图片防盗链**：`mmbiz.qpic.cn` 校验 Referer，非微信域名返回 403。→ 用浏览器 `context.request` 带 `Referer: https://mp.weixin.qq.com/` 下载。

## 环境要求

- Python 3.9+
- Google Chrome（本项目通过 `channel="chrome"` 复用系统 Chrome，无需 `playwright install` 下载浏览器）

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动服务
python -m uvicorn app:app --host 127.0.0.1 --port 8000

# 3. 浏览器打开
open http://127.0.0.1:8000
```

## 使用说明

1. 在微信里打开目标文章 → 右上角「···」→「复制链接」
2. 粘贴到页面输入框 → 点「抓取」（约 10~20 秒，含浏览器启动 + 图片下载）
3. 在下方富文本编辑器里直接编辑
4. 选择输出方式：
   - **复制（带图）**：图文写入剪贴板，粘贴到公众号编辑器 / Word / 印象笔记 / 语雀等
   - **复制 Markdown**：文字转 Markdown，图片 base64 内嵌
   - **导出 HTML / Markdown**：下载为文件

> 注意：复制功能依赖剪贴板 API，需在 `localhost` 或 HTTPS 下、且由点击触发。

## 项目结构

```
wechat_note/
├── app.py            # FastAPI 后端：浏览器抓取 + 图片本地化
├── index.html        # 前端：粘贴链接 → 可编辑 → 复制/导出
├── test_browser.py   # 抓取链路调试脚本
├── static/
│   └── images/       # 抓取后本地化的图片（运行时生成）
└── requirements.txt  # 依赖清单
```

## API

`POST /api/fetch`

- 请求：`{"url": "https://mp.weixin.qq.com/s/..."}`
- 响应：`{"title", "author", "content_html", "image_count", "source_url"}`

## 已知限制

- 服务端抓取依赖真实浏览器，每次约 10~20 秒，尚未做浏览器实例复用
- 高频 / 代理 IP 访问仍可能触发验证码（微信 IP 级风控），适合个人自用，不适合作为公网产品长期跑
- 需登录或有特殊权限的文章无法抓取
- 复制到纯文本环境（记事本、聊天框）时图片会丢失，属正常现象

## 后续规划

- [ ] 浏览器实例复用 / 连接池，降低抓取耗时
- [ ] 多篇收藏与历史管理
- [ ] 浏览器插件形态（用户自带会话，最稳）
- [ ] 公众号后台排版适配
