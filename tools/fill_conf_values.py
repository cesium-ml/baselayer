#!/usr/bin/env python

import os
import subprocess

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


def nginx_brotli_installed():
    """Check if the nginx brotli module is installed

    Returns
    -------
    installed : bool
        True if the nginx brotli module is installed, False otherwise
    dynamic : bool
        True if the module is dynamically loaded, False otherwise
    modules_dir : str
        The directory where the nginx modules are located if dynamic loading is used
    """

    installed = False
    dynamic = False
    dir = None

    try:
        output = subprocess.check_output(
            ["nginx", "-V"], stderr=subprocess.STDOUT
        ).decode("utf-8")
        if (
            "--add-module" in output
            and "brotli" in output.split("--add-module")[1].strip()
        ):
            installed = True
        elif (
            "--add-dynamic-module" in output
            and "brotli" in output.split("--add-dynamic-module")[1].strip()
        ):
            installed = True
            dynamic = True
            # we try to figure out where the modules are, there are 2 possibilities
            # 1. the --modules-path directive is used
            # 2. the default directory is used, which is where the configuration file is located so we look for it
            if "--modules-path" in output:
                dir = output.split("--modules-path=")[1].split(" ")[0]
            elif "--conf-path" in output:
                dir = os.path.dirname(
                    output.split("--conf-path=")[1].split(" ")[0]
                ).replace("nginx.conf", "modules")
            if dir is not None and not os.path.isdir(dir):
                dir = None
            if dir is None:
                print(
                    "Brotli is installed dynamically, but couldn't find the nginx modules directory. Skipping."
                )
                installed = False
                dynamic = False
            else:
                dir = dir.rstrip("/")
    except subprocess.CalledProcessError:
        pass
    return installed, dynamic, dir


custom_filters = {"md5sum": md5sum, "version": version, "hash": hash_filter}


def fill_config_file_values(template_paths):
    log("Compiling configuration templates")
    env, cfg = load_env()
    installed, dynamic, modules_dir = nginx_brotli_installed()
    print(f"Installed: {installed}, Dynamic: {dynamic}, Modules dir: {modules_dir}")
    cfg["fill_config_feature"] = {
        "nginx_brotli": {
            "installed": installed,
            "dynamic": dynamic,
            "modules_dir": modules_dir,
        }
    }

    for template_path in template_paths:
        with status(template_path):
            tpath, tfile = os.path.split(template_path)
            jenv = jinja2.Environment(
                loader=jinja2.FileSystemLoader(tpath),
            )
            jenv.filters.update(custom_filters)

            template = jenv.get_template(tfile)
            cfg["env"] = env
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
