#!/usr/bin/env python3

from plexapi.server import PlexServer
from getpass import getpass
from argparse import ArgumentParser
import requests
from lxml import html as lhtml
import os
import sys

#import tvdb_v4_official as tvdb

def get_token():
    plextkf = os.environ.get("PLEXTKF")
    plextk = os.environ.get("PLEXTK")
    if plextk:
        return plextk
    elif plextkf:
        return open(plextkf).read().split('\n')[0]
    else:
        tk = getpass("Token:")
        if not tk:
            print("Couldn't find a token. Exiting")
            sys.exit(0)

        return tk


def cache_exists(tmdbid):
    return os.path.exists(f"{cachedir}/tmdb-{tmdbid}")


parser = ArgumentParser()
parser.add_argument("--plex", "-P", help="HOST:PORT", required=True, metavar="HOST:PORT")
parser.add_argument("--ipy", help="Run ipython at the end")

args = parser.parse_args()

baseurl = f'http://{args.plex}'

plex = PlexServer(baseurl, get_token())

mydir = f'{os.environ.get("HOME")}/.plextool'
cachedir = f'{mydir}/cache'

if not os.path.exists(cachedir):
    os.makedirs(cachedir)

shows = plex.library.section("TV Shows").all()

while True:

    try:
        next_show = shows.pop(0)
        #print("Next?", next_show.title)
    except IndexError as e:
        # No more items
        sys.exit(0)

    #tvdburi = next(( x for x in next_show.guids if x.id.startswith("tvdb") ))
    try:
        tmdburi = next(( x for x in next_show.guids if x.id.startswith("tmdb") ))
    except StopIteration as e:
        # Not available
        print(f"No tmdb for {next_show.title}: {next_show.guids}")
        continue

    tmdbid = int(tmdburi.id.split("/")[-1])

    cachefile = f"{cachedir}/tmdb-{tmdbid}"

    if not os.path.exists(cachefile):
        break

print(f"Title: {next_show.title}")
#print(f"TVDB: {tvdburi}")
print(f"TMDB: {tmdburi}")

if not os.path.exists(cachefile):
    r = requests.get(f"https://www.themoviedb.org/tv/{tmdbid}/seasons")
    with open(cachefile, "wb") as f:
        f.write(r.text.encode("utf8"))

    html = lhtml.document_fromstring(r.text)
else:
    text = open(cachefile).read()
    html = lhtml.document_fromstring(text)

season_wrappers = html.xpath('//div[contains(@class, "season_wrapper")]')

for season in season_wrappers:
    season_strip = [ x.strip() for x in season.text_content().split("\n") ]
    season_strip = [ x for x in season_strip if x ]

    print(season_strip[0:2])

#print([ x.strip() for x in html.xpath('//div[contains(@class, "season_wrapper")]')[1].text_content().split('\n') if x.strip()][0:2])
#['Day 1', '2001 | 24 Episodes']

if args.ipy:
    import IPython; IPython.embed()
