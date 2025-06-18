import os
import subprocess
from collections import Counter
from importlib import import_module
from os.path import join as pjoin

from packaging import version
from packaging.specifiers import SpecifierSet

from baselayer.app.env import load_env
from baselayer.log import make_log

# let's try to use tomllib for Python 3.11+, and otherwise fall back to tomli
# (the standalone tomli package, or the one from setuptools)
try:
    import tomllib as tl
except (ImportError, ModuleNotFoundError):
    try:
        import tomli as tl
    except ImportError:
        try:
            import setuptools._vendor.tomli as tl
        except ImportError:
            raise ImportError(
                "Could not find tomli or tomllib for reading pyproject.toml files"
            )

log = make_log("baselayer")


def generate_supervisor_config(service_name: str, service_path: str) -> str:
    """
    Generates a supervisor configuration for a given service.

    Parameters
    ------
    service_name: str
        Name of the service to generate the configuration for.
    service_path: str
        Path to the service directory where the main.py file is located.

    Returns
    -------
    str: The generated supervisor configuration template.
    """
    supervisor_conf_template = f"""
[program:{service_name}]
command=/usr/bin/env python {pjoin(service_path, 'main.py')} %(ENV_FLAGS)s
environment=PYTHONPATH=".",PYTHONUNBUFFERED="1"
stdout_logfile=log/{service_name}_service.log
redirect_stderr=true
"""
    return supervisor_conf_template


def read_plugin_config(plugin_path: str) -> dict:
    """
    Reads the external service configuration from pyproject.toml.

    Parameters
    ------
    plugin_path: str
        Path to the external service directory containing pyproject.toml.

    Returns
    -------
    dict: Parsed configuration dictionary.
    """
    config_path = pjoin(plugin_path, "pyproject.toml")
    try:
        with open(config_path, "rb") as f:
            return tl.load(f)
    except FileNotFoundError:
        return None


def validate_version(version_string: str, requirement_string: str) -> bool:
    """
    Validate a version against a version requirement.

    Parameters
    ----------
    version_string: str
        The version to validate (e.g., "1.2.3").
    requirement_string: str
        The version requirement (e.g., ">=1.0,<2.0").

    Returns
    -------
    bool: True if the version satisfies the requirement, False otherwise.
    """
    try:
        v = version.parse(version_string)
        spec = SpecifierSet(requirement_string)
        return v in spec
    except Exception as e:
        log(f"Error validating version: {e}")
        return False


def validate_service_compatibility(service_path: str) -> bool:
    """
    Validate if a service is compatible with the current environment based on its optional pyproject.toml.

    Parameters
    ----------
    service_path: str
        Path to the service directory containing pyproject.toml.

    Returns
    -------
    bool: True if the service is compatible or has no pyproject.toml, False otherwise.
    """
    service_name = os.path.basename(service_path)
    plugin_config = read_plugin_config(service_path)
    if plugin_config is None:
        return True

    if plugin_config.get("project", {}).get("name"):
        service_name = plugin_config["project"]["name"]

    # if there is no supervisor.conf provided, we can only generate one
    # if we can make an assumption about the entry point (being named main.py)
    # otherwise we skip the service
    if not os.path.isfile(
        pjoin(service_path, "supervisor.conf")
    ) and not os.path.isfile(pjoin(service_path, "main.py")):
        log(
            f"External service {service_name} does not contain a supervisor.conf or main.py, skipping"
        )
        return False

    if "tool" not in plugin_config:
        log("External service `pyproject.toml` does not contain 'tool' section")
        return False

    # tool section specifies which software can a external service work with
    for name, value in plugin_config["tool"].items():
        if not isinstance(value, dict):
            log(
                f"Invalid tool section for {name}: expected a dictionary, got {type(value)}"
            )
            return False

        try:
            mod = import_module(name)
        except ImportError:
            log(
                f"External service {service_name} requires {name}, but it is not installed."
            )
            continue

        version_requirement = value.get("version", None)
        if not version_requirement:
            log(
                f"External service {service_name} does not specify a version requirement in tool.{name}.version"
            )
            continue

        try:
            installed_version = mod.__version__
            if not isinstance(installed_version, str):
                log(
                    f"External service {service_name} requires {name} with version {version_requirement}, but installed version is not a string ({installed_version})."
                )
                return False
        except ImportError:
            log(
                f"External service {service_name} requires {name} with version {version_requirement}, but unable to determine installed version."
            )
            return False

        if not validate_version(installed_version, version_requirement):
            log(
                f"External service {service_name} requires {name} with version {version_requirement}, but installed version is {installed_version}. Skipping"
            )
            return False

    return True


