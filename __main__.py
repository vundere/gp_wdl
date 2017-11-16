from spooder import ComicSpider


def load_source():
    result = []
    with open('source.txt', 'r') as src:
        for line in src.readlines():
            url = line.split(',')
            result.append((url[0], url[1].strip()))
    return result


def main():
    domains = load_source()
    print('Domains loaded, starting spider...')
    cs = ComicSpider(domains)
    cs.run()


if __name__ == '__main__':
    main()
