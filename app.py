from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
import aiohttp
import asyncio
import urllib.parse
from unidecode import unidecode

app = Flask(__name__)


async def fetch(session, url):
    async with session.get(url) as response:
        return await response.text()

async def fetch_json(session, url):
    async with session.get(url) as response:
        return await response.json()

def extract_text_with_spacing(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    return ' '.join(
        ' '.join(element.get_text().strip() for element in p.children if element.name in ['a', None])
        for p in soup.find_all('p')
    )

def extract_actual_url(url):
    key = "image="
    start = url.find(key)
    if start == -1:
        return None
    return urllib.parse.unquote(url[start + len(key):]).replace('width=720', '')

async def scrape_article(session, article_url, title, img_url):
    if article_url:
        article_response = await fetch(session, f"https://onefootball.com/{article_url}")
        article_soup = BeautifulSoup(article_response, 'html.parser')
        paragraph_divs = article_soup.find_all('div', class_='ArticleParagraph_articleParagraph__MrxYL')
        text_elements = extract_text_with_spacing(str(paragraph_divs)) if paragraph_divs else ""
        return {
            'title': title,
            'article_content': unidecode(text_elements),
            'img_url': img_url,
            'article_url': article_url,
        }
    return None

async def scrape_news_items(team, before_id, needbeforeid):
    news_items = []
    async with aiohttp.ClientSession() as session:
        url = f'https://api.onefootball.com/web-experience/en/team/{team}/news'
        if needbeforeid:
            url += f'?before_id={before_id}'

        response = await fetch_json(session, url)
        containers = response.get('containers', [])

        teasers = []
        if before_id:
            teasers = response.get('teasers')
        else:
            if len(containers) > 3:
                teasers = containers[3].get('fullWidth', {}).get('component', {}).get('gallery', {}).get('teasers', [])
            
            if len(containers) > 5:
                teasers += containers[5].get('fullWidth', {}).get('component', {}).get('gallery', {}).get('teasers', [])

        tasks = []
        last_id = None
        for teaser in teasers:
            link = teaser['link']
            title2 = teaser['title']
            image = extract_actual_url(urllib.parse.unquote(teaser['imageObject']['path']) if teaser['imageObject']['path'] else "")
            image = remove_after_jpg(image)
            last_id = teaser['id']

            tasks.append(scrape_article(session, link, title2, image))

        results = await asyncio.gather(*tasks)
        news_items.extend(filter(None, results))

    return news_items, last_id

@app.route('/scrape', methods=['GET'])
async def scrape():
    url = request.args.get('url')
    before_id = request.args.get('before_id')# Fetch the 'before_id' from the query parameters if provided
    if not url:
        return jsonify({'error': 'URL is required'}), 400

    team = url[32:-5]
    needbeforeid = False
    if before_id:
        needbeforeid = True
    news_items, last_id = await scrape_news_items(team, before_id, needbeforeid=needbeforeid)
    return jsonify({
        'news_items': news_items,
        'last_id': last_id  # Return the last ID so it can be used for the next page
    })

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)

