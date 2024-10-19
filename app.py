from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
import aiohttp
import asyncio
from unidecode import unidecode
import re

import urllib

app = Flask(__name__)



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

async def fetch_html(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.text()

@app.route('/scrape', methods=['GET'])
async def scrape_article():
    article_url = request.args.get('url')
    full_article_url = 'https://onefootball.com/en/news/' + article_url
    if full_article_url:
        html_content = await fetch_html(full_article_url)
        article_soup = BeautifulSoup(html_content, 'html.parser')

        article_id = full_article_url[-8:]  # Extract the last 8 characters as article_id
        img_element = article_soup.find('img', class_='ImageWithSets_of-image__img__pezo7 ImageWrapper_media-container__image__Rd2_F')
        img_url = img_element['src'] if img_element else ''
        img_url = extract_actual_url(img_url)
        title_element = article_soup.find('span', class_="ArticleHeroBanner_articleTitleTextBackground__yGcZl")
        title = title_element.text.strip() if title_element else 'Title not found'

        time_element = article_soup.find('p', class_='title-8-regular ArticleHeroBanner_providerDetails__D_5AV')
        time_element = time_element.find_all('span')[1]
        time = time_element.text.strip() if time_element else 'Time not found'

        publisher_element = article_soup.find('p', class_='title-8-bold')
        publisher = publisher_element.text.strip() if publisher_element else 'Publisher not found'

        paragraph_divs = article_soup.find_all('div', class_='ArticleParagraph_articleParagraph__MrxYL')
        textlist = extract_text_with_spacing(str(paragraph_divs))
        text_elements = textlist[0] if paragraph_divs else ""
        attribution = textlist[1] if len(textlist) > 1 else ''

        return jsonify({
            'title': title,
            'article_content': unidecode(text_elements),
            'img_url': img_url,
            'article_url': full_article_url,
            'article_id': article_id,
            'time': time,
            'publisher': publisher,
            'attribution': attribution
        })

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
