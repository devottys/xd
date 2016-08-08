# SQL based meta
import os.path
import codecs
from collections import Counter, namedtuple

from .html import mkhref, html_select_options
from .utils import COLSEP, EOL
from .xdfile import corpus

from xdfile import utils
import sqlite3


METADB = "meta.db" # SQLLite database
METADB_RECEIPTS = "receipts" # Receipts table

RECEIPTS_TSV = "gxd/receipts.tsv"
SIMILAR_TSV = "gxd/similar.tsv"
PUBLICATIONS_TSV = "gxd/publications.tsv"
PUZZLES_TSV = "pub/puzzles.tsv"
PUZZLE_SOURCES_TSV = "gxd/sources.tsv"
RECENT_DOWNLOADS_TSV = "gxd/recents.tsv"

# Initialize DB connection
sqlconn = sqlite3.connect(METADB)
sqlconn.row_factory = sqlite3.Row
cursor = sqlconn.cursor()
cursor.execute('PRAGMA journal_mode = MEMORY;')
sqlconn.commit()

class Error(Exception):
    pass


# Each delivery from an extractor should have a 'sources' table, to preserve the precise external sources.
xd_sources_header = [
        "ReceiptId",        # simple numeric row id (filled when approved)
        "SourceFilename",   # filename in the containing .zip; ideally referenceable by the ExternalSource
        "DownloadTime",     # '2016-04-11' (ISO8601; can be truncated)
        "ExternalSource",   # URL or email
    ]


# Each row from every 'sources' table appends an expanded version to the global 'receipts' table.
xd_receipts_header = [
        "CaptureTime",     # '2016-04-11' [as above, copied from xd-downloads.tsv]
        "ReceivedTime",     # '2016-04-14' [date of entry into receipts]
        "ExternalSource",   # URL or email [as above]
        "InternalSource",   # 'src/2016/xd-download-2016-04-11.zip'
        "SourceFilename",   # filename in the containing .zip [as above]
        "xdid"              # Shelf location (check log for error if empty)
    ]


xd_receipt = namedtuple('XDReceipt','CaptureTime, ReceivedTime, ExternalSource, InternalSource, SourceFilename, xdid')

# Each delivery from an extractor should have a 'sources' table, to preserve the precise external sources.
xd_recents_header = COLSEP.join([
        "pubid",
        "date",
    ]) + EOL


# xd-publications.tsv is curated manually or via some other process
xd_publications_header = COLSEP.join([
        "PublicationAbbr",  # 'nyt', should be unique across all publications; same as xdid prefix
        "PublisherAbbr",    # 'nytimes', toplevel directory (or 'self/quigley', or 'misc')
        "PublicationName",  # 'The New York Times'
        "PublisherName",    # 'New York Times Publishing Company'
        "FirstIssueDate",   # YYYY-MM-DD; empty if unknown
        "LastIssueDate",    # YYYY-MM-DD; empty if ongoing
        "NumberIssued",     # estimates allowed with leading '~'
    ]) + EOL

# xd-puzzles.tsv
# if ReceiptId's are preserved, generating a sorted list from all .xd files should result in an identical .tsv file.
xd_puzzles_header = COLSEP.join([
        "xdid",             # filename base ('nyt1994-10-02'), unique across all xd files
        "Date",             # '1994-10-02'
        "Size",             # '15x15'; append 'R' for rebus, 'S' for shaded squares
        "Title",            #
        "Author",           #
        "Editor",           #
        "Copyright",        #
        "A1_D1"             # a useful hash of the grid
    ]) + EOL


# yields dict corresponding to each row of receipts.tsv, in sequential order
@utils.memoize
def xd_receipts():
    return utils.parse_tsv(RECEIPTS_TSV, "Receipt")

@utils.memoize
def xd_receipts_rows():
    return utils.parse_tsv_rows(RECEIPTS_TSV, "Receipt")

@utils.memoize
def xd_publications():
    return utils.parse_tsv(PUBLICATIONS_TSV, "Publication")

@utils.memoize
def xd_puzzles():
    return utils.parse_tsv(PUZZLES_TSV, "Puzzle")

@utils.memoize
def xd_similar():
    return utils.parse_tsv(SIMILAR_TSV, "Similar")

@utils.memoize
def xd_puzzle_sources():
    return utils.parse_tsv(PUZZLE_SOURCES_TSV, "PuzzleSource")

