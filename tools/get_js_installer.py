#!/usr/bin/env python

import json


def get_js_installer():
    try:
        data = json.load(open("package.json", "rb"))
    except FileNotFoundError:
        data = {}

    packageManager = data.get("packageManager", "npm@")
    packageManagerVersion = None
    managers = ("pnpm", "yarn", "bun", "npm")

    if packageManager.count("@") == 1:
        parts = packageManager.split("@")
        packageManager = parts[0]
        packageManagerVersion = parts[1].strip() if len(parts[1].strip()) > 1 else None

    for manager in managers:
        if packageManager.startswith(manager):
            return manager, packageManagerVersion


if __name__ == "__main__":
    print(get_js_installer())
