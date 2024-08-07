from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
import requests
import urllib.parse
from unidecode import unidecode


def get_image_height(url):
    # Fetch the image
    response = requests.get(url)
    if response.status_code == 200:
        # Open the image
        img = Image.open(BytesIO(response.content))
        # Return the height
        return img.height
    else:
        raise Exception(f"Failed to retrieve image from {url}. Status code: {response.status_code}")

def extract_text_with_spacing(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    text_elements = []
    
    for p in soup.find_all('p'):
        # Get text from each paragraph, handling href links
        paragraph_text = []
        for element in p.children:
            if element.name == 'a':
                # Handle links: include text before and after links
                paragraph_text.append(element.get_text())
            elif element.name is None:  # It's a NavigableString
                paragraph_text.append(element.strip())
        
        text_elements.append(' '.join(paragraph_text))
    s = ''
    text_elements = s.join(text_elements)
    return text_elements

def join_text_elements(text_elements):
    # Join the text elements with a space between them
    return ' '.join(text_elements).strip()

def decode(text):
    text1= text.encode('utf-8').decode('unicode_escape')
    text2 = text1.encode('latin1')
    return text2


def extract_actual_url(url):
    # Find the position where the actual image URL starts
    key = "image="
    start = url.find(key)
    if start == -1:
        return None

    # Extract the part after 'image='
    encoded_url = url[start + len(key):]

    # Decode the URL-encoded string
    actual_url = urllib.parse.unquote(encoded_url)
    
    return actual_url


app = Flask(__name__)

@app.route('/scrape', methods=['GET'])

def scrape():
    url = request.args.get('url')

    if not url:
        return jsonify({'error': 'URL is required'}), 400

    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        

        news_items = []

        for article in soup.find_all('article', class_='NewsTeaser_teaser__BR1_B'):
            title = article.find('p', class_='NewsTeaser_teaser__title__OsMxr').text
            img_tag = article.find('img', class_='ImageWithSets_of-image__img__pezo7 teaser__img')
            img_url = img_tag['src'] if img_tag else None
            img_url = urllib.parse.unquote(img_url) if img_url else None
            img_url = extract_actual_url(img_url) if img_url else None
            imgheight = get_img_height(img_url)

            # Extract the link to the full article
            article_link_tag = article.find('a', href=True)
            article_url = article_link_tag['href'] if article_link_tag else None
            
            # Fetch and parse the full article content if the URL is found
            article_content = 'No Content'
            if article_url:
                article_response = requests.get(f"https://onefootball.com/{article_url}")
                article_soup = BeautifulSoup(article_response.text, 'html.parser')
               
                # Adjust the class name based on the actual structure of the full article page
                newscontents = []
                
                i = article_soup.find('div', class_='XpaLayout_xpaLayoutContainerGridItemComponents__MaerZ')
                paragraph_divs = article_soup.find_all('div', class_='ArticleParagraph_articleParagraph__MrxYL')
                if paragraph_divs:
                    text_elements = extract_text_with_spacing(str(paragraph_divs))
                    
            text_elements = unidecode(text_elements)
                    
               

            news_items.append({
                'title': title,
                'article_content': text_elements,
                'img_url': img_url,
                'img_height': img_height
                'article_url': article_url,
                
            })

        return jsonify(news_items)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