def append_receipts(receipts):
    INS_TMPL = ",".join('?' * len(xd_receipt._fields))
    utils.debug('Going to insert %s rows' % len(receipts))
    cursor.executemany("INSERT INTO %s VALUES (%s)" % (METADB_RECEIPTS, INS_TMPL),receipts) 
    sqlconn.commit()

def append_receipt(receipt):
    INS_TMPL = ",".join('?' * len(xd_receipt._fields))
    r = [str(x) for x in receipt]
    utils.debug('INSERT %s' % ' '.join(r))
    cursor.execute("INSERT INTO %s VALUES (%s)" % (METADB_RECEIPTS, INS_TMPL),r)
    sqlconn.commit()

def append_row(tsvpath, headerstr, row, to_sql=False):
    if not to_sql:
        addhdr = not os.path.exists(tsvpath)

        fp = codecs.open(tsvpath, 'a', encoding='utf-8')
        if addhdr:
            fp.write(COLSEP.join(headerstr.split()) + EOL)

        fp.write(COLSEP.join([str(x) for x in row]) + EOL)
        fp.close()
    else:
        cur = sqlconn.cursor()
        #print(headerstr)
        INS_TMPL = ",".join('?' * len(COLSEP.split(headerstr)))
        #print(INS_TMPL)
        cur.execute("INSERT INTO %s VALUES (%s)" % (METADB_RECEIPTS, INS_TMPL),([str(x) for x in row]))
        sqlconn.commit()


def check_already_recieved(extsrc, srcfn):
    cursor.execute('SELECT * FROM %s WHERE ExternalSource="%s" AND SourceFilename="%s"' % (METADB_RECEIPTS, extsrc, srcfn))
    return [ i for i in map(xd_receipt._make, cursor.fetchall())]


def get_last_receipt_id():
   res = cursor.execute('SELECT MAX(ReceiptID) FROM %s' % METADB_RECEIPTS) 
   if res:
        return res.fetchone()[0]
   else:
        return 0

# for each row in fnDownloadZip:*.tsv, assigns ReceivedTime, and appends to receipts.tsv.  
def xd_receipts_row(CaptureTime="", ReceivedTime="", ExternalSource="", InternalSource="", SourceFilename="", xdid=""):
    return COLSEP.join([
        CaptureTime,
        ReceivedTime,
        ExternalSource,
        InternalSource,
        SourceFilename,
        xdid
    ]) + EOL


def xd_sources_row(SourceFilename, ExternalSource, DownloadTime):
    return COLSEP.join([
        "",  # ReceiptId
        SourceFilename,
        DownloadTime,
        ExternalSource
    ]) + EOL


def xd_recent_download(pubid, dt):
    return COLSEP.join([ pubid, dt ]) + EOL


def update_puzzles_row(xd):
    # INSERT only for now
    if xd.xdid() in xd_puzzles():
        raise Error('record already exists; UPDATE not implemented')

    fields = [
        xd.xdid(),                   # xdid
        xd.get_header("Date"),
        "%dx%d%s%s" % (xd.width(), xd.height(), xd.get_header("Rebus") and "R" or "", xd.get_header("Special") and "S" or ""),

        xd.get_header("Title"),
        xd.get_header("Author") or xd.get_header("Creator"),
        xd.get_header("Editor"),
        xd.get_header("Copyright"),
        "%s_%s" % (xd.get_answer("A1"), xd.get_answer("D1"))
    ]

    assert COLSEP not in "".join(fields), fields

    append_row(PUZZLES_TSV, xd_puzzles_header, fields)


class Publication:
    def __init__(self, pubid, row):
        self.pubid = pubid
        self.row = row


@utils.memoize
def get_similar_grids():
    '''returns dict of [xdid] -> set of matching xdid'''

    ret = {}
    for r in utils.parse_tsv('gxd/similar.tsv', 'Similar').values():
        matches = [ x.split('=') for x in r.matches.split() ]
        if matches:
            if r.xdid not in ret:
                ret[r.xdid.lower()] = set()

            ret[r.xdid.lower()] |= set(xdid.lower() for xdid, pct in matches)
            
            for xdid, pct in matches:
                if xdid not in ret:
                    ret[xdid.lower()] = set()

                ret[xdid.lower()].add(r.xdid.lower())

    return ret 

