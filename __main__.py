from spooder import ComicSpider


def main():
    domains = [
        ('http://www.eeriecuties.com/', 'eeriecuties.com'),
        ('http://www.gunnerkrigg.com/', 'gunnerkrigg.com')
    ]
    cs = ComicSpider(domains)
    cs.run()


if __name__ == '__main__':
    main()
