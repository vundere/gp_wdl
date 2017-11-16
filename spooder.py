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
import re


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


def domain_safeguard(check_url, domain_url):
    # TODO test this for edge cases, may be too broad of a check
    common = ['com', 'org', 'net']
    check_components = check_url.split('.')
    domain_components = domain_url.split('.')

    for c_comp, d_comp in zip(check_components, domain_components):

        if c_comp in common:
            check_components.remove(c_comp)

        if d_comp in common:
            domain_components.remove(d_comp)

    for comp in check_components:
        if comp in domain_components:
            return True
    return False


def create_logger():
    lg = logging.getLogger(__name__)
    lg.setLevel(logging.DEBUG)

    fhandler = logging.FileHandler(filename='gp_wdl.log', encoding='utf-8', mode='a')
    shandler = logging.StreamHandler()
    fhandler.setLevel(logging.DEBUG)
    shandler.setLevel(logging.INFO)

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

    @property
    def _comic_dir_content(self):
        return os.listdir('comics/' + self.__curdomain.split('.')[0])

    @property
    def _comic_dir(self):
        return '/'.join(['comics', self.__curdomain.split('.')[0]])

    def _add_to_queue(self, url):
        if not url:
            return
        elif (url not in self.__visited) and (url not in self.__queue) and (self.__curdomain in url):
            logger.debug('Adding {} to queue.'.format(url), extra={'pid': os.getpid()})
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
        logger.debug('Parsing {}'.format(link), extra={'pid': os.getpid()})

        result = None

        if '#' in link:
            return None
        elif link.startswith('/') or not link.startswith('http'):
            result = parse.urljoin(self.__cururl, link)
        elif link.startswith('http'):
            result = link

        logger.debug('Parsed result: {}'.format(result), extra={'pid': os.getpid()})
        return result

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
            logger.debug('Could not connect to {}, stopping.'.format(url), extra={'pid': os.getpid()})
            return

        soup = BeautifulSoup(r.content, 'lxml')

        for meta in soup.find_all('meta', attrs={'http-equiv': re.compile("^refresh", re.I)}):
            try:
                refresh_url = meta['content'].split('=')[1]
                if refresh_url:
                    return self._collect(refresh_url)
            except KeyError:
                pass

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

        if filename in self._comic_dir_content:
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
        if target_conn:
            fname = '{}/{}'.format(self._comic_dir, get_file_name_from_request(target_conn))
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
            os.makedirs(self._comic_dir)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise

        while len(self.__queue) > 0:
            self._collect(self.__queue.pop(0))
            sleep(1.5)

        self._clean()

        logger.info('Worker finished #########################', extra={'pid': os.getpid()})

    def run(self):
        logger.debug('Spider starting...', extra={'pid': os.getpid()})
        targets = [self.__domains[x:x+4] for x in range(0, len(self.__domains), 4)]
        with Pool() as p:
            for subset in targets:
                apply = [p.apply_async(self._work, (d,)) for d in subset]
                res = [w.get(timeout=15) for w in apply]
