from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
import requests
import urllib.parse


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
                all_paragraph_texts = []
                for div in paragraph_divs:
                    p_tags = div.find_all('p')
                    for p in p_tags:
                        all_paragraph_texts.append(p.get_text(strip=True))

                # Print the extracted text
                for idx, text in enumerate(all_paragraph_texts, 1):
                    newscontents.append(text.text())
            
                    
               

            news_items.append({
                'title': title,
                'article_content': newscontents,
                'img_url': img_url,
                'article_url': article_url,
                
            })

        return jsonify(news_items)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
