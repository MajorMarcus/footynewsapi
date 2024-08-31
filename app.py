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

async def scrape_news_items(team):
    news_items = []
    async with aiohttp.ClientSession() as session:
        for j in range(20):
            response = await fetch_json(session, f'https://api.onefootball.com/web-experience/en/team/{team}/news')
            containers = response.get('containers', [])

            for teasers in [containers[3]['fullWidth']['component']['gallery']['teasers'], containers[5]['fullWidth']['component']['gallery']['teasers']]:
                tasks = []
                for i, teaser in enumerate(teasers):
                    link = teaser['link']
                    title2 = teaser['title']
                    image = extract_actual_url(urllib.parse.unquote(teaser['imageObject']['path']) if teaser['imageObject']['path'] else "")

                    tasks.append(scrape_article(session, link, title2, image))

                    if i == 5 and teasers is containers[5]['fullWidth']['component']['gallery']['teasers']:
                        lasturl = teaser['id']
                        more_news_response = await fetch_json(session, f'https://api.onefootball.com/web-experience/en/team/{team}/news?before_id={lasturl}')
                        more_teasers = more_news_response.get('teasers', [])
                        tasks.extend(scrape_article(session, t['link'], t['title'], extract_actual_url(urllib.parse.unquote(t['imageObject']['path']) if t['imageObject']['path'] else "")) for t in more_teasers)
                
                results = await asyncio.gather(*tasks)
                news_items.extend(filter(None, results))
            break
    return news_items

@app.route('/scrape', methods=['GET'])
async def scrape():
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'URL is required'}), 400

    team = url[32:-5]
    news_items = await scrape_news_items(team)
    return jsonify(news_items)

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)

