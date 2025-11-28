#!/usr/bin/env python3

from http.server import HTTPServer as BaseHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone
from functools import partial
import sqlite3
import html
import time
import sys
import os
import re

# http://base/?min=1996-12-19T16:40:00&max=1996-12-19T16:50:05
base = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Firefox Places Server</title></head>
<body>
<form action="/" method="GET">

<div>
<label for="tag">Tag: </label>
<input id="tag" name="tag" type="text" value="{tag}">
</div>

<div>
<label for="min">Beginning date and time: </label>
<input id="min" name="min" type="datetime-local" value="{mindef}" required step=1>
</div>

<div>
<label for="max">Ending date and time: </label>
<input id="max" name="max" type="datetime-local" value="{maxdef}" required step=1>
</div>

<div>
<label for="title">Title regular expression: </label>
<input id="title" name="title" type="text" value="{treg}">
</div>

<div>
<label for="url">URL regular expression: </label>
<input id="url" name="url" type="text" value="{ureg}">
</div>

<div>
<input type="submit" value="Submit">
</div>

</form>
<p><a href="/">Reset all filters</a></p>
{res}
</body>
"""


queryByTag = '''SELECT i.id,title,url,dateAdded,lastModified
    FROM moz_bookmarks b
    JOIN
      (SELECT p.id, p.url
          FROM moz_places p
          JOIN moz_bookmarks b
          WHERE b.parent = :tagid AND p.id = b.fk) i
    WHERE i.id = b.fk AND title NOT NULL'''


queryTagId = "SELECT id FROM moz_bookmarks WHERE parent = 4 AND title = :tag"


queryByAdded = '''SELECT i.id,title,url,dateAdded,lastModified
    FROM moz_bookmarks b
    JOIN
      (SELECT p.id, p.url
          FROM moz_places p
          JOIN moz_bookmarks b
          WHERE p.id = b.fk) i
    WHERE i.id = b.fk AND (b.dateAdded BETWEEN :beg AND :end) AND title NOT NULL'''


queryByTagAndAdded = '''SELECT i.id,title,url,dateAdded,lastModified
    FROM moz_bookmarks b
    JOIN
      (SELECT p.id, p.url
          FROM moz_places p
          JOIN moz_bookmarks b
          WHERE b.parent = :tagid AND p.id = b.fk) i
    WHERE i.id = b.fk AND (b.dateAdded BETWEEN :beg AND :end) AND title NOT NULL'''


queryByTitleRegexAndAdded = '''SELECT i.id,title,url,dateAdded,lastModified
    FROM moz_bookmarks b
    JOIN
      (SELECT p.id, p.url
          FROM moz_places p
          JOIN moz_bookmarks b
          WHERE p.id = b.fk) i
    WHERE i.id = b.fk AND (b.dateAdded BETWEEN :beg AND :end) AND title NOT NULL AND (b.title REGEXP :regex)'''


queryByUrlRegexAndAdded = '''SELECT i.id,title,url,dateAdded,lastModified
    FROM moz_bookmarks b
    JOIN
      (SELECT p.id, p.url
          FROM moz_places p
          JOIN moz_bookmarks b
          WHERE p.id = b.fk) i
    WHERE i.id = b.fk AND (b.dateAdded BETWEEN :beg AND :end) AND title NOT NULL AND (b.url REGEXP :regex)'''


queryByTitleAndUrlRegexAndAdded = '''SELECT i.id,title,url,dateAdded,lastModified
    FROM moz_bookmarks b
    JOIN
      (SELECT p.id, p.url
          FROM moz_places p
          JOIN moz_bookmarks b
          WHERE p.id = b.fk) i
    WHERE i.id = b.fk AND (b.dateAdded BETWEEN :beg AND :end) AND title NOT NULL AND (b.title REGEXP :tregex) AND (b.url REGEXP :uregex)'''


queryByTitleRegexAndTagAndAdded = '''SELECT i.id,title,url,dateAdded,lastModified
    FROM moz_bookmarks b
    JOIN
      (SELECT p.id, p.url
          FROM moz_places p
          JOIN moz_bookmarks b
          WHERE b.parent = :tagid AND p.id = b.fk) i
    WHERE i.id = b.fk AND (b.dateAdded BETWEEN :beg AND :end) AND title NOT NULL AND (b.title REGEXP :regex)'''


queryByUrlRegexAndTagAndAdded = '''SELECT i.id,title,url,dateAdded,lastModified
    FROM moz_bookmarks b
    JOIN
      (SELECT p.id, p.url
          FROM moz_places p
          JOIN moz_bookmarks b
          WHERE b.parent = :tagid AND p.id = b.fk) i
    WHERE i.id = b.fk AND (b.dateAdded BETWEEN :beg AND :end) AND title NOT NULL AND (b.url REGEXP :regex)'''


queryByTitleAndUrlRegexAndTagAndAdded = '''SELECT i.id,title,url,dateAdded,lastModified
    FROM moz_bookmarks b
    JOIN
      (SELECT p.id, p.url
          FROM moz_places p
          JOIN moz_bookmarks b
          WHERE b.parent = :tagid AND p.id = b.fk) i
    WHERE i.id = b.fk AND (b.dateAdded BETWEEN :beg AND :end) AND title NOT NULL AND (b.title REGEXP :tregex) AND (b.url REGEXP :uregex)'''


queryTagsByBookmark = '''SELECT id,title
    FROM moz_bookmarks b
    JOIN
      (SELECT parent FROM moz_bookmarks WHERE fk = :bmid) i
    WHERE b.parent = 4 AND b.id = i.parent'''


def parse_query(path):
    parsed = urlparse(path)
    query = parse_qs(parsed.query)
    return query


def parse_date(stamp):
    dt = datetime.fromisoformat(stamp)
    dt = dt.astimezone(tz=None)
    return int(dt.timestamp()) * 1000000


def make_date(stamp):
    return time.localtime(int(stamp) / 1000000)


def regex(expr, item):
    reg = re.compile(expr)
    return reg.search(item) is not None


def find_tags(db, bmid):
    res = []
    cursor = db.cursor()
    for row in cursor.execute(queryTagsByBookmark, ({"bmid": bmid})):
        res += [{"id": row[0], "tag": row[1]}]
    return res


def get_tagid(db, tag):
    cursor = db.cursor()
    cursor.execute(queryTagId, ({"tag": tag}))
    res = cursor.fetchone()
    if res:
        return res[0]
    return None


def get_bookmarks_by_added(db, beg, end):
    res = []
    cursor = db.cursor()
    for row in cursor.execute(queryByAdded, ({"beg": beg, "end": end})):
        res += [{"id": row[0], "title": row[1], "url": row[2], "added": make_date(row[3]), "modified": make_date(row[4])}]
    return res


def get_bookmarks_by_tag_and_added(db, beg, end, tagid):
    res = []
    cursor = db.cursor()
    for row in cursor.execute(queryByTagAndAdded, ({"tagid": tagid, "beg": beg, "end": end})):
        res += [{"id": row[0], "title": row[1], "url": row[2], "added": make_date(row[3]), "modified": make_date(row[4])}]
    return res


def get_bookmarks_by_title_regex_and_added(db, regex, beg, end):
    res = []
    cursor = db.cursor()
    for row in cursor.execute(queryByTitleRegexAndAdded, ({"regex": regex, "beg": beg, "end": end})):
        res += [{"id": row[0], "title": row[1], "url": row[2], "added": make_date(row[3]), "modified": make_date(row[4])}]
    return res


def get_bookmarks_by_url_regex_and_added(db, regex, beg, end):
    res = []
    cursor = db.cursor()
    for row in cursor.execute(queryByUrlRegexAndAdded, ({"regex": regex, "beg": beg, "end": end})):
        res += [{"id": row[0], "title": row[1], "url": row[2], "added": make_date(row[3]), "modified": make_date(row[4])}]
    return res


def get_bookmarks_by_title_and_url_regex_and_added(db, tregex, uregex, beg, end):
    res = []
    cursor = db.cursor()
    for row in cursor.execute(queryByTitleAndUrlRegexAndAdded, ({"tregex": tregex, "uregex": uregex, "beg": beg, "end": end})):
        res += [{"id": row[0], "title": row[1], "url": row[2], "added": make_date(row[3]), "modified": make_date(row[4])}]
    return res


def get_bookmarks_by_title_regex_and_tag_and_added(db, regex, tagid, beg, end):
    res = []
    cursor = db.cursor()
    for row in cursor.execute(queryByTitleRegexAndTagAndAdded, ({"regex": regex, "beg": beg, "end": end, "tagid": tagid})):
        res += [{"id": row[0], "title": row[1], "url": row[2], "added": make_date(row[3]), "modified": make_date(row[4])}]
    return res


def get_bookmarks_by_url_regex_and_tag_and_added(db, regex, tagid, beg, end):
    res = []
    cursor = db.cursor()
    for row in cursor.execute(queryByUrlRegexAndAdded, ({"regex": regex, "beg": beg, "end": end, "tagid": tagid})):
        res += [{"id": row[0], "title": row[1], "url": row[2], "added": make_date(row[3]), "modified": make_date(row[4])}]
    return res


def get_bookmarks_by_title_and_url_regex_and_tag_and_added(db, tregex, uregex, tagid, beg, end):
    res = []
    cursor = db.cursor()
    for row in cursor.execute(queryByTitleAndUrlRegexAndAdded, ({"tregex": tregex, "uregex": uregex, "beg": beg, "end": end, "tagid": tagid})):
        res += [{"id": row[0], "title": row[1], "url": row[2], "added": make_date(row[3]), "modified": make_date(row[4])}]
    return res


def make_response(path, db_file, dbmin, dbmax):
    if "max" in path:
        title_re = ""
        url_re = ""
        tag = ""
        con = sqlite3.connect("file:{}?immutable=1".format(db_file))
        con.create_function("REGEXP", 2, regex)
        pquery = parse_query(path)
        lo = parse_date(pquery['min'][0])
        hi = parse_date(pquery['max'][0])
        if 'title' in pquery and len(pquery['title'][0]) > 0:
            title_re = pquery['title'][0]
        if 'url' in pquery and len(pquery['url'][0]) > 0:
            url_re = pquery['url'][0]
        if 'tag' in pquery and len(pquery['tag'][0]) > 0:
            tag = pquery['tag'][0]
        res = "<ol>\n"
        val = []
        if len(tag) == 0:
            if len(title_re) > 0 and len(url_re) > 0:
                val = get_bookmarks_by_title_and_url_regex_and_added(con, title_re, url_re, lo, hi)
            elif len(title_re) > 0 and not len(url_re) > 0:
                val = get_bookmarks_by_title_regex_and_added(con, title_re, lo, hi)
            elif not len(title_re) > 0 and len(url_re) > 0:
                val = get_bookmarks_by_url_regex_and_added(con, url_re, lo, hi)
            else:
                val = get_bookmarks_by_added(con, lo, hi)
        else:
            tagid = get_tagid(con, tag)
            if len(title_re) > 0 and len(url_re) > 0:
                val = get_bookmarks_by_title_and_url_regex_and_tag_and_added(con, title_re, url_re, lo, hi, tagid)
            elif len(title_re) > 0 and not len(url_re) > 0:
                val = get_bookmarks_by_title_regex_and_tag_and_added(con, title_re, lo, hi, tagid)
            elif not len(title_re) > 0 and len(url_re) > 0:
                val = get_bookmarks_by_url_regex_and_tag_and_added(con, url_re, lo, hi, tagid)
            else:
                val = get_bookmarks_by_tag_and_added(con, lo, hi, tagid)
        for row in val:
            tags = find_tags(con, row['id'])
            title = html.escape(row['title'])
            url = row['url'].replace('"', '%22')
            added = time.strftime("%A, %B %d, %Y %T %z", row['added'])
            modified = time.strftime("%A, %B %d, %Y %T %z", row['modified'])
            resline = "{} ({}) &mdash; <a href=\"{}\">{}</a>".format(added, modified, url, title)
            if tags:
                resline += " ("
                for tag in tags:
                    resline += "<a href=\"/?hi={}&lo={}&tag={}\">{}</a> ".format(lo, hi, tag['tag'].replace(" ", "+"), html.escape(tag['tag']))
                resline += ")"
            res += "<li>{}</li>\n".format(resline)
        res += "</ol>"
        con.close()
        return base.format(res=res, mindef=pquery['min'][0], maxdef=pquery['max'][0], treg=html.escape(title_re), ureg=html.escape(url_re), tag=html.escape(tag))
    else:
        return base.format(res="", mindef=dbmin, maxdef=dbmax, treg="", ureg="", tag="")


class HTTPHandler(BaseHTTPRequestHandler):
    def __init__(self, db_file, min, max, *args, **kwargs):
        self.db_file = db_file
        self.min = min
        self.max = max
        super().__init__(*args, **kwargs)
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(make_response(self.path, self.db_file, self.min, self.max).encode())


class HTTPServer(BaseHTTPServer):
    def __init__(self, server_address, RequestHandlerClass=HTTPHandler):
        BaseHTTPServer.__init__(self, server_address, RequestHandlerClass)


if len(sys.argv) == 1:
    print("Usage: {} places.sqlite".format(sys.argv[0]))
    sys.exit(0)


db_file = os.path.abspath(sys.argv[1])
con = sqlite3.connect("file:{}?immutable=1".format(db_file))
cur = con.cursor()
cur.execute("SELECT MIN(dateAdded), MAX(dateAdded) FROM moz_bookmarks")
res = cur.fetchone()
con.close()
min = time.strftime("%Y-%m-%dT%H:%M:%S", make_date(res[0]))
max = time.strftime("%Y-%m-%dT%H:%M:%S", make_date(res[1]))
handler = partial(HTTPHandler, db_file, min, max)
httpd = HTTPServer(("", 8090), RequestHandlerClass=handler)
httpd.serve_forever()
