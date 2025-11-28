#!/usr/bin/env python3

import os
import sys
import time
import sqlite3
import argparse

query = '''SELECT title,url,dateAdded,lastModified
    FROM moz_bookmarks b
    JOIN
      (SELECT p.id, p.url
          FROM moz_places p
          JOIN moz_bookmarks b
          WHERE b.parent = {} AND p.id = b.fk) i
    WHERE i.id = b.fk AND title NOT NULL'''


def get_tags(db):
    tags = []
    cursor = db.cursor()
    for row in cursor.execute('SELECT id,title FROM moz_bookmarks WHERE parent = 4'):
        tags += [(row[0], row[1])]
    return tags


def make_date(stamp):
    return time.localtime(int(stamp) / 1000000)


def get_bookmarks(db, tagid):
    res = []
    cursor = db.cursor()
    for row in cursor.execute(query.format(tagid)):
        res += [{"title": row[0], "url": row[1], "added": make_date(row[2]), "modified": make_date(row[3])}]
    return res


def get_by_tag(dbname, tag):
    res = []
    path = os.path.abspath(dbname)
    db = sqlite3.connect('file:{}?immutable=1'.format(path))
    tags = get_tags(db)
    id = None
    for (i, t) in tags:
        if t == tag:
            id = i
    if id:
        res = get_bookmarks(db, id)
    db.close()
    return res


def list_tags(dbname):
    path = os.path.abspath(dbname)
    db = sqlite3.connect('file:{}?immutable=1'.format(path))
    res = get_tags(db)
    db.close()
    return res


parser = argparse.ArgumentParser(description='Get A List Of Bookmarks Matching A Specific Tag')

parser.add_argument('-d', '--database', metavar='DATABASE', type=str, nargs=1, default='', help='Specify INFILE as Firefox places database file', required=True)
parser.add_argument('-t', '--tag', metavar='TAG', type=str, nargs=1, default='', help='Specify TAG as tag to match; omit for list of all tags')

args = parser.parse_args()

dbname = args.database[0]


if len(args.tag) == 0:
    for (i, t) in list_tags(dbname):
        print(t)
    sys.exit(0)


for row in get_by_tag(dbname, args.tag[0]):
    print("{}\t{}\t{}\t{}".format(row['title'], row['url'], time.strftime("%A, %B %d, %Y %T %z", row['added']), time.strftime("%A, %B %d, %Y %T %z", row['modified'])))

