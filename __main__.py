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
    print('First line of domains is {}'.format(domains[0]))
    dec = input('Do you want to proceed?\n\t')
    if dec.lower() == 'y':
        cs = ComicSpider(domains)
        cs.run()
    else:
        return


if __name__ == '__main__':
    main()
