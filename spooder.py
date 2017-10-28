from urllib import parse
from bs4 import BeautifulSoup
from time import sleep
from multiprocessing import Pool, Manager
from pathlib import Path
from sys import setrecursionlimit, getrecursionlimit
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
        manager = Manager()
        self.__domains = domains
        self.__curdomain = None
        self.__cururl = None
        self.__queue = []
        self.__visited = []
        self.__trash = manager.dict()
        self.__avg_stored = {'count': 0, 'avg': 0}
        self.__scrub = False

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
        if link.startswith('/') or not link.startswith('http'):
            return parse.urljoin(self.__cururl, link)
        elif link.startswith('http'):
            return link
        else:
            return None

    def _trash(self, url, size):
        if url not in self.__trash:
            self.__trash[url] = size
        with open('dumpster.txt', 'a') as d:
            d.write('{}, {}\n'.format(url, size))

    def _collect(self, url):
        self.__cururl = url
        self.__visited.append(url)
        logger.info('Visiting {}'.format(url), extra={'pid': os.getpid()})

        r = requests.get(url)
        soup = BeautifulSoup(r.content, 'lxml')

        for link in soup.find_all('a', href=True):
            self._add_to_queue(self._parse(link['href']))

        # for img in soup.find_all('img'):
        #     self._process_img(img)

        with Pool() as sp:
            print('Pool initiated.')
            apply = [sp.apply_async(self._process_img, (img,)) for img in soup.find_all('img')]
            for s_worker in apply:
                s_worker.get()

    def _process_img(self, img):
        target = None
        if img['src'] is None:
            return

        img_src = img['src']

        url = self._parse(img_src)

        if url in self.__trash:
            return

        img_fetch = requests.get(url, stream=True)

        filename = get_file_name_from_request(img_fetch)
        if filename in os.listdir(self.__curdomain.split('.')[0]):
            try:
                os.remove('{}/{}'.format(self.__curdomain.split('.')[0], filename))
                logger.info('Removed {}'.format(filename), extra={'pid': os.getpid()})
                self._trash(url, img_fetch.headers['content-length'])
            except Exception as e:
                logger.info(e)
            return

        if img_fetch.status_code != 200:
            return

        if not target:
            target = img_fetch

        if int(target.headers['content-length']) < int(img_fetch.headers['content-length']):
            target.close()
            target = img_fetch

        self._add_size(target.headers['content-length'])
        self._save_img(target)

    def _save_img(self, target_conn):
        if target_conn:
            fname = '{}/{}'.format(self.__curdomain.split('.')[0], get_file_name_from_request(target_conn))
            if not Path(fname).is_file():
                with open(fname, 'wb') as f:
                    for chunk in target_conn.iter_content():
                        f.write(chunk)

                logger.info('{} saved!'.format(fname), extra={'pid': os.getpid()})
            else:
                logger.info('{} already exists.'.format(fname), extra={'pid': os.getpid()})
            target_conn.close()

    def _work(self, task):
        setrecursionlimit(2**14)
        logger.info('Worker starting, recursion limit: {}'.format(getrecursionlimit()), extra={'pid': os.getpid()})
        self.__curdomain = task[1]
        self.__queue.append(task[0])

        try:
            os.makedirs(self.__curdomain.split('.')[0])
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise

        while len(self.__queue) > 0:
            self._collect(self.__queue.pop(0))
            sleep(3)
        logger.info('Queue empty #########################', extra={'pid': os.getpid()})

    def run(self):
        apply = [threading.Thread(target=self._work, kwargs={'task': d}).start() for d in self.__domains]

        print(apply)
