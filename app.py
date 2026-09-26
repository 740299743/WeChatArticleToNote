"""微信公众号文章 → 可编辑笔记（带图）MVP 后端

关键结论（踩坑验证）：
- 服务端 requests/curl 直连 mp.weixin.qq.com/s 会被微信验证码风控拦截（返回 wappoc_appmsgcaptcha）
- 真实浏览器（headless Chrome + 移动端微信 UA）可绕过验证码，拿到完整正文
- 正文图片是懒加载：真实地址在 data-src / data-original，src 是 1x1 占位 svg
- 图片防盗链：用浏览器 context.request 带 Referer 下载可破
"""

import hashlib
from pathlib import Path

from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
IMG_DIR = STATIC_DIR / "images"
IMG_DIR.mkdir(parents=True, exist_ok=True)

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.49(0x1800312d) "
    "NetType/WIFI Language/zh_CN"
)
REFERER = "https://mp.weixin.qq.com/"

app = FastAPI(title="微信文章转笔记")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _download_img(context, img_url: str) -> str | None:
    """在浏览器上下文里下载图片（带 Referer，破防盗链），存本地返回路径。"""
    try:
        resp = context.request.get(
            img_url,
            headers={"Referer": REFERER, "User-Agent": UA},
            timeout=30000,
        )
        if resp.status != 200:
            return None
        data = resp.body()
    except Exception:
        return None
    if not data or len(data) < 100:
        return None

    ct = resp.headers.get("content-type", "")
    ext = "jpg"
    if "png" in ct:
        ext = "png"
    elif "gif" in ct:
        ext = "gif"
    elif "webp" in ct:
        ext = "webp"

    name = hashlib.md5(img_url.encode()).hexdigest()[:16] + "." + ext
    (IMG_DIR / name).write_bytes(data)
    return f"/static/images/{name}"


def fetch_article(url: str) -> dict:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            user_agent=UA,
            viewport={"width": 390, "height": 844},
            locale="zh-CN",
        )
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        # 等正文出现（最长 12s）
        page.wait_for_selector("#js_content", timeout=12000)
        page.wait_for_timeout(2500)

        if "captcha" in page.url or "wappoc" in page.url:
            browser.close()
            raise HTTPException(502, "微信触发了验证码，请稍后重试")

        # 触发懒加载：滚动到底部
        page.evaluate(
            "async () => { for (let i=0;i<5;i++){ window.scrollTo(0, document.body.scrollHeight); await new Promise(r=>setTimeout(r,300)); } }"
        )

        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "html.parser")

    t = soup.find("meta", property="og:title") or soup.find(id="activity-name")
    title = (t.get("content") or t.get_text()).strip() if t else "未命名文章"

    a = soup.find(id="js_name") or soup.find("meta", property="og:article:author")
    author = (a.get_text() or a.get("content") or "").strip() if a else ""

    content = soup.find(id="js_content") or soup.body
    if content is None:
        raise HTTPException(502, "未能解析到正文")

    for tag in content.find_all(["script", "style"]):
        tag.decompose()

    # 重新打开浏览器上下文下载图片（复用抓取时的 cookie 最稳，但这里简化：新开一个短上下文）
    img_urls = []
    for img in content.find_all("img"):
        src = (
            img.get("data-src")
            or img.get("data-original")
            or img.get("src")
            or ""
        ).strip()
        if src.startswith("//"):
            src = "https:" + src
        if src.startswith("http"):
            img_urls.append(src)

    # 用一个独立短会话统一下载图片
    local_map = {}
    if img_urls:
        with sync_playwright() as p:
            b2 = p.chromium.launch(channel="chrome", headless=True)
            c2 = b2.new_context(user_agent=UA, locale="zh-CN")
            for u in dict.fromkeys(img_urls):
                local_map[u] = _download_img(c2, u)
            b2.close()

    img_count = 0
    for img in content.find_all("img"):
        src = (
            img.get("data-src")
            or img.get("data-original")
            or img.get("src")
            or ""
        ).strip()
        if src.startswith("//"):
            src = "https:" + src
        if not src.startswith("http"):
            img.decompose()
            continue
        local = local_map.get(src)
        img["src"] = local if local else src
        if local:
            img_count += 1
        for attr in ("data-src", "data-original", "data-w", "data-ratio",
                     "data-type", "data-s", "data-croporisrc", "data-cropselx1",
                     "data-cropselx2", "data-cropsely1", "data-cropsely2",
                     "data-oversubscription-url", "style"):
            if img.has_attr(attr):
                del img[attr]

    return {
        "title": title,
        "author": author,
        "content_html": str(content),
        "image_count": img_count,
        "source_url": url,
    }


class FetchReq(BaseModel):
    url: str


@app.post("/api/fetch")
def fetch(req: FetchReq):
    url = req.url.strip()
    if "mp.weixin.qq.com" not in url:
        raise HTTPException(400, "请粘贴微信公众号文章链接（mp.weixin.qq.com）")
    try:
        return fetch_article(url)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"抓取失败：{e}")


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
