#!/usr/bin/env python

import os

import jinja2
from status import status

from baselayer.app.env import load_env
from baselayer.log import make_log

log = make_log("baselayer")


def md5sum(fn):
    import hashlib

    with open(fn, "rb") as f:
        file_hash = hashlib.md5()
        while chunk := f.read(8192):
            file_hash.update(chunk)
    return file_hash.hexdigest()


def version(module):
    import importlib

    m = importlib.import_module(module)
    return getattr(m, "__version__", "")


def hash_filter(string, htype):
    import hashlib

    h = hashlib.new(htype)
    h.update(string.encode("utf-8"))
    return h.hexdigest()


custom_filters = {"md5sum": md5sum, "version": version, "hash": hash_filter}


def fill_config_file_values(template_paths):
    log("Compiling configuration templates")
    env, cfg = load_env()

    for template_path in template_paths:
        with status(template_path):
            tpath, tfile = os.path.split(template_path)
            env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(tpath),
            )
            env.filters.update(custom_filters)
            template = env.get_template(tfile)
            rendered = template.render(cfg)

            with open(os.path.splitext(template_path)[0], "w") as f:
                f.write(rendered)
                f.write("\n")


if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser(description="Fill config file templates")
    parser.add_argument("template_paths", nargs="+")
    args, _ = parser.parse_known_args()
    fill_config_file_values(args.template_paths)