def run_git_command(args: list, plugin_path: str, plugin_name: str) -> tuple:
    """
    Run a git command in the specified external service path.

    Parameters
    ----------
    args: list
        Git command to run, e.g. ['checkout', 'main']
    plugin_path: str
        Directory where the command runs
    plugin_name: str
        Name of the external service, used in error logs

    Returns
    -------
    tuple: (stdout_lines, stderr_lines)
        stdout_lines: List of output lines from stdout
        stderr_lines: List of output lines from stderr
    """
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=plugin_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.splitlines(), result.stderr.splitlines()

    except subprocess.CalledProcessError as e:
        msg = f"[ERROR] Git command failed: {' '.join(args)}"
        if plugin_name:
            msg += f" (external service: {plugin_name})"
        msg += f"\n{e.stderr}"
        raise RuntimeError(msg) from e


def is_git_repo(plugin_path: str) -> bool:
    """Check if the external service path contains a valid git repository.

    Parameters
    ----------
    plugin_path: str
        Path to the external service directory.

    Returns
    -------
    bool: True if the directory is a valid git repository, False otherwise.
    """
    if not os.path.exists(pjoin(plugin_path, ".git")):
        log(f"Directory {plugin_path} is not a valid git repository, skipping update.")
        return False
    return True


def has_modified_files(plugin_path: str, plugin_name: str) -> bool:
    """Check if the git repo has modified files that would prevent update.

    Parameters
    ----------
    plugin_path: str
        Path to the external service directory.
    plugin_name: str
        Name of the external service, used in error logs

    Returns
    -------
    bool: True if there are modified files, False otherwise.
    """
    try:
        modified_files, _ = run_git_command(
            ["status", "--porcelain"], plugin_path, plugin_name
        )
    except RuntimeError:
        modified_files = []

    modified_lines = [line for line in modified_files if "M" in line[:2]]

    return len(modified_lines) > 0


def get_current_sha(plugin_path: str) -> str | None:
    """Get the current branch and SHA of the git repository.

    Parameters
    ----------
    plugin_path: str
        Path to the external service directory.

    Returns
    -------
    str or None: Current commit SHA if available, None otherwise.
    """
    try:
        _, _ = run_git_command(["rev-parse", "--abbrev-ref", "HEAD"], plugin_path, "")
        sha, _ = run_git_command(["rev-parse", "HEAD"], plugin_path, "")
        return sha[0]
    except RuntimeError:
        return None


def get_current_tag(plugin_path: str) -> str | None:
    """Get the current tag of the git repository.

    Parameters
    ----------
    plugin_path: str
        Path to the external service directory.

    Returns
    -------
    str or None: Current tag if available, None otherwise.
    """
    try:
        tag, _ = run_git_command(
            ["describe", "--exact-match", "--tags"], plugin_path, ""
        )
        return tag[0]
    except RuntimeError:
        return None


def update_or_clone_plugin_by_tag(
    url: str, version_tag: str, plugin_name: str, plugin_path: str
) -> bool:
    """Clone a new external service repository.

    Parameters
    ----------
    url: str
        Git repository URL.
    version_tag: str
        Version tag to checkout.
    plugin_name: str
        Name of the external service, used in error logs
    plugin_path: str
        Path to the external service directory.

    Returns
    -------
    bool: True if the operation was successful, False otherwise.
    """

    # if tag doesn't start with 'v', we add it
    if not version_tag.startswith("v"):
        version_tag = "v" + version_tag

    # if the dir exists and we already are on the correct tag, we can skip cloning
    if not os.path.exists(plugin_path):
        clone_cmd = [
            "clone",
            "--depth",
            "1",
            "--branch",
            version_tag,
            url,
            plugin_path,
        ]
        try:
            run_git_command(clone_cmd, ".", plugin_name)
        except RuntimeError:
            return False

    current_tag = get_current_tag(plugin_path)
    if current_tag == version_tag:
        return True

    # let's be extra safe and verify that it's a valid tagged release
    stdout, _ = run_git_command(["tag", "-l"], plugin_path, plugin_name)
    if version_tag not in stdout:
        log(f"Version tag {version_tag} not found in external service {plugin_name}.")
        return False

    # checkout the specific tag after cloning
    log(f"Checking out version tag {version_tag} for external service {plugin_name}")
    try:
        # since it's a shallow clone, we need to fetch the specific tag
        run_git_command(["fetch", "origin", version_tag], plugin_path, plugin_name)
        run_git_command(["checkout", version_tag], plugin_path, plugin_name)
    except RuntimeError:
        return False

    return True


