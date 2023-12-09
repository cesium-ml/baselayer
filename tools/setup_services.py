import os
from collections import Counter
from os.path import join as pjoin
import subprocess

from baselayer.app.env import load_env
from baselayer.log import make_log

log = make_log("baselayer")

def download_plugin_services():
    env, cfg = load_env()

    services_path = cfg["services.paths"]

    plugins = cfg.get("plugins", {})
    plugin_services = []

    log(f"Discovered {len(plugins)} plugins")

    for plugin_name, plugin_info in plugins.items():
        if "url" not in plugin_info:
            log(f"Skipping plugin {plugin_name} because it has no URL")
            continue

        git_repo = plugin_info["url"].split(".git")[0].split("/")[-1]
        plugin_path = pjoin(services_path[-1], git_repo)

        if os.path.exists(plugin_path):
            if os.path.exists(pjoin(plugin_path, ".git")):
                log(f"Updating plugin {plugin_name}")
                _, stderr = subprocess.Popen(
                    f"cd {plugin_path} && git pull",
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                ).communicate()
                if stderr and len(stderr) > 0:
                    log(f"Error updating plugin {plugin_name}: {stderr}")
                    continue
            else:
                log(f"Skipping plugin {plugin_name} because a microservice with the same name exists at {plugin_path}")
            continue
        else:
            log(f"Cloning plugin {plugin_name}")
            _, stderr = subprocess.Popen(
                f"cd {services_path[-1]} && git clone {plugin_info['url']}",
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ).communicate()
            if stderr and len(stderr) > 0:
                log(f"Error cloning plugin {plugin_name}: {stderr}")
                continue
        plugin_services.append(plugin_name)
    return plugin_services

def copy_supervisor_configs():
    env, cfg = load_env()

    services = {}
    for path in cfg["services.paths"]:
        if os.path.exists(path):
            path_services = [
                d for d in os.listdir(path) if os.path.isdir(pjoin(path, d))
            ]
            services.update({s: pjoin(path, s) for s in path_services})

    duplicates = [k for k, v in Counter(services.keys()).items() if v > 1]
    if duplicates:
        raise RuntimeError(f"Duplicate service definitions found for {duplicates}")

    log(f"Discovered {len(services)} services")

    disabled = cfg["services.disabled"] or []
    enabled = cfg["services.enabled"] or []

    both = set().union(disabled).intersection(enabled)
    if both:
        raise RuntimeError(
            f"Invalid service specification: {both} in both enabled and disabled"
        )

    if disabled == "*":
        disabled = services.keys()
    if enabled == "*":
        enabled = []

    services_to_run = set(services.keys()).difference(disabled).union(enabled)
    log(f"Enabling {len(services_to_run)} services")

    supervisor_configs = []
    for service in services_to_run:
        path = services[service]
        supervisor_conf = pjoin(path, "supervisor.conf")

        if os.path.exists(supervisor_conf):
            with open(supervisor_conf) as f:
                supervisor_configs.append(f.read())

    with open("baselayer/conf/supervisor/supervisor.conf", "a") as f:
        f.write("\n\n".join(supervisor_configs))


if __name__ == "__main__":
    download_plugin_services()
    print()
    copy_supervisor_configs()
