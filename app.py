from flask import Flask, request, jsonify
from bs4 import BeautifulSoup, SoupStrainer
import asyncio
import aiohttp
import urllib.parse
import re
from functools import lru_cache

# Constants and Patterns
WOMENS_WORDS = frozenset([
    'wsl', "women", "women's", "womens", "female", "ladies", "girls", "nwsl", 
    "fa wsl", "female football", "mujer", "damas", "femme", "calcio femminile", 
    "football féminin", "fußball frauen", "she", "her", "w-league"
])
PATTERN_PHOTO = re.compile(r"\(Photo by [^)]+\)")
PATTERN_WORD = re.compile(r'\b\w+\b')
BLOCKED_DOMAINS = frozenset(['betting', 'squawka', 'bit.ly', 'footballtoday.com'])

app = Flask(__name__)

# Caching common computations
@lru_cache(maxsize=1000)
def contains_word_from_list(text):
    words_in_text = set(PATTERN_WORD.findall(text.lower()))
    return bool(words_in_text & WOMENS_WORDS)

@lru_cache(maxsize=1000)
def extract_actual_url(url):
    if any(domain in url for domain in BLOCKED_DOMAINS):
        return None
    key = "image="
    start = url.find(key)
    return urllib.parse.unquote(url[start + len(key):]).replace('width=720', '') if start != -1 else None

def extract_text_with_spacing(html_content):
    soup = BeautifulSoup(html_content, 'html.parser', parse_only=SoupStrainer('p'))
    texts = []
    attribution = None

    for p in soup:
        text = p.get_text()
        clean_text = PATTERN_PHOTO.sub('', text).strip()
        if clean_text:
            texts.append(clean_text)
        if not attribution:
            match = PATTERN_PHOTO.search(text)
            if match:
                attribution = match.group()

    return ' '.join(texts), attribution

async def fetch(session, url):
    try:
        async with session.get(url, timeout=10) as response:
            return await response.text() if response.status == 200 else None
    except Exception:
        return None

async def fetch_json(session, url):
    try:
        async with session.get(url, timeout=10) as response:
            return await response.json() if response.status == 200 else None
    except Exception:
        return None

async def scrape_article(session, article_url, title, img_url, time, publisher, womens):
    try:
        article_response = await fetch(session, f"https://onefootball.com/{article_url}")
        if not article_response:
            return None

        article_soup = BeautifulSoup(
            article_response, 
            'html.parser', 
            parse_only=SoupStrainer('div', class_='ArticleParagraph_articleParagraph__MrxYL')
        )
        text_elements, attribution = extract_text_with_spacing(str(article_soup))

        if not text_elements or (not womens and contains_word_from_list(text_elements)):
            return None

        img_url = img_url.replace('&q=25&w=1080', '')
        return {
            'title': title,
            'article_content': text_elements,
            'img_url': img_url,
            'article_url': article_url,
            'article_id': article_url[-8:],
            'time': time,
            'publisher': publisher,
            'attribution': attribution or '',
        }
    except Exception:
        return None

async def batch_rephrase(titles_or_contents, lang, is_title):
    if not titles_or_contents:
        return []

    batch_size = 10 if is_title else 4
    results = []

    async def process_batch(batch, is_title):
        prompt_type = "titles" if is_title else "contents"
        prompt = (
            f"Rephrase these football news {prompt_type} to 6-9 words each "
            if is_title else
            f"Rephrase these football news {prompt_type} into concise summaries."
        )
        prompt += " Use '|||' as a separator between entries.\n"
        prompt += "\n".join(batch)

        # Here you'd include your actual rephrasing logic, e.g., calling an AI API.
        # Simulating response here:
        return [item for item in batch]  # Placeholder

    for i in range(0, len(titles_or_contents), batch_size):
        batch = titles_or_contents[i:i + batch_size]
        results.extend(await process_batch(batch, is_title))

    return results

async def scrape_news_items(team, before_id, needbeforeid, womens, lang):
    async with aiohttp.ClientSession() as session:
        url = f'https://api.onefootball.com/web-experience/en/team/{team}/news'
        if needbeforeid:
            url += f'?before_id={before_id}'

        response = await fetch_json(session, url)
        if not response:
            return [], None

        teasers = response.get('teasers', [])
        scrape_tasks = []

        for teaser in teasers:
            image_path = teaser.get('imageObject', {}).get('path', '')
            image = extract_actual_url(urllib.parse.unquote(image_path))
            if image:
                scrape_tasks.append(
                    scrape_article(
                        session, teaser['link'], teaser['title'], 
                        image, teaser['publishTime'], teaser['publisherName'], womens
                    )
                )

        articles = [a for a in await asyncio.gather(*scrape_tasks) if a]

        # Rephrase titles and contents
        rephrased_titles = await batch_rephrase([a['title'] for a in articles], lang, is_title=True)
        rephrased_contents = await batch_rephrase([a['article_content'] for a in articles], lang, is_title=False)

        for article, title, content in zip(articles, rephrased_titles, rephrased_contents):
            article['title'] = title
            article['article_content'] = content

        return articles, teasers[-1]['id'] if teasers else None

@app.route('/scrape', methods=['GET'])
async def scrape():
    url = request.args.get('url')

    if not url:
        return jsonify({'error': 'URL is required'}), 400

    womens = request.args.get('womens', 'False').lower() == 'true'
    lang = request.args.get('lang', 'en')
    before_id = request.args.get('before_id')
    team = url[32:-5]

    news_items, last_id = await scrape_news_items(team, before_id, bool(before_id), womens, lang)
    return jsonify({'news_items': news_items, 'last_id': last_id})

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
