#!/usr/bin/env python

import json


def get_js_installer():
    try:
        data = json.load(open("package.json", "rb"))
    except FileNotFoundError:
        data = {}

    packageManager = data.get("packageManager", "npm@")
    managers = ("pnpm", "yarn", "bun", "npm")

    for manager in managers:
        if manager in packageManager:
            return manager


if __name__ == "__main__":
    print(get_js_installer())
