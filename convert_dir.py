#!/usr/bin/env python
# This is based on work by huntingb. https://github.com/huntingb/gemtext-html-converter
import datetime
from email.utils import format_datetime
import os
import re
import sys

TAGS_DICT = {
    "# ": "<h1>{inner}</h1>",
    "## ": "<h2>{inner}</h2>",
    "###": "<h3>{inner}</h3>",
    "* ": "<li>{inner}</li>",
    "> ": "<blockquote>{inner}</blockquote>",
    "=>": '<li><a href="{href}">{inner}</a></li>',
}
DEFAULT = "<p>{inner}</p>"
HTML = \
r"""<!DOCTYPE HTML>
<html>
<head>
  <meta charset="UTF-8">
  <title>%%title%%</title>
  <link rel="alternate" type="application/rss+xml" title="rss" href="rss.xml">
  <meta name=viewport content="width=device-width, initial-scale=1">
  <style>body {font-family:sans-serif;max-width:40em;margin:auto;} html {overflow-y:scroll;}
  @media (max-width:50rem) {body {margin:0px 20px;}}</style>
</head>
<body>
<p>This page is an HTML mirror of the <a href="%%gem_root_url%%%%fn%%">original gemini page</a>.</p><hr>
%%body%%
<hr>
<p>Subscribe to my <a href="rss.xml">RSS feed</a>.</p>
</body>
</html>
"""
POST_TIME = " 12:00:00 +01:00"
DATE_REGEX = re.compile(r"^\d\d\d\d-\d\d-\d\d")
# rss is generated from index.gmi
RSS = \
r"""<rss version="2.0"><channel>
<title>%%title%%</title><link>%%http_root_url%%</link>
<description></description>
%%items%%
</channel></rss>
"""
RSS_ITEM = \
"""
<item><title>%%title%%</title><link>%%http_root_url%%%%fn%%</link><pubDate>%%date%%</pubDate></item>
"""
GEM_ROOT_URL = "gemini://halfbigdata.eu:47060/"
HTTP_ROOT_URL = "http://halfbigdata.eu/"


class TemplateProcessor(object):
    # don't use str.format, because HTML contains so many curly braces
    def __init__(self, template, defaults=None, delimiter="%%"):
        self.mapper = {}
        self.components = template.split(delimiter)
        # so, components now alternates between literal text and variable names
        # variables are on even indices if the template starts with delimiter
        variable_parity = int(not template.startswith(delimiter))
        for idx, tl in enumerate(self.components):
            if idx & 1 != variable_parity:
                continue
            self.mapper[tl] = idx

    def substitute(self, **value_mapping):
        for key, value in value_mapping.items():
            idx = self.mapper.get(key)
            if idx is None:
                continue
            self.components[idx] = value

    def realize(self, **value_mapping):
        # destructively update template (because why not, it's not like we are doing concurrency)
        self.substitute(**value_mapping)
        sys.stderr.write(f"{self.mapper} {value_mapping}")
        return "".join(self.components)


def convert_gem_link(meat):
    # `meat` is the gemtext link line without the prefix "=>"
    href, inner = [x.strip() for x in meat.split(maxsplit=1)]
    # links to local gemini files should be converted to the corresponding html
    if href.endswith(".gmi") and not (
        href.startswith("http://") or href.startswith("gemini://") or href.startswith("/")
    ):
        href = href[:-4] + ".html"
    return href, inner


def convert_gemtext(lines):
    title = None

    def generate_html():
        nonlocal title
        in_list = False
        preformat = False
        for gmi_line in lines:
            if gmi_line.startswith("```"):
                preformat = not preformat
                yield ("</pre>", "<pre>")[int(preformat)]
                continue
            if preformat:
                yield gmi_line
                continue
            # skip empty line except in preformat
            if not gmi_line:
                continue
            href = None
            pattern = TAGS_DICT.get(gmi_line[:2])
            if not pattern:
                pattern = TAGS_DICT.get(gmi_line[:3])
                if not pattern:
                    pattern = DEFAULT
                    inner = gmi_line.strip()
                else:
                    inner = gmi_line[3:].strip()
            else:
                inner = gmi_line[2:].strip()
            if "{href}" in pattern:
                href, inner = convert_gem_link(inner)
            if not title and "<h1>" in pattern:
                title = inner
            if ("<li>" in pattern) != in_list:
                in_list = not in_list
                yield ("</ul>", "<ul>")[int(in_list)]
            yield pattern.format(inner=inner, href=href)
        if in_list:
            yield "</ul>"

    # sure, it's a bit perverse... title is set by generate_html, so we have to call this first
    htmllines = list(generate_html())
    return title, htmllines


def convert_gemtext_to_rss_items(gem_lines, rss_item_template):
    # separate processing (redundant, if you will) of index.gmi for rss.xml
    # but: separation of concerns
    for line in gem_lines:
        if not line.startswith("=>"):
            continue
        href, inner = convert_gem_link(line[2:])
        m = DATE_REGEX.match(inner)
        iso_date = m.group() if m else "2022-02-22"
        title = inner[m.span()[1]:].strip() if m else inner
        # convert ISO date to this nonsense RFC format (why, oh why)
        sys.stderr.write(f"{datetime.datetime.fromisoformat(iso_date + POST_TIME)}\n")
        date = format_datetime(datetime.datetime.fromisoformat(iso_date + POST_TIME))
        yield rss_item_template.realize(title=title, date=date, fn=href)


def process_dir(path):
    html_template = TemplateProcessor(HTML)
    rss_template = TemplateProcessor(RSS)
    rss_item_template = TemplateProcessor(RSS_ITEM)
    for template in (html_template, rss_template, rss_item_template):
        template.substitute(gem_root_url=GEM_ROOT_URL, http_root_url=HTTP_ROOT_URL)
    for fn in os.listdir(path):
        if not fn.endswith(".gmi"):
            continue
        # read the whole file into memory
        # in the old days this would have been sacrilege, but memory abounds and Python instructions are expensive
        with open(os.path.join(path, fn), "r") as fileobj:
            gemtext = fileobj.read()
        gem_lines = gemtext.splitlines()
        title, html_lines = convert_gemtext(gem_lines)
        if not title:
            title = "(untitled)"
        html_text = html_template.realize(title=title, fn=fn, body="\n".join(html_lines))
        # likewise, write out the whole HTML file at once
        with open(os.path.join(path, fn[:-4] + ".html"), "w") as fileobj:
            fileobj.write(html_text)
        sys.stderr.write(f"done processing: {fn}\n")
        if fn == "index.gmi":
            rss_items = convert_gemtext_to_rss_items(gem_lines, rss_item_template)
            rss_text = rss_template.realize(title=title, items="\n".join(rss_items))
            with open(os.path.join(path, "rss.xml"), "w") as fileobj:
                fileobj.write(rss_text)
            sys.stderr.write(f"done writing rss.xml\n")


if __name__ == "__main__":
    process_dir("." if len(sys.argv) < 2 else sys.argv[1])
