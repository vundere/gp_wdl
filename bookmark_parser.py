from bs4 import BeautifulSoup
from urllib.parse import urlparse

BM_FILE = "bookmark_source.html"
SOURCE_FILE = 'source.txt'


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
    with open(SOURCE_FILE, 'w') as src:
        for dat in indata:
            src.write('{},{}\n'.format(dat[0], dat[1]))


def dedupe(sourcefile):
    with open(sourcefile, 'r+') as src:
        lines = src.readlines()
        newlines = []
        src.seek(0)
        src.truncate()
        for line in lines:
            if line not in newlines:
                newlines.append(line)
        for line in newlines:
            src.write(line)
