from urllib import parse
from bs4 import BeautifulSoup
from time import sleep
from multiprocessing import Pool
from pathlib import Path
from sys import setrecursionlimit, getrecursionlimit
from requests.exceptions import ConnectionError
import threading
import requests
import os
import errno
import logging


def get_file_name_from_request(req):
    try:
        url = req.url
        parsed_url = parse.urlsplit(url)
        return os.path.basename(parsed_url.path)
    except AttributeError as e:
        logger.info(e,  extra={'pid': os.getpid()})
        return None


def content_length(req):
    try:
        res = req.headers['content-length']
        # logger.info('Content length from header: {}'.format(res),  extra={'pid': os.getpid()})
    except KeyError:
        res = len(req.content)
        # logger.info('Content length from content: {}'.format(res),  extra={'pid': os.getpid()})
    return res


def create_logger():
    lg = logging.getLogger(__name__)
    lg.setLevel(logging.INFO)
    fhandler = logging.FileHandler(filename='gp_wdl.log', encoding='utf-8', mode='a')
    shandler = logging.StreamHandler()
    fmt = logging.Formatter('[%(asctime)s]:%(pid)s: %(message)s', datefmt='%H:%M:%S')
    fhandler.setFormatter(fmt)
    shandler.setFormatter(fmt)
    lg.addHandler(fhandler)
    lg.addHandler(shandler)
    return lg


logger = create_logger()


class ComicSpider(object):
    def __init__(self, domains):
        self.__domains = domains
        self.__curdomain = None
        self.__cururl = None
        self.__queue = []
        self.__visited = []
        self.__trash = {}
        self.__avg_stored = {'count': 0, 'avg': 0}

    def _add_to_queue(self, url):
        if (url not in self.__visited) and (url not in self.__queue) and (self.__curdomain in url):
            self.__queue.append(url)

    def _add_size(self, size):
        size = int(size)
        count = int(self.__avg_stored['count'])
        avg = int(self.__avg_stored['avg'])
        try:
            self.__avg_stored = {'count': count + 1, 'avg': (avg+size) / count + 1}
        except ZeroDivisionError:
            self.__avg_stored = {'count': 1, 'avg': size}

    def _parse(self, link):
        if '#' in link:
            return None
        elif link.startswith('/') or not link.startswith('http'):
            return parse.urljoin(self.__cururl, link)
        elif link.startswith('http'):
            return link
        else:
            return None

    def _trash(self, url, size, filename):
        if url not in self.__trash:
            self.__trash[url] = {'size': size, 'filename': filename}
        with open('dumpster.txt', 'a') as d:
            d.write('{}, {}\n'.format(url, size))

    def _clean(self):
        for item in self.__trash.values():
            if item['size'] < (self.__avg_stored['size']/3):
                filename = item['filename']
                try:
                    os.remove('{}/{}/{}'.format('comics', self.__curdomain.split('.')[0], filename))
                    logger.info('Removed {}'.format(filename), extra={'pid': os.getpid()})
                except Exception as e:
                    logger.info(e)

    def _collect(self, url):
        self.__cururl = url
        self.__visited.append(url)
        logger.info('Visiting {}'.format(url), extra={'pid': os.getpid()})

        try:
            r = requests.get(url)
        except ConnectionError:
            return
        soup = BeautifulSoup(r.content, 'lxml')

        for link in soup.find_all('a', href=True):
            self._add_to_queue(self._parse(link['href']))

        for img in soup.find_all('img'):
            threading.Thread(target=self._process_img, kwargs={'img': img}).start()

    def _process_img(self, img):
        # TODO refactor into something more concise
        target = None
        if img['src'] is None:
            return

        img_src = img['src']

        url = self._parse(img_src)

        if url in self.__trash:
            return

        img_fetch = requests.get(url, stream=True)

        filename = get_file_name_from_request(img_fetch)
        if filename in os.listdir('comics/'+self.__curdomain.split('.')[0]):
            self._trash(url, content_length(img_fetch), filename)
            return

        if img_fetch.status_code != 200:
            return

        if not target:
            target = img_fetch

        if int(content_length(target)) < int(content_length(img_fetch)):
            target.close()
            target = img_fetch

        self._add_size(content_length(target))
        self._save_img(target)

    def _save_img(self, target_conn):
        # TODO locks
        if target_conn:
            fname = '{}/{}/{}'.format('comics', self.__curdomain.split('.')[0], get_file_name_from_request(target_conn))
            if not Path(fname).is_file():
                with open(fname, 'wb') as f:
                    for chunk in target_conn.iter_content():
                        f.write(chunk)

                logger.info('{} saved!'.format(fname), extra={'pid': os.getpid()})
            else:
                logger.info('{} already exists.'.format(fname), extra={'pid': os.getpid()})
            target_conn.close()

    def _work(self, task):
        setrecursionlimit(2**12)
        logger.info('Worker starting, recursion limit: {}'.format(getrecursionlimit()), extra={'pid': os.getpid()})
        self.__curdomain = task[1]
        self.__queue.append(task[0])

        try:
            os.makedirs('comics/'+self.__curdomain.split('.')[0])
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise

        while len(self.__queue) > 0:
            self._collect(self.__queue.pop(0))
            sleep(3)
        self._clean()
        logger.info('Worker finished #########################', extra={'pid': os.getpid()})

    def run(self):
        with Pool() as p:
            apply = [p.apply_async(self._work, (d,)) for d in self.__domains]
            res = [w.get() for w in apply]

        print(apply)
