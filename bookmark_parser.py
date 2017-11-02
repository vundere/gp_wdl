from bs4 import BeautifulSoup
from urllib.parse import urlparse

BM_FILE = "bookmark_source.html"


def find():
    result = []
    with open(BM_FILE, 'r') as source:
        soup = BeautifulSoup(source, 'lxml')
        for obj in soup.find_all('a', href=True):
            link = obj['href']
            if link not in result:
                domain = urlparse(link).netloc
                result.append((link, domain.replace('www.', '')))
    return result


def output(indata):
    with open('source.txt', 'w') as src:
        for dat in indata:
            src.write('{},{}\n'.format(dat[0], dat[1]))


if __name__ == '__main__':
    bookmark_links = find()
    output(bookmark_links)
