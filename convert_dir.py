#!/usr/bin/env python
# This is based on work by huntingb. https://github.com/huntingb/gemtext-html-converter
import os
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
  <meta name=viewport content="width=device-width, initial-scale=1">
  <style>body {font-family:sans-serif;max-width:40em;margin:auto;} html {overflow-y:scroll;}
  @media (max-width:50rem) {body {margin:0px 20px;}}</style>
</head>
<body>
<p>This page is an HTML mirror of the <a href="%%fn%%">original gemini page</a>.</p><hr>
%%body%%
</body>
</html>
"""
ROOT_URL = "gemini://halfbigdata.eu:47060/"


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
                href, inner = inner.split(maxsplit=1)
                # links to local gemini files should be converted to the corresponding html
                if href.endswith(".gmi") and not (
                    href.startswith("http://") or href.startswith("gemini://") or href.startswith("/")
                ):
                    href = href[:-4] + ".html"
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


def process_dir(path):
    # don't use template.format, because HTML contains so many curly braces
    template = HTML.split("%%")
    indexmapper = {"title": None, "body": None, "fn": None}
    for i, tl in enumerate(template):
        if tl in indexmapper:
            indexmapper[tl] = i
    for fn in os.listdir(path):
        if not fn.endswith(".gmi"):
            continue
        # read the whole file into memory
        # in the old days this would have been sacrilege, but memory abounds and Python instructions are expensive
        with open(os.path.join(path, fn), "r") as fileobj:
            gemtext = fileobj.read()
        title, htmllines = convert_gemtext(gemtext.splitlines())
        # destructively update template (because why not, it's not like we are doing concurrency)
        template[indexmapper["title"]] = title or "(untitled)"
        template[indexmapper["fn"]] = ROOT_URL + fn
        template[indexmapper["body"]] = "\n".join(htmllines)
        # likewise, write out the whole HTML file at once
        with open(os.path.join(path, fn[:-4] + ".html"), "w") as fileobj:
            fileobj.write("".join(template))
        sys.stderr.write(f"done processing: {fn}\n")


if __name__ == "__main__":
    process_dir("." if len(sys.argv) < 2 else sys.argv[1])
