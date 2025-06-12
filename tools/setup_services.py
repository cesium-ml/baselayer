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
    # a version requirement, retrieve it
    if "tool" not in plugin_config:
        log("Plugin `pyproject.toml` does not contain 'tool' section")
        return None, None
    # there should only be one key in tool, which is the name of the package
    # for which we are installing the plugin
    if len(plugin_config["tool"]) != 1:
        log("Plugin config must have exactly one 'tool' section")
        return None, None

    tool_name = next(iter(plugin_config["tool"]))
    tool_version_requirement = plugin_config["tool"][tool_name].get("version", None)

    if not tool_version_requirement:
        log(f"Plugin config for '{tool_name}' does not specify a version")
        return None, None

    return tool_name, tool_version_requirement


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

    if plugin_config["project"]["name"] != plugin_name:
        log(
            f"Plugin {plugin_name} has a different name in its config ({plugin_config['project']['name']}). Skipping."
        )
        return False

    return True


def run_git_command(args, plugin_path, plugin_name):
    """
    Run a git command in the specified plugin path.

    Args:
        args (list): Git command, e.g. ['checkout', 'main']
        plugin_path (str): Directory where the command runs
        plugin_name (str): Used in error logs

    Returns:
        stdout_lines (list of str): Output lines from stdout
        stderr_str (str): Full stderr output

    Raises:
        subprocess.CalledProcessError: If the command fails
    """
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=plugin_path,
            capture_output=True,
            text=True,
            check=True,
        )

        return result.stdout.splitlines(), result.stderr

    except subprocess.CalledProcessError as e:
        msg = f"[ERROR] Git command failed: {' '.join(args)}"
        if plugin_name:
            msg += f" (plugin: {plugin_name})"
        msg += f"\n{e.stderr}"
        print(msg)
        raise


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

        if process_plugin(plugin_name, plugin_info, plugins_path):
            plugin_services.append(plugin_name)

    return plugin_services


def process_plugin(plugin_name, plugin_info, plugins_path):
    """Process a single plugin - clone or update as needed."""
    plugin_path = pjoin(plugins_path, plugin_name)

    if os.path.exists(plugin_path):
        success = update_existing_plugin(plugin_name, plugin_info, plugin_path)
    else:
        success = clone_new_plugin(plugin_name, plugin_info, plugin_path)

    if success and validate_plugin_compatibility(plugin_name, plugin_path):
        generate_supervisor_config(plugin_name, plugin_path)
        return True

    return False


def update_existing_plugin(plugin_name, plugin_info, plugin_path):
    """Update an existing plugin repository."""
    if not is_valid_git_repo(plugin_path):
        return False

    if has_modified_files(plugin_path, plugin_name):
        return False

    version_tag = plugin_info.get("version")
    sha = plugin_info.get("sha")
    branch = plugin_info.get("branch", "main")

    if version_tag:
        return update_to_version(plugin_name, plugin_path, version_tag)
    elif sha:
        return update_to_sha(plugin_name, plugin_path, sha)
    else:
        return update_to_branch(plugin_name, plugin_path, branch)


def clone_new_plugin(plugin_name, plugin_info, plugin_path):
    """Clone a new plugin repository."""
    branch = plugin_info.get("branch", "main")
    version_tag = plugin_info.get("version")
    sha = plugin_info.get("sha")

    log(f"Cloning plugin {plugin_name}")
    clone_cmd = [
        "clone",
        "--branch",
        branch,
        plugin_info["url"],
        plugin_path,
    ]

    try:
        run_git_command(clone_cmd, ".", plugin_name)
    except subprocess.CalledProcessError:
        return False

    # If version tag is specified, checkout that specific tag after cloning
    # Version tag has priority over SHA - if version is specified, SHA is ignored
    if version_tag:
        log(f"Checking out version {version_tag} for plugin {plugin_name}")
        try:
            # Fetch origin tags
            run_git_command(["fetch", "origin", "--tags"], plugin_path, plugin_name)
            # Checkout the version tag
            run_git_command(["checkout", version_tag], plugin_path, plugin_name)
        except subprocess.CalledProcessError:
            return False

    # If SHA is specified (and no version tag), checkout that specific commit after cloning
    elif sha:
        log(f"Checking out SHA {sha} for plugin {plugin_name}")
        try:
            run_git_command(["checkout", sha], plugin_path, plugin_name)
        except subprocess.CalledProcessError:
            return False

    return True


def update_to_version(plugin_name, plugin_path, version_tag):
    """Update plugin to a specific version tag."""
    # Check if we're already at that tag
    try:
        stdout_lines, _ = run_git_command(
            ["describe", "--exact-match", "--tags", "HEAD"],
            plugin_path=plugin_path,
            plugin_name=plugin_name,
        )
        current_tag = stdout_lines[0] if stdout_lines else "no-tag"
    except subprocess.CalledProcessError:
        current_tag = "no-tag"

    if current_tag == version_tag:
        log(
            f"Plugin {plugin_name} is already at version {version_tag}, skipping update."
        )
        return True
    else:
        log(f"Updating plugin {plugin_name} to version {version_tag}")
        # Fetch latest changes and checkout specific version tag
        try:
            run_git_command(["fetch", "origin", "--tags"], plugin_path, plugin_name)
            run_git_command(["checkout", version_tag], plugin_path, plugin_name)
            return True
        except subprocess.CalledProcessError:
            log(
                f"Failed to fetch or checkout version {version_tag} for plugin {plugin_name}"
            )
            return False