def update_or_clone_plugin_by_branch(
    url: str, branch: str, sha: str, plugin_name: str, plugin_path: str
) -> bool:
    """Clone a new external service repository.

    Parameters
    ----------
    url: str
        Git repository URL.
    branch: str
        Branch to checkout.
    sha: str
        Commit SHA to checkout.
    plugin_name: str
        Name of the external service, used in error logs
    plugin_path: str
        Path to the external service directory.

    Returns
    -------
    bool: True if the operation was successful, False otherwise.
    """

    # if the dir exists and we already are on the correct branch and SHA, we can skip cloning
    if not os.path.exists(plugin_path):
        clone_cmd = [
            "clone",
            "--depth",
            "1",
            "--branch",
            branch,
            url,
            plugin_path,
        ]
        try:
            run_git_command(clone_cmd, ".", plugin_name)
        except RuntimeError:
            return False

    current_sha = get_current_sha(plugin_path)
    if current_sha == sha:
        return True

    # checkout the specific SHA after cloning
    log(f"Checking out SHA {sha} for external service {plugin_name}")
    try:
        # since it's a shallow clone, we need to fetch the specific SHA
        run_git_command(["fetch", "origin", sha], plugin_path, plugin_name)
        run_git_command(["checkout", sha], plugin_path, plugin_name)
    except RuntimeError:
        return False

    return True


def update_or_clone_plugin(
    plugin_name: str, plugin_info: dict, plugin_path: str
) -> bool:
    """Clone a new external service repository.

    Parameters
    ----------
    plugin_name: str
        Name of the external service, used in error logs
    plugin_info: dict
        External service information dictionary containing 'url', 'branch', 'sha', and/or 'version'.
    plugin_path: str
        Path to the external service directory.

    Returns
    -------
    bool: True if the operation was successful, False otherwise.
    """
    branch = plugin_info.get("branch", "main")
    sha = plugin_info.get("sha")
    version_tag = (
        plugin_info.get("version").lower() if plugin_info.get("version") else None
    )
    url = plugin_info.get("url")

    if url is None:
        return True

    if os.path.exists(plugin_path) and has_modified_files(plugin_path, plugin_name):
        log(f"External service {plugin_name} has modified files, skipping update.")
        return True

    if version_tag:
        return update_or_clone_plugin_by_tag(url, version_tag, plugin_name, plugin_path)
    elif branch and sha:
        return update_or_clone_plugin_by_branch(
            url, branch, sha, plugin_name, plugin_path
        )
    else:
        return False


def initialize_external_services() -> list:
    """
    Initialize external services by cloning or updating their repositories.

    Returns
    -------
    external_services: list
        List of tuples containing (plugin_name, enabled) for each external service.
    """
    _, cfg = load_env(False)
    plugins_path = cfg["services.paths"][-1]
    os.makedirs(plugins_path, exist_ok=True)

    plugins = cfg.get("services.external", {})
    external_services = []

    for plugin_name, plugin_info in plugins.items():
        plugin_path = pjoin(plugins_path, plugin_name)
        if os.path.exists(plugin_path) and not is_git_repo(plugin_path):
            continue
        elif update_or_clone_plugin(plugin_name, plugin_info, plugin_path):
            external_services.append((plugin_name, True))
        else:
            external_services.append((plugin_name, False))

    return external_services


def copy_supervisor_configs(external_services=[]):
    """
    Copy supervisor configurations from all services to the main supervisor.conf file.

    Parameters
    ----------
    external_services: list
        List of external services, each as a tuple (service_name, enabled).

    Returns
    -------
    None
    """
    _, cfg = load_env(False)

    services = {}
    for path in cfg["services.paths"]:
        if os.path.exists(path):
            path_services = [
                d for d in os.listdir(path) if os.path.isdir(pjoin(path, d))
            ]
            services.update({s: pjoin(path, s) for s in path_services})

    # TODO (in a future PR): loop over all services, check if they are a git submodule or not
    # if they are a submodule make sure they are initialized and updated
    # this should be discussed, it does not seem necessary as soon as we have the
    # config based external service system working

    duplicates = [k for k, v in Counter(services.keys()).items() if v > 1]
    if duplicates:
        raise RuntimeError(f"Duplicate service definitions found for {duplicates}")

    log(f"Discovered {len(services)} services ({len(external_services)} external)")

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

    disabled = set(disabled).union([s for s, e in external_services if not e])

    services_to_run = set(services.keys()).difference(disabled).union(enabled)

    incompatible = [
        service
        for service in services_to_run
        if not validate_service_compatibility(services[service])
    ]

    services_to_run = services_to_run.difference(incompatible)

    log(f"Enabling {len(services_to_run)} services")

    supervisor_configs = []
    for service in services_to_run:
        path = services[service]
        supervisor_conf = pjoin(path, "supervisor.conf")

        if os.path.exists(supervisor_conf):
            with open(supervisor_conf) as f:
                supervisor_configs.append(f.read())
        else:
            conf = generate_supervisor_config(service, path)
            supervisor_configs.append(conf)

    with open("baselayer/conf/supervisor/supervisor.conf", "a") as f:
        f.write("\n\n".join(supervisor_configs))


if __name__ == "__main__":
    print()
    external_services = initialize_external_services()
    copy_supervisor_configs(external_services)
