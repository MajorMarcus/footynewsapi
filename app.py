from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
import aiohttp
import asyncio
import urllib.parse
import httpx
from unidecode import unidecode
import re
from groq import Groq
proxies = {
    "http://": "https://groqcall.ai/proxy/groq/v1",
}

# Custom client to handle proxy
class ProxyHttpxClient(httpx.Client):
    def __init__(self, proxies=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if proxies:
            self.proxies = proxies

client = Groq(
    api_key='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',
    http_client= ProxyHttpxClient(proxies=proxies)
)

def contains_word_from_list(text, word_list):
    # Split the text into words using regular expressions to handle punctuation
    words_in_text = re.findall(r'\b\w+\b', text.lower())  
    word_list = [word.lower() for word in word_list]  
    for word in word_list:
        if word in words_in_text:
            return True  
    
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



def batch_rephrase_titles(titles, batch_size=10):
    if not titles:
        return []
    titles_prompt = "\n".join([f"{i+1}. {title}" for i, title in enumerate(titles)])
    prompt = f"Rephrase the following football news article titles to 6-9 words each without changing their meaning:\n{titles_prompt}"
    
    for i in range(0, len(contents), batch_size):
        batch = contents[i:i + batch_size]
        batch_prompt = "\n".join([f"{j+1}. {content}" for j, content in enumerate(batch)])
        
        
        try:
            chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3-8b-8192",
            temperature=0,
            top_p=0,
    )
            batch_rephrased = chat_completion.choices[0].message.content.split("\n")
            batch_rephrased = [
                content.split(". ", 1)[-1]
                for content in batch_rephrased
                if ". " in content
            ]
            rephrased_titles.extend(batch_rephrased)
    return rephrased_titles
    
def batch_rephrase_content(contents, batch_size=3):
    """
    Rephrase article contents in batches to avoid character limitations.

    :param contents: List of article contents to rephrase.
    :param batch_size: Number of contents per batch.
    :return: List of rephrased article contents.
    """
    if not contents:
        return []
    
    rephrased_contents = []
    for i in range(0, len(contents), batch_size):
        batch = contents[i:i + batch_size]
        batch_prompt = "\n".join([f"{j+1}. {content}" for j, content in enumerate(batch)])
        prompt = (
            "Rephrase each of  the following football news articles' content into detailed summaries "
            "of 4-5 lines each. do not try to make it concise and give every detail but rephrase it to avoid recessive words and make it to the point while also providing an exact interpretation of what the article wanted to show, without changing names, keywords, or player names:\n"
            f"{batch_prompt}"
        )
        
        try:
            chat_completion = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama3-8b-8192",
                temperature=0,
                top_p=0,
            )
            batch_rephrased = chat_completion.choices[0].message.content.split("\n")
            batch_rephrased = [
                content.split(". ", 1)[-1]
                for content in batch_rephrased
                if ". " in content
            ]
            rephrased_contents.extend(batch_rephrased)
        except Exception as e:
            print(f"Error during rephrasing: {e}")
            rephrased_contents.extend(batch)  # Fallback to original content if rephrasing fails.

    return rephrased_contents

app = Flask(__name__)

async def fetch(session, url):
    async with session.get(url) as response:
        return await response.text()

async def fetch_json(session, url):
    async with session.get(url) as response:
        return await response.json()

async def scrape_article(session, article_url, title, img_url, time, publisher, womens):
    if article_url:
        article_response = await fetch(session, f"https://onefootball.com/{article_url}")
        article_soup = BeautifulSoup(article_response, 'html.parser')
        paragraph_divs = article_soup.find_all('div', class_='ArticleParagraph_articleParagraph__MrxYL')
        textlist = extract_text_with_spacing(str(paragraph_divs))
        text_elements = textlist[0] if paragraph_divs else ""
        attribution = textlist[1]
        
        womenswords = [
            'WSL', "Women", "Women's", "female", "ladies", "girls", "nwsl", "fa wsl"
        ]
        available = not (womens is False and (
            contains_word_from_list(textlist[0], womenswords) or contains_word_from_list(img_url, womenswords)
        ))
        if available:
            return {
                'title': title,
                'article_content': text_elements,
                'img_url': img_url,
                'article_url': article_url,
                'article_id':article_url[:-8],
                'time': time,
                'publisher': publisher,
                'attribution': attribution or '',
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
        titles = []
        contents = []
        for teaser in teasers:
            image = extract_actual_url(urllib.parse.unquote(teaser['imageObject']['path']) if teaser['imageObject']['path'] else "")
            
            if not image:
                continue
            image = image.replace('&q=25&w=1080','')
            link = teaser['link']
            title = teaser['title']
            time = teaser['publishTime']
            publisher = teaser['publisherName']
            titles.append(title)
            tasks.append(scrape_article(session, link, title, image, time, publisher, womens))

        articles = await asyncio.gather(*tasks)
        articles = [article for article in articles if article]
        
        # Batch rephrase titles and content
        rephrased_titles = batch_rephrase_titles([article['title'] for article in articles])
        rephrased_contents = batch_rephrase_content([article['article_content'] for article in articles])
        for i, article in enumerate(articles):
            article['title'] = rephrased_titles[i]
            article['article_content'] = rephrased_contents[i]

        news_items.extend(articles)

    return news_items, teasers[-1]['id'] if teasers else None

@app.route('/scrape', methods=['GET'])
async def scrape():
    url = request.args.get('url')
    womens = eval(request.args.get('womens', 'False'))
    before_id = request.args.get('before_id')
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    team = url[32:-5]
    needbeforeid = bool(before_id)
    news_items, last_id = await scrape_news_items(team, before_id, needbeforeid, womens)
    return jsonify({'news_items': news_items, 'last_id': last_id})

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
