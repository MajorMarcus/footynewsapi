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
            subtitle = article.find('p', class_='NewsTeaser_teaser__preview__ZRFyi').text
            img_tag = article.find('img', class_='ImageWithSets_of-image__img__pezo7 teaser__img')
            img_url = img_tag['src'] if img_tag else None
            img_url =img_url
            img_url = urllib.parse.unquote(img_url)
            img_url = extract_actual_url(img_url)
            news_items.append({
                'title': title,
                'subtitle': subtitle,
                'img_url': img_url
            })

        return jsonify(news_items)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
