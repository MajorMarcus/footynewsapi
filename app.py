from flask import Flask, request, jsonify
from bs4 import BeautifulSoup, SoupStrainer
import aiohttp
import asyncio
import urllib.parse
import httpx
from unidecode import unidecode
import re
from groq import Groq
from functools import lru_cache
from aiohttp import TCPConnector, ClientTimeout

# Constants and Patterns
WOMENS_WORDS = frozenset([
    'wsl', "women", "women's", "womens", "female", "ladies", "girls", "nwsl", 
    "fa wsl", "female football", "mujer", "damas", "femme", "calcio femminile", 
    "football féminin", "fußball frauen", "she", "her", "w-league"
])
PATTERN_PHOTO = re.compile(r"\(Photo by [^)]+\)")
PATTERN_WORD = re.compile(r'\b\w+\b')
BLOCKED_DOMAINS = frozenset(['betting', 'squawka', 'bit.ly', 'footballtoday.com'])

# Proxy Configuration
proxies = {"http://": "https://groqcall.ai/proxy/groq/v1"}

class ProxyHttpxClient(httpx.Client):
    def __init__(self, proxies=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if proxies:
            self.proxies = proxies

# Initialize clients with connection pooling
clients = [
    Groq(api_key=key, http_client=ProxyHttpxClient(proxies=proxies))
    for key in [
        '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',
        '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',
        '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',
        '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',
        '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'
    ]
]

app = Flask(__name__)

@lru_cache(maxsize=1000)
def contains_word_from_list(text):
    words_in_text = set(PATTERN_WORD.findall(text.lower()))
    return bool(words_in_text & WOMENS_WORDS)

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

@lru_cache(maxsize=1000)
def extract_actual_url(url):
    if any(domain in url for domain in BLOCKED_DOMAINS):
        return None
    key = "image="
    start = url.find(key)
    return urllib.parse.unquote(url[start + len(key):]).replace('width=720', '') if start != -1 else None

async def batch_rephrase_titles(titles, batch_size=10):
    if not titles:
        return []
    
    titles_prompt = "\n".join([f"{i+1}. {title}" for i, title in enumerate(titles)])
    prompt = f"Rephrase these football news article titles to 6-9 words each without changing meaning:\n{titles_prompt}"
    
    results = []
    for i in range(0, len(titles), batch_size):
        batch = titles[i:i + batch_size]
        client = clients[i % len(clients)]
        
        try:
            completion = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama3-8b-8192",
                temperature=0,
                top_p=0,
            )
            batch_results = [
                content.split(". ", 1)[-1]
                for content in completion.choices[0].message.content.split("\n")
                if ". " in content
            ]
            results.extend(batch_results)
        except Exception as e:
            print(f"Error in title rephrasing: {e}")
            results.extend(batch)  # Fallback to original titles
            
    return results

async def batch_rephrase_content(contents):
    if not contents:
        return []

    batch_size = 2
    results = []
    
    async def process_batch(client, batch):
        if not batch:
            return []
        prompt = (
            "Rephrase these football news articles into detailed summaries. Make them concise while keeping all details. "
            "only respond with the article content and dont give any intro for seamlessness to not break the 4th wall"
            "Avoid repetitive words and make it direct while maintaining the original meaning. Keep all names and keywords unchanged:\n" +

            "\n".join(f"{i+1}. {content}" for i, content in enumerate(batch))
        )
        try:
            completion = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama3-8b-8192",
                temperature=0,
                top_p=0,
            )
            return [
                content for content in completion.choices[0].message.content.split("\n")
                if content and not any(word in content.lower() for word in ['article:', 'summary:','article','Article','summaries', '*'])
            ]
        except Exception as e:
            print(f"Error in content rephrasing: {e}")
            return batch

    for i in range(0, len(contents), batch_size * len(clients)):
        tasks = []
        for j, client in enumerate(clients):
            start_idx = i + j * batch_size
            batch = contents[start_idx:start_idx + batch_size]
            if batch:
                tasks.append(process_batch(client, batch))
        
        batch_results = await asyncio.gather(*tasks)
        for batch_result in batch_results:
            if 'article' in batch_result:
                print(batch_result)
                continue
            else:
                results.extend(batch_result)
    
    return results

async def fetch(session, url):
    async with session.get(url, timeout=10) as response:
        return await response.text() if response.status == 200 else None

async def fetch_json(session, url):
    async with session.get(url, timeout=10) as response:
        return await response.json() if response.status == 200 else None

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
        
        if not text_elements or (womens is False and (contains_word_from_list(text_elements) or contains_word_from_list(img_url))):
            return None

        return {
            'title': title,
            'article_content': text_elements,
            'img_url': img_url,
            'article_url': article_url,
            'article_id': article_url[:-8],
            'time': time,
            'publisher': publisher,
            'attribution': attribution or '',
        }
    except Exception as e:
        print(f"Error scraping article: {e}")
        return None

async def scrape_news_items(team, before_id, needbeforeid, womens):
    connector = TCPConnector(limit=100, force_close=True)
    timeout = ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        url = f'https://api.onefootball.com/web-experience/en/team/{team}/news'
        if needbeforeid:
            url += f'?before_id={before_id}'
        
        response = await fetch_json(session, url)
        if not response:
            return [], None

        containers = response.get('containers', [])
        teasers = []
        
        if before_id:
            teasers.extend(response.get('teasers', []))
        else:
            if len(containers) > 3:
                teasers.extend(containers[3].get('fullWidth', {}).get('component', {}).get('gallery', {}).get('teasers', []))
            if len(containers) > 5:
                teasers.extend(containers[5].get('fullWidth', {}).get('component', {}).get('gallery', {}).get('teasers', []))

        if not teasers:
            return [], None

        scrape_tasks = []
        titles = []
        for teaser in teasers:
            image_path = teaser.get('imageObject', {}).get('path', '')
            if not image_path:
                continue
                
            image = extract_actual_url(urllib.parse.unquote(image_path))
            if not image:
                continue
                
            image = image.replace('&q=25&w=1080', '')
            titles.append(teaser['title'])
            scrape_tasks.append(
                scrape_article(
                    session, teaser['link'], teaser['title'], 
                    image, teaser['publishTime'], 
                    teaser['publisherName'], womens
                )
            )

        articles = [a for a in await asyncio.gather(*scrape_tasks) if a]
        
        # Parallel processing of titles and contents
        title_task = batch_rephrase_titles([a['title'] for a in articles])
        content_task = batch_rephrase_content([a['article_content'] for a in articles])
        
        rephrased_titles, rephrased_contents = await asyncio.gather(title_task, content_task)
        
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
    before_id = request.args.get('before_id')
    team = url[32:-5]
    
    news_items, last_id = await scrape_news_items(team, before_id, bool(before_id), womens)
    return jsonify({'news_items': news_items, 'last_id': last_id})

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
 
