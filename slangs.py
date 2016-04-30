import csv
import urllib2
from lxml import etree

slugs = ['1', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm',
        'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z']

#slugs = ['1']

base_url = 'http://www.noslang.com/dictionary/'


hdr = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.11 (KHTML, like Gecko) Chrome/23.0.1271.64 Safari/537.11',
       'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
       'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.3',
       'Accept-Encoding': 'none',
       'Accept-Language': 'en-US,en;q=0.8',
       'Connection': 'keep-alive'
}

url_list = []
for slug in slugs:
    url_list.append(base_url + slug)

for url in url_list:
    request = urllib2.Request(url, headers=hdr)
    r = urllib2.urlopen(request)
    htmlparser = etree.HTMLParser()
    tree = etree.parse(r, htmlparser)
    slang = tree.xpath('//a/@name')
    slang = slang[1:]
    meaning = tree.xpath('//abbr/@title')
    #slang_meaning = dict(zip(slang, meaning))
    slang_meaning = []
    for i in range(len(slang)):
        d = {'slang': slang[i], 'meaning': meaning[i]}
        slang_meaning.append(d)

    with open('slangs_meaning.csv', 'a') as sm:
        field_names = ['slang', 'meaning']
        writer = csv.DictWriter(sm, fieldnames=field_names)
        writer.writeheader()
        for j in slang_meaning:
            writer.writerow(j)
