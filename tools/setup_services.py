import os
import subprocess
from collections import Counter
from os.path import join as pjoin

import tomli
from packaging import version
from packaging.specifiers import SpecifierSet

from baselayer.app.env import load_env
from baselayer.log import make_log

log = make_log("baselayer")


def generate_supervisor_config(service_name, service_path):
    """
    Generates a supervisor configuration for a given service.
    """
    supervisor_conf_template = f"""
[program:{service_name}]
command=/usr/bin/env python {pjoin(service_path, 'main.py')} %(ENV_FLAGS)s
environment=PYTHONPATH=".",PYTHONUNBUFFERED="1"
stdout_logfile=log/{service_name}_service.log
redirect_stderr=true
"""
    # Write the configuration to a file
    with open(f"{service_path}/supervisor.conf", "w") as f:
        f.write(supervisor_conf_template)


def read_plugin_config(plugin_path):
    # read the config (pyproject.toml) for the plugin
    config_path = pjoin(plugin_path, "pyproject.toml")
    with open(config_path, "rb") as f:
        return tomli.load(f)


def get_plugin_compatible_version(plugin_config: dict):
    # if the plugin specifies a "tool.<name>" section with
    # a version requirement, retrive it
    if "tool" not in plugin_config:
        log("Plugin config does not contain 'tool' section")
        return None, None
    # there should only be one key in tool, which is the name of the package
    # for which we are installing the plugin
    if len(plugin_config["tool"]) != 1:
        log("Plugin config must have exactly one 'tool' section")
        return None, None

    tool_name = next(iter(plugin_config["tool"]))
    tool_version = plugin_config["tool"][tool_name].get("version", None)

    if not tool_version:
        log(f"Plugin config for '{tool_name}' does not specify a version")
        return None, None

    return tool_name, tool_version


def validate_version(version_string, requirement_string):
    """
    Validate a version against a version requirement.

    Args:
        version_string (str): The version to check (e.g., "1.2.3")
        requirement_string (str): The requirement specification (e.g., ">=1.0.0", "==1.2.3", ">=1.0,<2.0")

    Returns:
        bool: True if version satisfies the requirement, False otherwise
    """
    try:
        v = version.parse(version_string)
        spec = SpecifierSet(requirement_string)
        return v in spec
    except Exception as e:
        log(f"Error validating version: {e}")
        return False


def validate_plugin_compatibility(plugin_name: str, plugin_path: str):
    plugin_config = read_plugin_config(plugin_path)
    name, version_requirement = get_plugin_compatible_version(plugin_config)
    if not (name and version_requirement):
        return True
    try:
        mod = __import__(name)
        installed_version = mod.__version__

        if not validate_version(installed_version, version_requirement):
            log(
                f"Plugin {plugin_name} is incompatible: required {version_requirement}, found {installed_version}. Skipping."
            )
            return False

    except ImportError:
        log(
            f"Could not find package {name} which plugin {plugin_name} depends on. Skipping."
        )
        return False

    return True


def download_plugin_services():
    _, cfg = load_env()

    plugins_path = cfg.get("services.plugins_path", "./plugins")
    os.makedirs(plugins_path, exist_ok=True)

    plugins = cfg.get("plugins", {})

    plugin_services = []

    log(f"Discovered {len(plugins)} plugins")

    for plugin_name, plugin_info in plugins.items():
        if "url" not in plugin_info:
            log(f"Skipping plugin {plugin_name} because it has no URL")
            continue

        git_repo = plugin_info["url"].split(".git")[0].split("/")[-1]
        plugin_path = pjoin(plugins_path, git_repo)
        branch = plugin_info.get("branch", "main")

        if os.path.exists(plugin_path):
            if os.path.exists(pjoin(plugin_path, ".git")):
                # Check if the git repo currently has modified files, if it does, skip update
                # added files are fine, but modified files could cause issues
                modified_files = (
                    subprocess.Popen(
                        f"cd {plugin_path} && git status --porcelain",
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    .communicate()[0]
                    .decode()
                    .strip()
                )
                if modified_files:
                    log(f"Plugin {plugin_name} has modified files, skipping update.")
                else:
                    last_commit = (
                        subprocess.Popen(
                            f"cd {plugin_path} && git rev-parse HEAD",
                            shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                        )
                        .communicate()[0]
                        .decode()
                        .strip()
                    )
                    remote_commit = (
                        subprocess.Popen(
                            f"cd {plugin_path} && git rev-parse origin/{branch}",
                            shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                        )
                        .communicate()[0]
                        .decode()
                        .strip()
                    )
                    if last_commit == remote_commit:
                        log(
                            f"Plugin {plugin_name} is already up to date on branch {branch}, skipping update."
                        )
                        plugin_services.append(plugin_name)
                    else:
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
                log(
                    f"Skipping plugin {plugin_name} because a microservice with the same name exists at {plugin_path}"
                )
                continue
        else:
            log(f"Cloning plugin {plugin_name}")
            _, stderr = subprocess.Popen(
                f"cd {plugins_path} && git clone {plugin_info['url']}",
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ).communicate()
            if stderr and stderr.decode().strip() != f"Cloning into '{git_repo}'...":
                log(f"Error cloning plugin {plugin_name}: {stderr}")
                continue

        # validate plugin compatibility:
        if validate_plugin_compatibility(plugin_name, plugin_path):
            plugin_services.append(plugin_name)
            generate_supervisor_config(plugin_name, plugin_path)
        else:
            continue

    return plugin_services


def copy_supervisor_configs():
    _, cfg = load_env()

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
