import os
import json
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# 这里改成你要抓的网站文章列表页
SITE_URL = "https://example.com/news"

# 这里改成网站首页域名
BASE_URL = "https://example.com"

# 如果你要发到另一个频道，GitHub Secrets 里设置 CHAT_ID_OTHER
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID_OTHER")

# 新网站建议用新的 seen 文件，避免和旧频道冲突
SEEN_FILE = "seen_other_site.json"


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

    r = requests.get(url, headers=headers, timeout=25)
    r.raise_for_status()
    return r.text


def fetch_articles():
    html = get_html(SITE_URL)
    soup = BeautifulSoup(html, "html.parser")

    articles = []

    for a in soup.find_all("a", href=True):
        title = clean_text(a.get_text())
        href = a.get("href", "")

        if len(title) < 8:
            continue

        link = urljoin(BASE_URL, href)

        # 通用文章链接判断
        # 如果抓不到文章，可以把下面这一段改成适合目标网站的关键词
        article_keywords = [
            "/news/",
            "/article/",
            "/story/",
            "/post/",
            "/content/",
            "/world/",
            "/china/",
            "/realtime/",
        ]

        if not any(word in link.lower() for word in article_keywords):
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


def get_image(article_url):
    try:
        html = get_html(article_url)
        soup = BeautifulSoup(html, "html.parser")

        og_image = soup.find("meta", attrs={"property": "og:image"})
        if og_image and og_image.get("content"):
            return urljoin(BASE_URL, og_image.get("content"))

        twitter_image = soup.find("meta", attrs={"name": "twitter:image"})
        if twitter_image and twitter_image.get("content"):
            return urljoin(BASE_URL, twitter_image.get("content"))

        img = soup.find("img")
        if img and img.get("src"):
            return urljoin(BASE_URL, img.get("src"))

        return None

    except Exception as e:
        print("获取图片失败：", e)
        return None


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

        # 如果图片发送失败，就改成只发文字
        if response.status_code != 200:
            print("图片发送失败，改发文字：", response.text)
            send_text_to_telegram(caption)
            return

    else:
        send_text_to_telegram(caption)
        return

    print("Telegram 状态：", response.status_code)
    print("Telegram 返回：", response.text)

    response.raise_for_status()


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
