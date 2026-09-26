"""用真实 Chrome 验证能否绕过微信验证码，拿到公众号文章正文 + 图片。"""

import sys
import json
import asyncio
from playwright.async_api import async_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else (
    "https://mp.weixin.qq.com/s?__biz=MzA3MzI4MjgzMw%3D%3D&mid=2651058555&idx=1&sn=7607ebea718c9fa42624ed4b21622a4b"
)

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.49(0x1800312d) "
    "NetType/WIFI Language/zh_CN"
)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome",
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent=UA,
            viewport={"width": 390, "height": 844},
            locale="zh-CN",
        )
        page = await ctx.new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(4000)

        final_url = page.url
        title = await page.title()
        has_captcha = ("captcha" in final_url) or ("wappoc" in final_url)

        result = {"final_url": final_url, "title": title, "has_captcha": has_captcha}

        if not has_captcha:
            og = await page.eval_on_selector(
                "meta[property='og:title']", "el => el.content"
            ) if await page.query_selector("meta[property='og:title']") else ""
            js = await page.query_selector("#js_content")
            if js:
                html = await js.inner_html()
                imgs = await js.query_selector_all("img")
                srcs = []
                for im in imgs:
                    s = await im.get_attribute("src") or await im.get_attribute("data-src") or ""
                    srcs.append(s)
                result.update({
                    "og_title": og,
                    "content_len": len(html),
                    "img_count": len(imgs),
                    "img_srcs": srcs[:5],
                })
        print(json.dumps(result, ensure_ascii=False, indent=2))
        await browser.close()


asyncio.run(main())