def update_to_sha(plugin_name, plugin_path, sha):
    """Update plugin to a specific SHA commit."""
    # Check if we're already at that commit
    try:
        stdout_lines, _ = run_git_command(
            ["rev-parse", "HEAD"], plugin_path, plugin_name
        )
        current_commit = stdout_lines[0] if stdout_lines else ""
    except subprocess.CalledProcessError:
        current_commit = ""
        log(f"Failed to get current commit for plugin {plugin_name}")

    if current_commit == sha:
        log(f"Plugin {plugin_name} is already at SHA {sha}, skipping update.")
        return True
    else:
        log(f"Updating plugin {plugin_name} to SHA {sha}")
        # Fetch latest changes and checkout specific SHA
        try:
            run_git_command(["fetch", "origin"], plugin_path, plugin_name)
            run_git_command(["checkout", sha], plugin_path, plugin_name)
            return True
        except subprocess.CalledProcessError:
            log(f"Failed to fetch or checkout SHA {sha} for plugin {plugin_name}")
            return False


def update_to_branch(plugin_name, plugin_path, branch):
    """Update plugin to the latest commit on a specific branch."""
    # First fetch to get latest remote refs
    try:
        run_git_command(["fetch", "origin", branch], plugin_path, plugin_name)
    except subprocess.CalledProcessError as e:
        log(f"Failed to fetch branch {branch} for plugin {plugin_name}: {e}")
        return False

    try:
        stdout_lines, _ = run_git_command(
            ["branch", "--show-current"], plugin_path, plugin_name
        )
        current_branch = stdout_lines[0] if stdout_lines else ""
    except subprocess.CalledProcessError:
        current_branch = ""
        log(f"Failed to get current branch for plugin {plugin_name}")

    # If we're not on the correct branch, switch to it
    if current_branch != branch:
        log(f"Switching plugin {plugin_name} from branch {current_branch} to {branch}")
        try:
            run_git_command(["checkout", branch], plugin_path, plugin_name)
        except subprocess.CalledProcessError:
            log(f"[ERROR] Git checkout failed for plugin {plugin_name}")
            return False
        return True

    # Check if we're up to date with the remote branch
    try:
        stdout_lines, _ = run_git_command(
            ["rev-parse", "HEAD"], plugin_path, plugin_name
        )
        last_commit = stdout_lines[0] if stdout_lines else ""
    except subprocess.CalledProcessError:
        last_commit = ""
        log(f"Failed to get last commit for plugin {plugin_name}")

    try:
        stdout_lines, _ = run_git_command(
            ["rev-parse", f"origin/{branch}"], plugin_path, plugin_name
        )
        remote_commit = stdout_lines[0] if stdout_lines else ""
    except subprocess.CalledProcessError:
        remote_commit = ""
        log(f"Failed to get remote commit for branch {branch} in plugin {plugin_name}")

    if last_commit == remote_commit:
        log(
            f"Plugin {plugin_name} is already up to date on branch {branch}, skipping update."
        )
        return True
    else:
        log(f"Updating plugin {plugin_name} to latest on branch {branch}")
        try:
            run_git_command(["pull", "origin", branch], plugin_path, plugin_name)
            return True
        except subprocess.CalledProcessError:
            log(f"Failed to pull branch {branch} for plugin {plugin_name}")
            return False


def is_valid_git_repo(plugin_path):
    """Check if the plugin path contains a valid git repository."""
    if not os.path.exists(pjoin(plugin_path, ".git")):
        log(f"Directory {plugin_path} is not a valid git repository, skipping update.")
        return False
    return True


def has_modified_files(plugin_path, plugin_name):
    """Check if the git repo has modified files that would prevent update."""
    try:
        modified_files, _ = run_git_command(
            ["status", "--porcelain"], plugin_path, plugin_name
        )
    except subprocess.CalledProcessError:
        modified_files = []

    modified_lines = [line for line in modified_files if "M" in line[:2]]

    if modified_lines:
        log(f"Plugin {plugin_name} has modified files, skipping update.")
        return True
    return False


def copy_supervisor_configs(activated_plugins=[]):
    _, cfg = load_env()

    services = {}
    for path in cfg["services.paths"]:
        if os.path.exists(path):
            path_services = [
                d for d in os.listdir(path) if os.path.isdir(pjoin(path, d))
            ]
            services.update({s: pjoin(path, s) for s in path_services})

    all_plugins_path = cfg.get("services.plugins_path", "./plugins")
    for p in activated_plugins:
        services.update({p: pjoin(all_plugins_path, p)})

    # TODO (in a future PR): loop over all services, check if they are a git submodule or not
    # if they are a submodule make sure they are initialized and updated
    # this should be discussed, it does not seem necessary as soon as we have the
    # config based plugin system working

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
    activated_plugins = download_plugin_services()
    print()
    copy_supervisor_configs(activated_plugins)
