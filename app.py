from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
import aiohttp
import asyncio
import urllib.parse
from unidecode import unidecode
import re

app = Flask(__name__)

async def fetch(session, url):
    async with session.get(url) as response:
        return await response.text()

async def fetch_json(session, url):
    async with session.get(url) as response:
        return await response.json()
    

def contains_word_from_list(text, word_list):
    # Split the text into words using regular expressions to handle punctuation
    words_in_text = re.findall(r'\b\w+\b', text.lower())  # Convert text to lowercase for case-insensitive matching
    word_list = [word.lower() for word in word_list]  # Convert word list to lowercase

    # Check if any word from word_list is present in words_in_text
    for word in word_list:
        if word in words_in_text:
            return True  # If any word is found, return True
    
    return False

def extract_text_with_spacing(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    imageattributions = []
    pattern = r"\(Photo by [^)]+\)"
    textelements = []
    attribution = False
    for p in soup.find_all('p'):
        text = p.get_text()
        text_without_attribution = re.sub(pattern, '', text).strip()
        textelements.append(text_without_attribution)
        
        match = re.search(pattern, text)
        if match:
            attribution = match.group()
    
    text = [' '.join(textelements), attribution]
    return text

def extract_actual_url(url):
    key = "image="
    start = url.find(key)
    if start == -1:
        return None
    if 'betting' in url or 'squawka' in url or "bit.ly" in url or "footballtoday.com" in url:
        return False 
    else:
        return urllib.parse.unquote(url[start + len(key):]).replace('width=720', '')

async def scrape_article(session, article_url, title, img_url, time, publisher, womens):
    if article_url:
        article_response = await fetch(session, f"https://onefootball.com/{article_url}")
        article_soup = BeautifulSoup(article_response, 'html.parser')
        article_id = article_url[-8:]
        paragraph_divs = article_soup.find_all('div', class_='ArticleParagraph_articleParagraph__MrxYL')
        textlist = extract_text_with_spacing(str(paragraph_divs))

        text_elements = textlist[0] if paragraph_divs else ""
        attribution = textlist[1]

        womenswords = [
            'WSL', "Women", "Women's", "Womens", "women", "woman", "wsl", "female", "ladies", "girls", "feminine",
            "nwsl", "fa wsl", "female football", "mujer", "mujeres", "damas", "niñas", "femme", "calcio femminile",
            "football féminin", "fußball frauen", "ladies league", "she", "her", "w-league", "division féminine","wcl","nwcl"
            # Add more women's related terms here
        ]

        available = True
        contains_word_in_text = contains_word_from_list(textlist[0], womenswords)
        contains_word_in_img = contains_word_from_list(img_url, womenswords)

        if womens is False:
            if contains_word_in_text or contains_word_in_img:
                available = False

        if available:
            return {
                'title': title,
                'article_content': unidecode(text_elements),
                'img_url': img_url,
                'article_url': article_url,
                'article_id': article_id,
                'time': time,
                'publisher': publisher,
                'attribution': attribution or ''
            }
        return None

async def scrape_news_items(team, before_id, needbeforeid, womens):
    news_items = []
    async with aiohttp.ClientSession() as session:
        url = f'https://api.onefootball.com/web-experience/en/team/{team}/news'
        if needbeforeid:
            url += f'?before_id={before_id}'

        response = await fetch_json(session, url)
        containers = response.get('containers', [])
        teasers = response.get('teasers') if before_id else containers[3].get('fullWidth', {}).get('component', {}).get('gallery', {}).get('teasers', [])
        try:
            teasers += containers[5].get('fullWidth', {}).get('component', {}).get('gallery', {}).get('teasers', [])
        except:
            pass                                
        tasks = []
        last_id = None
        for teaser in teasers:
            image = extract_actual_url(urllib.parse.unquote(teaser['imageObject']['path']) if teaser['imageObject']['path'] else "")
         
            if not image:
                continue
            else:
                image = image[:-12]
                link = teaser['link']
                title = teaser['title']
                time = teaser['publishTime']
                publisher = teaser['publisherName']
                last_id = teaser['id']

                tasks.append(scrape_article(session, article_url=link, title=title, img_url=image, time=time, publisher=publisher, womens=womens))
                
        results = await asyncio.gather(*tasks)
        news_items.extend(filter(None, results))

    return news_items, last_id

@app.route('/scrape', methods=['GET'])
async def scrape():
    url = request.args.get('url')
    womens = request.args.get('womens')
    
    womens = eval(womens)
    before_id = request.args.get('before_id')
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    print(url[32:-5])
    team = url[32:-5]

    needbeforeid = bool(before_id)
    news_items, last_id = await scrape_news_items(team, before_id, needbeforeid=needbeforeid, womens=womens)

    return jsonify({
        'news_items': news_items,
        'last_id': last_id
    })

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
