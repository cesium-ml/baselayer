#!/usr/bin/env python
import argparse
import shutil
import subprocess
import sys
import textwrap

from status import status

from baselayer.app.env import load_env
from baselayer.log import make_log

log = make_log("db_init")

parser = argparse.ArgumentParser(description="Create or re-create the database.")
parser.add_argument(
    "-f",
    "--force",
    action="store_true",
    help="recreate the db, even if it already exists",
)
parser.add_argument(
    "--test-only",
    action="store_true",
    help="only act on the test database",
)
args, unknown = parser.parse_known_args()

env, cfg = load_env()

db = cfg["database.database"]
db_test = db + "_test"
dbs = (db_test,) if args.test_only else (db, db_test)

user = cfg["database.user"] or db
host = cfg["database.host"]
port = cfg["database.port"]
password = cfg["database.password"]

psql_cmd = "psql"
flags = f"-U {user}"

if password:
    psql_cmd = f'PGPASSWORD="{password}" {psql_cmd}'
flags += " --no-password"

if host:
    flags += f" -h {host}"

if port:
    flags += f" -p {port}"

# Superuser for creating the role/databases; not every install uses "postgres".
admin_user = cfg.get("database.admin_user") or "postgres"
admin_cmd = f"{psql_cmd} {flags.replace(f'-U {user}', f'-U {admin_user}')}"

# Stock Linux installs only admit the superuser through peer auth on the socket.
sudo_admin_cmd = f"sudo -n -u {admin_user} psql -X --no-password" + (
    f" -p {port}" if port else ""
)

test_cmd = f"{psql_cmd} {flags} -c 'SELECT 0;' "


def run(cmd):
    return subprocess.run(cmd, capture_output=True, shell=True)


def stderr(p):
    return p.stderr.decode("utf-8").strip()


def test_db(database):
    return run(test_cmd + database)


def manual_commands():
    """Commands that do the superuser part of this script by hand."""
    errors = {d: stderr(test_db(d)) for d in dbs}
    no_role = any(f'role "{user}" does not exist' in e for e in errors.values())
    to_create = [
        d
        for d, e in errors.items()
        if args.force or no_role or f'database "{d}" does not exist' in e
    ]
    return [
        *(f"sudo -u {admin_user} dropdb --if-exists {d}" for d in dbs if args.force),
        *([f"sudo -u {admin_user} createuser {user}"] if no_role else []),
        *(f"sudo -u {admin_user} createdb -O {user} {d}" for d in to_create),
    ]


def ask(question):
    try:
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def find_admin_cmd():
    """Return a psql command that connects as the superuser, or None."""
    p = run(f"{admin_cmd} -c 'SELECT 0;' postgres")
    if p.returncode == 0:
        return admin_cmd
    if "authentication failed" not in stderr(p) and "pg_hba.conf" not in stderr(p):
        return None
    if not (sys.stdin.isatty() and shutil.which("sudo")):
        return None

    print(
        f"\nCannot connect as the superuser [{admin_user}] over "
        f"{host or 'the socket'}. Either:\n\n"
        f"  1. Let this script run `sudo -u {admin_user} psql`. "
        "sudo can ask for your password.\n"
        "  2. Answer no, and run these commands yourself:\n"
    )
    print("\n".join(f"       {cmd}" for cmd in manual_commands()) + "\n")
    if not ask("Use sudo?"):
        print("\nRun the commands above, then run this script again.\n")
        sys.exit(1)
    if subprocess.run(["sudo", "-v"]).returncode != 0:
        return None
    if run(f"{sudo_admin_cmd} -c 'SELECT 0;' postgres").returncode != 0:
        return None
    return sudo_admin_cmd


def show_hba_file(admin):
    if admin is not None:
        p = run(f"{admin} -t -P format=unaligned -c 'SHOW hba_file;' postgres")
        if p.returncode == 0:
            return p.stdout.decode("utf-8").strip()
    return None


