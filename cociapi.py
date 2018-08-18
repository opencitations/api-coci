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
from rdflib.namespace import RDF, OWL, Namespace
from re import sub


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
    base_api_url = "https://doi.org/"
    rdf_format = "application/rdf+xml"

    # doi, reference, citation_count
    header = res[0]
    doi_field = header.index("doi")
    additional_fields = ["author", "year", "title", "source_title", "volume", "issue", "page"]

    header.extend(additional_fields)

    for row in res[1:]:
        citing_doi = row[doi_field][1]

        try:
            r = get(base_api_url + citing_doi,
                    headers={"Accept": rdf_format,
                             "User-Agent": "COCI REST API (via OpenCitations - "
                                           "http://opencitations.net; mailto:contact@opencitations.net)"}, timeout=30)
            if r.status_code == 200:
                g = Graph()
                g.parse(data=r.text, format=rdf_format)
                __add_data(row, g, additional_fields)
            else:
                row.extend([""] * len(additional_fields))  # empty list
        except Exception as e:
            raise e
            row.extend([""] * len(additional_fields))  # empty list

    return res


def __add_data(row, g, additional_fields):
    res = None
    if len(list(g.triples((None, URIRef("http://prismstandard.org/namespaces/basic/2.1/doi"), None)))):
        res = __crossref_parser(g)
    elif len(list(g.triples((None, RDF.type, URIRef("http://schema.org/ScholarlyArticle"))))):
        res = __datacite_parser(g)

    if res is None or len(res) == 0:
        row.extend([""] * len(additional_fields))  # empty list
    else:
        row.extend([str(item) if item is not None else "" for item in res[0]])


def __crossref_parser(g):
    return list(g.query("""
        PREFIX foaf: <http://xmlns.com/foaf/0.1/>
        PREFIX dcterms: <http://purl.org/dc/terms/>
        PREFIX prism: <http://prismstandard.org/namespaces/basic/2.1/>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        SELECT DISTINCT ?author ?year ?title ?source_title ?volume ?issue ?page
        WHERE {
            ?article prism:doi ?string_doi .
            {
                SELECT ?article (GROUP_CONCAT(?name; separator="; ") as ?author) {
                    {
                        SELECT ?article ?fn ?gn ?orcid {
                            ?article dcterms:creator ?a .
                            ?a foaf:familyName ?fn ;
                                foaf:givenName ?gn .
                            OPTIONAL {
                                ?a owl:sameAs ?another_a .
                                BIND(STRAFTER(str(?another_a), "http://orcid.org/") as ?orcid)   
                            }
                        } ORDER BY ?article ?fn ?gn
                    }
                    
                    BIND(CONCAT(?fn, ", ", ?gn, IF(bound(?orcid), CONCAT(", ", ?orcid), "")) as ?name)
                } GROUP BY ?article
            }
            OPTIONAL { 
                ?article dcterms:date ?date .
                BIND(SUBSTR(str(?date), 1, 4) as ?year)
            }
            OPTIONAL { ?article dcterms:title ?title }
            OPTIONAL { ?article dcterms:isPartOf / dcterms:title ?source_title }
            OPTIONAL { ?article prism:volume ?volume }
            OPTIONAL { ?article prism:issueIdentifier ?issue }
            OPTIONAL {
                ?article prism:startingPage ?sp .
                OPTIONAL { ?article prism:endingPage ?ep }
                BIND(CONCAT(?sp, IF(bound(?ep), CONCAT("-", ?ep), "")) as ?page)
            }
        }"""))


def __datacite_parser(g):
    return list(g.query("""
        PREFIX schema: <http://schema.org/>
        SELECT DISTINCT ?author ?year ?title ?source_title ?volume ?issue ?page
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
        }"""))
