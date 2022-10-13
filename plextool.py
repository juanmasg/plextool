#!/usr/bin/env python3

from plexapi.server import PlexServer
from plexapi.exceptions import NotFound as PlexNotFound
from getpass import getpass
from argparse import ArgumentParser
import requests
from lxml import html as lhtml
import os
import sys
import re
import json

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

def get_show_tmdbid(plex_show):
    try:
        tmdburi = next(( s for s in plex_show.guids if s.id.startswith("tmdb") ))
    except StopIteration as si:
        # No tmdb uri associated
        return

    tmdbid = int(tmdburi.id.split("/")[-1])
    return tmdbid

def epstr(season, episode, eur=True):
    if eur:
        return f'{season}x{episode:02d}'
    else:
        return f's{season}e{episode:02d}'

class PlexWrapper:
    def __init__(self, host, port):
        self._host = host
        self._port = port

        self._plex = PlexServer(f"http://{host}:{port}", get_token())

    def shows(self, title_re=None):
        print("Retrieving all shows...")
        shows = self._plex.library.section("TV Shows").all()
        if title_re:
            print(f"Filtering shows matching '{title_re}'...")
            title_re = title_re.lower()
            return [ show for show in shows if re.search(title_re, show.title.lower()) ]

        return shows

    def get_show_seasons(self, plex_show):
        return { s.index: [e.index for e in s.episodes()] for s in plex_show.seasons() }


class TVDBScrapper():
    
    def __init__(self, basedir):
        pass
        self._cachedir = f"{basedir}/tvdb_cache"
        if not os.path.exists(self._cachedir):
            os.makedirs(self._cachedir)

    def get_show_seasons(self, plex_show):

        title = plex_show.originalTitle or plex_show.title
        cachedpath = f"{self._cachedir}/tvdb-{title}"

        if not os.path.exists(cachedpath):
            print(f"Retrieving from TVDB {title} to {cachedpath}")
            r = requests.get(f"https://thetvdb.com/series/{title.replace(' ', '-')}/")
            with open(cachedpath, "wb") as f:
                f.write(r.text.encode("utf8"))

        text = open(cachedpath).read()
        html = lhtml.document_fromstring(text)
        
        season_wrappers = html.xpath("//div[@id='tab-official']")[0].xpath(".//li[contains(@class, 'list-group-item')][@data-number]")
        seasons = {}

        for season_wrapper in season_wrappers:
            season_elems = [ x.strip() for x in season_wrapper.text_content().split('\n') if x.strip() ]
            season_epcount, season_name = season_elems[0:2]
            try:
                season_number = re.search('\d+', season_name).group(0)
            except Exception as e:
                # No season number
                continue

            seasons[int(season_number)] = int(season_epcount)

        return seasons

class TMDBScrapper():
    def __init__(self, basedir):
        pass
        self._cachedir = f"{basedir}/tmdb_cache"
        if not os.path.exists(self._cachedir):
            os.makedirs(self._cachedir)

    def get_show_seasons(self, plex_show):

        tmdbid = get_show_tmdbid(plex_show)
        if not tmdbid:
            return {}

        cachedpath = f"{self._cachedir}/tmdb-{tmdbid}"
        if not os.path.exists(cachedpath):
            print(f"Retrieving from TMDB {tmdbid} to {cachedpath}")
            r = requests.get(f"https://www.themoviedb.org/tv/{tmdbid}/seasons")
            with open(cachedpath, "wb") as f:
                f.write(r.text.encode("utf8"))
        
        text = open(cachedpath).read()
        html = lhtml.document_fromstring(text)
        
        season_wrappers = html.xpath('//div[contains(@class, "season_wrapper")]')
        seasons = {}

        for season_wrapper in season_wrappers:
            season_data = [ x.strip() for x in season_wrapper.text_content().split("\n") ]
            season_data = [ x for x in season_data if x ]

            if season_data[0].startswith("Specials"):
                continue

            season_epcount = re.search('(\d+) Episodes', season_data[1]).group(1)
            try:
                season_number = re.search('\d+', season_data[0]).group(0)
            except Exception as e:
                # No season number
                # FIXME: Match by title
                continue

            if not season_number:
                print("Ignoring season", season_data)
                continue

            seasons[int(season_number)] = int(season_epcount)
        
        return seasons


parser = ArgumentParser()
parser.add_argument("--plex", "-P", help="HOST:PORT", required=True, metavar="HOST:PORT")
parser.add_argument("--ipy", help="Run ipython at the end", action="store_true")
parser.add_argument("--int", "-I", help="Use internacional naming (e.g sXXeYY) ", action="store_true")
parser.add_argument("--list-shows", "-S", help="List all plex shows", action="store_true")
parser.add_argument("--tmdb", help="Check against tmdb", action="store_true")
parser.add_argument("--tvdb", help="Check against tvdb", action="store_true")
parser.add_argument("--diff", help="Print missing seasons/episodes", action="store_true")
parser.add_argument("--list", help="Print season information", action="store_true")
parser.add_argument("--report", help="Print completeness summary", action="store_true")
parser.add_argument("--title", "-t", help="Filter by title")

args = parser.parse_args()

plex = PlexWrapper(*args.plex.split(":"))

mydir = f'{os.environ.get("HOME")}/.plextool'

if not os.path.exists(mydir):
    os.makedirs(mydir)

db = None
if args.tmdb:
    db = TMDBScrapper(mydir)
elif args.tvdb:
    db = TVDBScrapper(mydir)

if args.list:
    if not db:
        print("Please enable `--tmdb` or `--tvdb`")
        sys.exit(1)

    for show in plex.shows(title_re=args.title):
        seasons = db.get_show_seasons(show)
        for index, epcount in seasons.items():
            print(f"{show.title} - Season {index: 2d} has {epcount: 3d} episodes")

elif args.diff:
    for show in plex.shows(title_re=args.title):
        db_seasons = db.get_show_seasons(show)
        plex_seasons = plex.get_show_seasons(show)

        all_seasons_ok = True

        for db_idx, db_epcount in db_seasons.items():
            if db_idx not in plex_seasons:
                print(f"{show.title} Season {db_idx} ({db_epcount}) is missing.")
                all_seasons_ok = False
                continue

            db_eps = list(range(1, db_epcount))

            plex_eps = plex_seasons[db_idx]
            #diff = db_eps - plex_eps
            diff = [ x for x in db_eps if x not in plex_eps ]
            if diff:
                missing = ", ".join([ epstr(db_idx, x, eur=not args.int) for x in diff])
                print(f"{show.title} Season {db_idx} missing {len(diff)}/{db_epcount} episodes: {missing}")
                all_seasons_ok = False
                continue

            print(f"{show.title} Season {db_idx} is complete ({db_epcount})")

elif args.report:
    for show in plex.shows(title_re=args.title):
        db_seasons = db.get_show_seasons(show)
        plex_seasons = plex.get_show_seasons(show)

        db_epcount = sum(db_seasons.values())
        plex_epcount = sum([len(x) for x in plex_seasons.values()])

        if db_epcount > 0:
            print(f"{show.title} completed status is {plex_epcount/db_epcount*100: 3.0f}%")
        else:
            print(f"{show.title} db_epcount is zero1 {db_seasons}")


elif args.list_shows:
    shows = plex.shows(title_re=args.title) #plex.library.section("TV Shows").all()
    for show in shows:
        print(f"{show.title} has {len(show.seasons())} seasons and {sum([ len(s.episodes()) for s in show.seasons() ])} episodes.")


if args.ipy:
    import IPython; IPython.embed()