def advice(error, admin):
    """Return instructions that fix the connection error, if it is a known one."""
    sudo_psql = f"sudo -u {admin_user} psql"

    if "password authentication failed" in error:
        return [
            f"The password for [{user}] is wrong or not set. Set it with:",
            "",
            f"  {sudo_psql} -c \"ALTER USER {user} PASSWORD '<password>';\"",
            "",
            "and put the same password in `database.password` in your config.",
        ]

    if "authentication failed" in error or "no pg_hba.conf entry" in error:
        method = "scram-sha-256" if password else "trust"
        all_dbs = ",".join(dbs)
        if host:
            lines = [
                f"  host    {all_dbs}  {user}  127.0.0.1/32  {method}",
                f"  host    {all_dbs}  {user}  ::1/128       {method}",
            ]
        else:
            lines = [f"  local   {all_dbs}  {user}  {method}"]

        hba_file = show_hba_file(admin)
        if hba_file:
            where = ["Your `pg_hba.conf` is:", "", f"  {hba_file}"]
        else:
            where = [
                "Find your `pg_hba.conf` with:",
                "",
                f"  {sudo_psql} -t -P format=unaligned -c 'SHOW hba_file;'",
            ]
        return [
            f"PostgreSQL rejected the login method for [{user}].",
            *where,
            "",
            "Add these lines above the first uncommented line of that file.",
            "PostgreSQL uses the first line that matches, so they must come",
            "before the default `ident` or `peer` lines:",
            "",
            *lines,
            "",
            "Then reload the configuration:",
            "",
            f"  {sudo_psql} -c 'SELECT pg_reload_conf();'",
        ]

    if "does not exist" in error:
        return [
            "The role or the database does not exist. Create them with:",
            "",
            *(f"  {cmd}" for cmd in manual_commands()),
        ]

    if "Connection refused" in error or "No such file or directory" in error:
        return [
            "The PostgreSQL server is not running. Start it with:",
            "",
            "  sudo systemctl enable --now postgresql",
            "",
            "On Fedora and RHEL, initialize the data directory first with:",
            "",
            "  sudo postgresql-setup --initdb",
        ]

    return []


log("Initializing databases")

# If test_only is false, we only test the connection to the main database,
# since the test database may not exist in production
db_to_check = db_test if args.test_only else db

# Other connection errors, such as auth failures, are diagnosed below.
missing = any("does not exist" in stderr(test_db(d)) for d in dbs)
needs_admin = args.force or missing
admin = find_admin_cmd() if needs_admin else None
if needs_admin and admin is None:
    print(
        f"\nCannot connect as the superuser [{admin_user}]. "
        "Run these commands yourself, then run this script again:\n"
    )
    print("\n".join(f"  {cmd}" for cmd in manual_commands()) + "\n")
    sys.exit(1)

if admin is not None:
    with status(f"Creating user [{user}]"):
        p = run(f'{admin} -c "CREATE USER {user};" postgres')
    if p.returncode != 0 and "already exists" not in stderr(p):
        print(f"\nWarning: could not create user {user}\n\n{stderr(p)}\n")

if args.force and admin is not None:
    try:
        for current_db in dbs:
            with status(f"Removing database [{current_db}]"):
                p = run(f'{admin} -c "DROP DATABASE IF EXISTS {current_db};" postgres')
                if p.returncode != 0:
                    raise RuntimeError(stderr(p))
    except RuntimeError as e:
        print(
            f"Could not delete database: \n\n{textwrap.indent(str(e), prefix='  ')}\n"
        )
        sys.exit(1)

for current_db in dbs if admin is not None else ():
    # We allow this to fail, because oftentimes because of complicated db setups
    # users want to create their own databases
    with status(f"Creating database [{current_db}]"):
        # If database already exists, and we can connect to it, there's nothing to do
        if test_db(current_db).returncode == 0:
            continue

        p = run(f'{admin} -c "CREATE DATABASE {current_db} OWNER {user};" postgres')
        if p.returncode != 0 and "already exists" not in stderr(p):
            print()
            print(f"Warning: could not create db {current_db}")
            print()
            print("\n".join(line for line in stderr(p).split("\n") if "ERROR" in line))
            print()
            print("  Create it manually with:")
            print()
            print(f"    sudo -u {admin_user} createdb -O {user} {current_db}")
            print()

p = test_db(db_to_check)
try:
    with status(f"Testing database connection to [{db_to_check}]"):
        if p.returncode != 0:
            raise RuntimeError()

except RuntimeError:
    print(
        textwrap.dedent(
            f"""
        !!! Error accessing database:

        We tried to connect to the database with the following parameters:

          database: {db_to_check}
          username: {user}
          host:     {host}
          port:     {port}

        The postgres client exited with the following error message:

        {"-" * 78}
        {stderr(p)}
        {"-" * 78}
        """
        )
    )
    fix = advice(stderr(p), admin)
    if fix:
        print("\n".join(fix) + "\n")
    print("Check your connection with:\n")
    print(f"  {test_cmd + db_to_check}\n")
    sys.exit(1)

print()
