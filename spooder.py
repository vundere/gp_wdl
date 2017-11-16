import threading
import requests
import os
import errno
import logging
import re

from urllib import parse
from bs4 import BeautifulSoup
from time import sleep
from multiprocessing import Pool
from pathlib import Path
from sys import setrecursionlimit, getrecursionlimit
from requests.exceptions import ConnectionError


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


def split(data, n):
    chunk_size = int(len(data)/n)
    output = [data[x:x+chunk_size] for x in range(0, len(data), chunk_size)]
    outlen = len(output)
    lastind = outlen - 1
    if outlen > n:
        while outlen > n:
            for subset in output[0:n-1]:
                outlen = len(output)
                try:
                    val = output[lastind].pop()
                    subset.append(val)
                except IndexError:
                    if outlen > n:
                        output.pop()
    return output


def create_logger():
    lg = logging.getLogger(__name__)
    lg.setLevel(logging.DEBUG)
    # fhandler = logging.FileHandler(filename='gp_wdl.log', encoding='utf-8', mode='a')
    shandler = logging.StreamHandler()
    # fhandler.setLevel(logging.DEBUG)
    shandler.setLevel(logging.INFO)
    fmt = logging.Formatter('[%(asctime)s]:%(pid)s: %(message)s', datefmt='%H:%M:%S')
    # fhandler.setFormatter(fmt)
    shandler.setFormatter(fmt)
    # lg.addHandler(fhandler)
    lg.addHandler(shandler)
    return lg


logger = create_logger()  # Created here for easier handling TODO less clumsy logging


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

    @property
    def _comic_name(self):
        return self.__curdomain.split('.')[0]

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
        result = None
        if '#' in link:
            return None
        elif link.startswith('/') or not link.startswith('http'):
            result = parse.urljoin(self.__cururl, link)
        elif link.startswith('http'):
            result = link
        return result

    def _trash(self, url, size, filename):
        if url not in self.__trash:
            self.__trash[url] = {'size': size, 'filename': filename}
            with open('dumpster.txt', 'a') as d:
                d.write('{}, {}\n'.format(url, size))

    def _clean(self):
        for item in self.__trash.values():
            os.makedirs('{}/{}'.format(self._comic_dir, 'trash'))
            if item['size'] < (self.__avg_stored['size']/3):
                filename = item['filename']
                try:
                    # Moves files instead of deleting them, to allow for manual inspection and deletion.
                    # os.remove('{}/{}/{}'.format('comics', self.__curdomain.split('.')[0], filename))
                    # logger.info('Removed {}'.format(filename), extra={'pid': os.getpid()})
                    os.rename(
                        '{}/{}'.format(self._comic_dir, filename),
                        '{}/{}/{}'.format(self._comic_dir, 'trash', filename)
                    )
                except Exception as e:
                    logger.info(e)
        if len(os.listdir(self._comic_dir)) == 0:
            os.remove(self._comic_dir)

    def _collect(self, url):
        self.__cururl = url
        self.__visited.append(url)
        logger.info('Visiting {}'.format(url), extra={'pid': os.getpid()})

        try:
            r = requests.get(url)
            if r.status_code != 200:
                raise ConnectionError
        except ConnectionError:
            logger.debug('Could not connect to {}, stopping.'.format(url), extra={'pid': os.getpid()})
            return

        soup = BeautifulSoup(r.content, 'lxml')

        for meta in soup.find_all('meta', attrs={'http-equiv': re.compile("^refresh", re.I)}):
            try:
                refresh_url = meta['content'].split('=')[1]
                if refresh_url:
                    self.__curdomain = parse.urlparse(refresh_url).netloc.replace('www.', '')
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

        try:
            self._save_img(target)
            logger.debug('{} saved!'.format(img_src), extra={'pid': os.getpid()})
        except PermissionError:
            logger.debug('ERROR!\n\tPermissionError saving {}'.format(img_src), extra={'pid': os.getpid()})

    def _save_img(self, target_conn):
        if target_conn:
            fname = '{}/{}'.format(self._comic_dir, get_file_name_from_request(target_conn))
            if not Path(fname).is_file():
                with open(fname, 'wb') as f:
                    f.write(target_conn.content)

                logger.info('{} saved!'.format(fname), extra={'pid': os.getpid()})
            else:
                logger.info('{} already exists.'.format(fname), extra={'pid': os.getpid()})
            target_conn.close()

    def _work(self, tasks):
        setrecursionlimit(2**12)
        for task in tasks:
            self.__avg_stored = {'count': 0, 'avg': 0}  # Reset to account for file size difference between comics
            self.__curdomain = task[1]
            self.__queue.append(task[0])

            try:
                os.makedirs(self._comic_dir)
                os.makedirs('logs')
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise

            logger.addHandler(logging.FileHandler(filename='logs/{}.log'.format(self._comic_name), encoding='utf-8'))
            logger.info('Worker starting, recursion limit: {}'.format(getrecursionlimit()), extra={'pid': os.getpid()})

            while len(self.__queue) > 0:
                self._collect(self.__queue.pop(0))
                sleep(1.5)

            self._clean()

            if len(os.listdir(self._comic_dir)) < len(self.__visited)/10:
                # An easy way of knowing which comics might have uncaught issues
                with open('concerns.txt', 'a') as f:
                    f.write('Low download amount for comic {}'.format(self._comic_name))

            logger.info('Task finished #########################', extra={'pid': os.getpid()})
        logger.info('Worker finished #########################', extra={'pid': os.getpid()})

    def run(self):
        # targets = [self.__domains[x:x+4] for x in range(0, len(self.__domains), 4)]
        targets = split(self.__domains, 4)
        # targets = [[self.__domains[0]]]  # Uncomment for single-site testing
        with Pool(processes=4) as p:
            for subset in targets:
                apply = [p.apply_async(self._work, (d,)) for d in subset]
                res = [w.get() for w in apply]
