import os
import json
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

SITE_URL = "https://www.dnyxxg.com/"
BASE_URL = "https://www.dnyxxg.com"

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID_OTHER")

SEEN_FILE = "seen_dnyxxg.json"


def clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def load_seen():
    if not os.path.exists(SEEN_FILE):
        return set()

    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen)[-300:], f, ensure_ascii=False, indent=2)


def get_html(url):
    headers = {
        "User-Agent": "Mozilla/5.0 AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    response = requests.get(url, headers=headers, timeout=25)
    response.raise_for_status()

    # 修复中文乱码
    response.encoding = response.apparent_encoding

    return response.text


def fetch_articles():
    html = get_html(SITE_URL)
    soup = BeautifulSoup(html, "html.parser")

    articles = []

    skip_words = [
        "首页",
        "更多",
        "搜索",
        "导航",
        "联系我们",
        "阅读更多",
        "XML地图",
        "English",
        "EN",
        "专题",
        "标签",
        "热门",
        "排行榜",
        "快速链接",
        "新闻分类",
        "美食专题",
        "旅游专题",
    ]

    category_words = [
        "东盟新闻",
        "社会新闻",
        "国际新闻",
        "文旅频道",
        "财经新闻",
        "娱乐新闻",
        "国内新闻",
        "南亚视窗",
        "图行天下",
        "美食特产",
        "泰国",
        "越南",
        "柬埔寨",
        "印尼",
        "马来西亚",
        "新加坡",
        "老挝",
        "缅甸",
        "菲律宾",
        "文莱",
    ]

    for a in soup.find_all("a", href=True):
        title = clean_text(a.get_text())
        href = a.get("href", "")

        if len(title) < 14:
            continue

        if any(word in title for word in skip_words):
            continue

        if title in category_words:
            continue

        link = urljoin(BASE_URL, href)

        if "dnyxxg.com" not in link:
            continue

        bad_links = [
            "/tags/",
            "/tag/",
            "/search",
            "/sitemap",
            "/list/",
            "/category/",
            "/about",
            "/contact",
            "#",
        ]

        if any(bad in link.lower() for bad in bad_links):
            continue

        path = link.replace(BASE_URL, "").strip("/")

        if not path:
            continue

        if len(path) < 5:
            continue

        articles.append({
            "title": title,
            "link": link
        })

    unique = []
    used = set()

    for item in articles:
        if item["link"] not in used:
            unique.append(item)
            used.add(item["link"])

    print(f"找到 {len(unique)} 篇文章")

    for item in unique[:8]:
        print("文章：", item["title"], item["link"])

    return unique[:8]


def get_summary(article_url):
    try:
        html = get_html(article_url)
        soup = BeautifulSoup(html, "html.parser")

        desc = soup.find("meta", attrs={"name": "description"})
        if desc and desc.get("content"):
            return clean_text(desc.get("content"))[:500]

        og_desc = soup.find("meta", attrs={"property": "og:description"})
        if og_desc and og_desc.get("content"):
            return clean_text(og_desc.get("content"))[:500]

        paragraphs = []

        bad_words = [
            "广告",
            "订阅",
            "更多消息",
            "延伸阅读",
            "相关新闻",
            "版权所有",
            "关注我们",
            "免责声明",
            "责任编辑",
            "来源",
        ]

        for p in soup.find_all("p"):
            text = clean_text(p.get_text())

            if len(text) < 20:
                continue

            if any(word in text for word in bad_words):
                continue

            paragraphs.append(text)

        if paragraphs:
            return " ".join(paragraphs[:4])[:500]

        return "暂无更多内容。"

    except Exception as e:
        print("获取内容失败：", e)
        return "暂无更多内容。"


def is_bad_image(image_url):
    image_url = (image_url or "").lower()

    bad_keywords = [
        "logo",
        "icon",
        "favicon",
        "qrcode",
        "qr",
        "wechat",
        "weixin",
        "avatar",
        "default",
        "banner",
        "ad",
        "ads",
        "loading",
        "placeholder",
        "blank",
        "sprite",
    ]

    return any(word in image_url for word in bad_keywords)


def get_image(article_url):
    try:
        html = get_html(article_url)
        soup = BeautifulSoup(html, "html.parser")

        # 1. 优先取文章封面图
        og_image = soup.find("meta", attrs={"property": "og:image"})
        if og_image and og_image.get("content"):
            image_url = urljoin(BASE_URL, og_image.get("content"))

            if not is_bad_image(image_url):
                print("使用 og:image：", image_url)
                return image_url

        # 2. 再取 twitter:image
        twitter_image = soup.find("meta", attrs={"name": "twitter:image"})
        if twitter_image and twitter_image.get("content"):
            image_url = urljoin(BASE_URL, twitter_image.get("content"))

            if not is_bad_image(image_url):
                print("使用 twitter:image：", image_url)
                return image_url

        # 3. 再从正文图片里找
        for img in soup.find_all("img"):
            src = (
                img.get("src")
                or img.get("data-src")
                or img.get("data-original")
                or img.get("data-lazy-src")
            )

            if not src:
                continue

            image_url = urljoin(BASE_URL, src)

            if is_bad_image(image_url):
                continue

            print("使用正文图片：", image_url)
            return image_url

        print("没有找到合适图片")
        return None

    except Exception as e:
        print("获取图片失败：", e)
        return None


def send_text_to_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(url, data={
        "chat_id": CHAT_ID,
        "text": text[:3900],
        "disable_web_page_preview": True,
    }, timeout=25)

    print("Telegram 状态：", response.status_code)
    print("Telegram 返回：", response.text)

    response.raise_for_status()


def send_to_telegram(title, summary, image_url=None):
    caption = f"""📰 {title}

{summary}
"""

    if image_url:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

        response = requests.post(url, data={
            "chat_id": CHAT_ID,
            "photo": image_url,
            "caption": caption[:1000],
        }, timeout=25)

        print("Telegram 状态：", response.status_code)
        print("Telegram 返回：", response.text)

        if response.status_code == 200:
            return

        print("图片发送失败，改发文字")

    send_text_to_telegram(caption)


def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN 没有设置")

    if not CHAT_ID:
        raise ValueError("CHAT_ID_OTHER 没有设置")

    seen = load_seen()
    articles = fetch_articles()

    count = 0

    for article in reversed(articles):
        title = article["title"]
        link = article["link"]

        if link in seen:
            continue

        print("准备发布：", title)

        summary = get_summary(link)
        image_url = get_image(link)

        send_to_telegram(title, summary, image_url)

        seen.add(link)
        count += 1

        time.sleep(2)

    save_seen(seen)

    print(f"完成，本次发布 {count} 篇")


if __name__ == "__main__":
    main()
