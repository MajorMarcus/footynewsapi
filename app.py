from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
import aiohttp
import asyncio
import urllib.parse
from unidecode import unidecode
import firebase_admin
from firebase_admin import firestore
from firebase_admin import credentials
import os
import re
from groq import Groq

# Initialize Groq client
client = Groq(
    api_key='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',
)

# Initialize Firestore
cred = credentials.Certificate('futnews-864e6-c9579021ac88.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

# Flask app setup
app = Flask(__name__)

# Helper functions
def responsetitle(cont):
    chat_completion = client.chat.completions.create(
        messages=[{
            "role": "user",
            "content": f"Rephrase this football news article title to 6-9 words without changing the meaning: '{cont}'"
        }],
        model="llama3-8b-8192",
    )
    return chat_completion.choices[0].message.content

def response(cont):
    chat_completion = client.chat.completions.create(
        messages=[{
            "role": "user",
            "content": f"Rephrase this football news article text without changing names, keywords, or player names. Ensure similar word count and please just respond with the response and not anything else breaking the 4th wall of seamlessness: '{cont}'"
        }],
        model="llama3-8b-8192",
    )
    return chat_completion.choices[0].message.content

def contains_word_from_list(text, word_list):
    words_in_text = re.findall(r'\b\w+\b', text.lower())
    word_list = [word.lower() for word in word_list]
    return any(word in words_in_text for word in word_list)

def extract_text_with_spacing(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    pattern = r"\(Photo by [^)]+\)"
    textelements = []
    attribution = None
    for p in soup.find_all('p'):
        text = p.get_text()
        text_without_attribution = re.sub(pattern, '', text).strip()
        textelements.append(text_without_attribution)

        match = re.search(pattern, text)
        if match:
            attribution = match.group()

    return ' '.join(textelements), attribution

def extract_actual_url(url):
    key = "image="
    start = url.find(key)
    if start == -1 or any(domain in url for domain in ['betting', 'squawka', 'bit.ly', 'footballtoday.com']):
        return None
    return urllib.parse.unquote(url[start + len(key):]).replace('width=720', '')

def check_if_data_cached(article_id):
    doc = db.collection('cache').document(article_id).get()
    return doc.to_dict() if doc.exists else None

def add_data(article_id, content, title):
    db.collection('cache').document(article_id).set({
        'content': content,
        'title': title
    })

def add_data_in_batches(data):
    """Add multiple documents to Firestore using batched writes."""
    batch = db.batch()  # Initialize a Firestore batch
    batch_size = 500  # Firestore allows a maximum of 500 writes per batch
    counter = 0

    for article_id, content_data in data.items():
        # Reference the Firestore document
        doc_ref = db.collection('cache').document(article_id)
        # Add the set operation to the batch
        batch.set(doc_ref, content_data)
        counter += 1

        # Commit the batch if it reaches the batch size limit
        if counter >= batch_size:
            batch.commit()
            batch = db.batch()  # Start a new batch
            counter = 0

    # Commit any remaining writes in the final batch
    if counter > 0:
        batch.commit()


async def fetch(session, url):
    async with session.get(url) as response:
        return await response.text()

async def fetch_json(session, url):
    async with session.get(url) as response:
        return await response.json()

async def scrape_article(session, article_url, title, img_url, time, publisher, womens):
    article_id = article_url[-8:]
    cached_data = check_if_data_cached(article_id)

    if cached_data:
        return {
            'title': cached_data['title'],
            'article_content': cached_data['content'],
            'img_url': img_url,
            'article_url': article_url,
            'article_id': article_id,
            'time': time,
        }

    article_response = await fetch(session, f"https://onefootball.com/{article_url}")
    article_soup = BeautifulSoup(article_response, 'html.parser')

    paragraph_divs = article_soup.find_all('div', class_='ArticleParagraph_articleParagraph__MrxYL')
    text_elements, attribution = extract_text_with_spacing(str(paragraph_divs))

    if not text_elements:
        return None

    text_rephrased = response(unidecode(text_elements))
    text_rephrased = re.sub(r'[\n/]', '', text_rephrased)

    title_rephrased = responsetitle(title)
    title_rephrased = title_rephrased.replace(r"\\",'')
    add_data(article_id, text_rephrased, title_rephrased)

    womenswords = [
        'WSL', "Women", "Women's", "Womens", "women", "female", "ladies", "girls", "nwsl", "fa wsl", "female football",
        "mujer", "damas", "femme", "calcio femminile", "football féminin", "fußball frauen", "she", "her", "w-league"
    ]
    if womens is False and (contains_word_from_list(text_rephrased, womenswords) or contains_word_from_list(img_url, womenswords)):
        return None

    return {
        'title': title_rephrased,
        'article_content': text_rephrased,
        'img_url': img_url,
        'article_url': article_url,
        'article_id': article_id,
        'time': time,
    }

async def scrape_news_items(team, before_id, needbeforeid, womens):
    news_items = []
    async with aiohttp.ClientSession() as session:
        url = f'https://api.onefootball.com/web-experience/en/team/{team}/news'
        if needbeforeid:
            url += f'?before_id={before_id}'

        response = await fetch_json(session, url)
        containers = response.get('containers', [])
        teasers = containers[3].get('fullWidth', {}).get('component', {}).get('gallery', {}).get('teasers', []) if not before_id else response.get('teasers', [])
        teasers += containers[5].get('fullWidth', {}).get('component', {}).get('gallery', {}).get('teasers', []) or []

        tasks = []
        for teaser in teasers:
            image = extract_actual_url(urllib.parse.unquote(teaser['imageObject']['path']))
            if not image:
                continue
            image = image[:-12]
            tasks.append(scrape_article(
                session,
                article_url=teaser['link'],
                title=teaser['title'],
                img_url=image,
                time=teaser['publishTime'],
                publisher=teaser['publisherName'],
                womens=womens
            ))

        results = await asyncio.gather(*tasks)
        news_items.extend(filter(None, results))

        last_id = teasers[-1]['id'] if teasers else None
        return news_items, last_id

# Flask routes
@app.route('/scrape', methods=['GET'])
async def scrape():
    url = request.args.get('url')
    womens = request.args.get('womens', 'False') == 'True'
    before_id = request.args.get('before_id')

    if not url:
        return jsonify({'error': 'URL is required'}), 400

    team = url[32:-5]
    needbeforeid = bool(before_id)
    news_items, last_id = await scrape_news_items(team, before_id, needbeforeid, womens)

    return jsonify({
        'news_items': news_items,
        'last_id': last_id
    })

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
