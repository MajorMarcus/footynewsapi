from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
import aiohttp
import asyncio
import urllib.parse
import sqlite3
from unidecode import unidecode
import os

from groq import Groq

client = Groq(
    api_key='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',
)


def response(cont):
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": """rephrase this text with similar wordcount. dont change out any of the names, football keywords related to transfers news or any playernames. u may change the structure of the sentence or switch out any arbitrary words that dont change the meaning of the sentence or the text in whole.just reply with the text and not anything other like here is the rephrased text with around the same word count. here's the text:
                """+"'"+cont+"'",
            }
        ],
        model="llama3-8b-8192",
    )

    return chat_completion.choices[0].message.content
DB_NAME = 'cache.db'

def initialize_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cache (
                article_id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                title TEXT NOT NULL
            )
        ''')
        conn.commit()

initialize_db()


# SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# SERVICE_ACCOUNT_FILE = 'credentials.json'

# SPREADSHEET_ID = '1fwIRN_OwAdZ59WU4_QsGNaSN7Yb4_ZxjnDhNRKx9wJ0'


# def checkifdatacached(article_id):
    
#     credentials = Credentials.from_service_account_file(
#         SERVICE_ACCOUNT_FILE, scopes=SCOPES)
#     service = build('sheets', 'v4', credentials=credentials)
    
    
#     result = (
#         service.spreadsheets()
#         .values()
#         .get(spreadsheetId=SPREADSHEET_ID, range='Sheet1!A:C').execute()
        
#     )
#     rows = result.get("values", [])
    
    
#     print(rows)
#     # Iterate through rows and find the desired article_id
#     for row in rows:
#         if row[0] == article_id:
#             if len(row) == 3:
#                 return [row[1], row[2]]
#             else:
#                return "Row doesn't have enough columns."


# def adddata(data):
#     credentials = Credentials.from_service_account_file(
#         SERVICE_ACCOUNT_FILE, scopes=SCOPES)
#     service = build('sheets', 'v4', credentials=credentials)
#     sheet = service.spreadsheets()
   
    
#     result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range='Sheet1!A:C', ).execute()
#     values = result.get('values', [])

#     first_empty_row = len(values) + 1

#     append_range = f'Sheet1!A{first_empty_row}:C'
#     body={
#     "values": [
#         data
#     ]
# }

    # Append the data to the sheet
    # response = sheet.values().append(
    #     spreadsheetId=SPREADSHEET_ID,
    #     range=append_range,
    #     valueInputOption='USER_ENTERED',
    #     body=body
    # ).execute()

    # print(f"Data added to range {response.get('tableRange')}.")
    # print(f"Updated cells: {response.get('updates').get('updatedCells')}")



app = Flask(__name__)

async def fetch(session, url):
    async with session.get(url) as response:
        return await response.text()

async def fetch_json(session, url):
    async with session.get(url) as response:
        return await response.json()
    

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

async def scrape_article(session, article_url, title, img_url, time, publisher, womens):
    if article_url:
        article_response = await fetch(session, f"https://onefootball.com/{article_url}")
        article_soup = BeautifulSoup(article_response, 'html.parser')
        article_id = article_url[-8:]
        cached_data = check_if_data_cached(article_id)

        txt = None  # Initialize txt with None to check later
        if cached_data:
            txt = cached_data[0]  # Cached content
        else:
            # Extract paragraph content if not cached
            paragraph_divs = article_soup.find_all('div', class_='ArticleParagraph_articleParagraph__MrxYL')
            textlist = extract_text_with_spacing(str(paragraph_divs))
            text_elements = textlist[0] if paragraph_divs else ""
            attribution = textlist[1]
            txt = unidecode(text_elements) if text_elements else None
            
            txt = response(txt)
            txt = txt.replace('/n', '').replace('/', '')
            txt = txt.replace('Here is the rephrased text:','')
            txt = txt.replace("Here is the rephrased text with similar word count:",'')
            txt = txt.replace('Here is the rephrased text with a similar word count:','')

            txt = txt.replace('\n','')

            if txt:  # Cache the data only if text was successfully extracted
                add_data(article_id, txt, title)

        if txt:
            womenswords = [
                'WSL', "Women", "Women's", "Womens", "women", "woman", "wsl", "female", "ladies", "girls", "feminine",
                "nwsl", "fa wsl", "female football", "mujer", "mujeres", "damas", "niñas", "femme", "calcio femminile",
                "football féminin", "fußball frauen", "ladies league", "she", "her", "w-league", "division féminine", "wcl", "nwcl"
            ]
            available = True
            contains_word_in_text = contains_word_from_list(txt, womenswords)
            contains_word_in_img = contains_word_from_list(img_url, womenswords)

            if womens is False:
                if contains_word_in_text or contains_word_in_img:
                    available = False

            if available:
                return {
                    'title': title,
                    'article_content': txt,
                    'img_url': img_url,
                    'article_url':article_url,
                    'article_id': article_id,
                    'time': time,
                }
            
        return None

def check_if_data_cached(article_id):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT content, title FROM cache WHERE article_id = ?", (article_id,))
        row = cursor.fetchone()
    return row  # Returns (content, title) if found, else None

def add_data(article_id, content, title):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO cache (article_id, content, title) VALUES (?, ?, ?)", (article_id, content, title))
        conn.commit()

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
