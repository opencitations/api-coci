#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2018, Silvio Peroni <essepuntato@gmail.com>
#
# Permission to use, copy, modify, and/or distribute this software for any purpose
# with or without fee is hereby granted, provided that the above copyright notice
# and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
# REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
# FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT,
# OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE,
# DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS
# ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS
# SOFTWARE.

__author__ = 'essepuntato'
from urllib.parse import quote, unquote
from requests import get
from rdflib import Graph, URIRef
from re import sub
from json import loads


def lower(s):
    return s.lower(),


def encode(s):
    return quote(s),


def decode_doi(res, *args):
    header = res[0]
    field_idx = []

    for field in args:
        field_idx.append(header.index(field))

    for row in res[1:]:
        for idx in field_idx:
            t, v = row[idx]
            row[idx] = t, unquote(v)

    return res


def split_dois(s):
    return "\"%s\"" % "\" \"".join(s.split("__")),


def metadata(res, *args):
    # doi, reference, citation_count
    header = res[0]
    doi_field = header.index("doi")
    additional_fields = ["author", "year", "title", "source_title", "volume", "issue", "page", "source_id"]

    header.extend(additional_fields)

    for row in res[1:]:
        citing_doi = row[doi_field][1]

        r = None
        for p in (__crossref_parser, __datacite_parser):
            if r is None:
                r = p(citing_doi)

        if r is None:
            row.extend([""] * len(additional_fields))  # empty list
        else:
            row.extend(r)

    return res


def __get_issn(body):
    cur_id = ""
    if "ISSN" in body and len(body["ISSN"]):
        cur_id = "; ".join("issn:" + cur_issn for cur_issn in body["ISSN"])
    return __normalise(cur_id)


def __get_isbn(body):
    cur_id = ""
    if "ISBN" in body and len(body["ISBN"]):
        cur_id = "; ".join("isbn:" + cur_issn for cur_issn in body["ISBN"])
    return __normalise(cur_id)


def __get_id(body, f_list):
    cur_id = ""
    for f in f_list:
        if cur_id == "":
            cur_id = f(body)
    return __normalise(cur_id)


def __create_title_from_list(title_list):
    cur_title = ""

    for title in title_list:
        strip_title = title.strip()
        if strip_title != "":
            if cur_title == "":
                cur_title = strip_title
            else:
                cur_title += " - " + strip_title

    return __normalise(cur_title.title())


def __normalise(s):
    return sub("\s+", " ", s).strip()


def __crossref_parser(doi):
    api = "https://api.crossref.org/works/%s"

    try:
        r = get(api % doi,
                headers={"User-Agent": "COCI REST API (via OpenCitations - "
                                       "http://opencitations.net; mailto:contact@opencitations.net)"}, timeout=30)
        if r.status_code == 200:
            json_res = loads(r.text)
            if "message" in json_res:
                body = json_res["message"]

                authors = []
                if "author" in body:
                    for author in body["author"]:
                        author_string = None
                        if "family" in author:
                            author_string = author["family"].title()
                            if "given" in author:
                                author_string += ", " + author["given"].title()
                                if "ORCID" in author:
                                    author_string += ", " + author["ORCID"].replace("http://orcid.org/", "")
                        if author_string is not None:
                            authors.append(__normalise(author_string))

                year = ""
                if "issued" in body and "date-parts" in body["issued"] and len(body["issued"]["date-parts"]) and \
                        len(body["issued"]["date-parts"][0]):
                    year = __normalise(str(body["issued"]["date-parts"][0][0]))

                title = ""
                if "title" in body:
                    title = __create_title_from_list(body["title"])

                source_title = ""
                if "container-title" in body:
                    source_title = __create_title_from_list(body["container-title"])

                volume = ""
                if "volume" in body:
                    volume = __normalise(body["volume"])

                issue = ""
                if "issue" in body:
                    issue = __normalise(body["issue"])

                page = ""
                if "page" in body:
                    page = __normalise(body["page"])

                source_id = ""
                if "type" in body:
                    if body["type"] == "book-chapter":
                        source_id = __get_isbn(body)
                    else:
                        source_id = __get_issn(body)
                else:
                    source_id = __get_id(body, [__get_issn, __get_isbn])

                return ["; ".join(authors), year, title, source_title, volume, issue, page, source_id]

    except Exception as e:
        pass  # do nothing


def __datacite_parser(doi):
    api = "https://doi.org/"
    rdf_format = "application/rdf+xml"

    try:
        r = get(api + doi,
                headers={"Accept": rdf_format,
                         "User-Agent": "COCI REST API (via OpenCitations - "
                                       "http://opencitations.net; mailto:contact@opencitations.net)"}, timeout=30)
        if r.status_code == 200:
            g = Graph()
            g.parse(data=r.text, format=rdf_format)
            res = list(g.query("""
                PREFIX schema: <http://schema.org/>
                SELECT DISTINCT ?author ?year ?title ?source_title ?volume ?issue ?page ?source_id
                WHERE {
                    ?article a schema:ScholarlyArticle .
                    
                    {   
                        SELECT ?article (GROUP_CONCAT(?name; separator="; ") as ?author) {
                            {
                                SELECT ?article ?fn ?gn ?orcid {
                                    ?article schema:author ?a .
                                    ?a schema:familyName ?fn ;
                                        schema:givenName ?gn .
                                    BIND(STRAFTER(str(?a), "https://orcid.org/") as ?orcid)
                                    BIND(CONCAT(?fn, ", ", ?gn, IF(bound(?orcid), CONCAT(", ", ?orcid), "")) as ?name)
                                } ORDER BY ?article ?fn ?gn
                            } 
                            BIND(CONCAT(?fn, ", ", ?gn, IF(bound(?orcid), CONCAT(", ", ?orcid), "")) as ?name)
                        } GROUP BY ?article
                    }
                    
                    OPTIONAL { ?article schema:name ?title }
                    OPTIONAL { 
                        ?article schema:datePublished ?date .
                        BIND(SUBSTR(str(?date), 1, 4) as ?year)
                    }
                    OPTIONAL { ?article schema:publisher/schema:name ?source_title }
                }"""))[0]

            return [str(item) if item is not None else "" for item in res]
    except Exception as e:
        pass  # no nothing


def oalink(res, *args):
    base_api_url = "https://api.unpaywall.org/v2/%s?email=contact@opencitations.net"

    # doi, reference, citation_count
    header = res[0]
    doi_field = header.index("doi")
    additional_fields = ["oa_link"]

    header.extend(additional_fields)

    for row in res[1:]:
        citing_doi = row[doi_field][1]

        try:
            r = get(base_api_url % citing_doi,
                    headers={"User-Agent": "COCI REST API (via OpenCitations - "
                                           "http://opencitations.net; mailto:contact@opencitations.net)"}, timeout=30)
            if r.status_code == 200:
                res_json = loads(r.text)
                if "best_oa_location" in res_json and res_json["best_oa_location"] is not None and \
                        "url" in res_json["best_oa_location"]:
                    row.append(res_json["best_oa_location"]["url"])
                else:
                    row.append("")  # empty element
            else:
                row.append("")  # empty element
        except Exception as e:
            row.append("")  # empty element

    return res
