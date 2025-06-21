#!/usr/bin/env python

import os
import subprocess

import jinja2
from baselayer.app.env import load_env
from baselayer.log import make_log
from status import status

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
    modules_path : str
        The directory where the nginx modules are located if dynamic loading is used
    """

    installed = False
    dynamic = False
    modules_path = None

    try:
        output = subprocess.check_output(
            ["nginx", "-V"], stderr=subprocess.STDOUT
        ).decode("utf-8")
        # Option 1: installed at compilation: always loaded
        if (
            "--add-module" in output
            and "brotli" in output.split("--add-module")[1].strip()
        ):
            installed = True
        # Option 2: installed dynamically at compilation or later: has to be loaded
        else:
            # a. find the modules path
            config_path = (
                str(output.split("--conf-path=")[1].split(" ")[0]).strip()
                if "--conf-path" in output
                else None
            )
            modules_path = (
                str(output.split("--modules-path=")[1].split(" ")[0]).strip()
                if "--modules-path" in output
                else None
            )
            # if there's no modules path, try to guess it from the config path
            if config_path and not modules_path:
                modules_path = os.path.dirname(config_path).replace(
                    "nginx.conf", "modules"
                )
                if not modules_path or not os.path.isdir(modules_path):
                    modules_path = None

            # b. check if there is a brotli module in the modules path
            if modules_path:
                modules_path = modules_path.rstrip("/")
                if all(
                    os.path.isfile(os.path.join(modules_path, f))
                    for f in [
                        "ngx_http_brotli_filter_module.so",
                        "ngx_http_brotli_static_module.so",
                    ]
                ):
                    installed = True
                    dynamic = True
                else:
                    installed = False
                    dynamic = False
                    modules_path = None
    except subprocess.CalledProcessError:
        pass
    return installed, dynamic, modules_path


custom_filters = {"md5sum": md5sum, "version": version, "hash": hash_filter}


def fill_config_file_values(template_paths):
    log("Compiling configuration templates")
    env, cfg = load_env()
    installed, dynamic, modules_path = nginx_brotli_installed()
    cfg["fill_config_feature"] = {
        "nginx_brotli": {
            "installed": installed,
            "dynamic": dynamic,
            "modules_path": modules_path,
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
