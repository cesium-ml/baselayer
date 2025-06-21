#!/usr/bin/env python
import argparse
import subprocess
import sys
import textwrap

from baselayer.app.env import load_env
from baselayer.log import make_log
from status import status

log = make_log("db_init")

parser = argparse.ArgumentParser(description="Create or re-create the database.")
parser.add_argument(
    "-f",
    "--force",
    action="store_true",
    help="recreate the db, even if it already exists",
)
args, unknown = parser.parse_known_args()

env, cfg = load_env()

db = cfg["database.database"]
db_test = db + "_test"
all_dbs = (db, db_test)

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

admin_flags = flags.replace(f"-U {user}", "-U postgres")

test_cmd = f"{psql_cmd} {flags} -c 'SELECT 0;' "


def run(cmd):
    return subprocess.run(cmd, capture_output=True, shell=True)


def test_db(database):
    p = run(test_cmd + database)
    return p.returncode == 0


log("Initializing databases")

with status(f"Creating user [{user}]"):
    run(f'{psql_cmd} {admin_flags} -c "CREATE USER {user};"')

if args.force:
    try:
        for current_db in all_dbs:
            with status(f"Removing database [{current_db}]"):
                p = run(
                    f'{psql_cmd} {admin_flags}\
                          -c "DROP DATABASE {current_db};"'
                )
                if p.returncode != 0:
                    raise RuntimeError()
    except RuntimeError:
        print(
            "Could not delete database: \n\n"
            f'{textwrap.indent(p.stderr.decode("utf-8").strip(), prefix="  ")}\n'
        )
        sys.exit(1)

for current_db in all_dbs:
    with status(f"Creating database [{current_db}]"):
        # We allow this to fail, because oftentimes because of complicated db setups
        # users want to create their own databases

        # If database already exists and we can connect to it, there's nothing to do
        if test_db(current_db):
            continue

        p = run(
            f'{psql_cmd} {admin_flags}\
                  -c "CREATE DATABASE {current_db} OWNER {user};"'
        )
        if p.returncode == 0:
            run(
                f'{psql_cmd} {flags}\
                 -c "GRANT ALL PRIVILEGES ON DATABASE {current_db} TO {user};"\
                 {current_db}'
            )
        else:
            print()
            print(f"Warning: could not create db {current_db}")
            print()
            print(
                "\n".join(
                    line
                    for line in p.stderr.decode("utf-8").split("\n")
                    if "ERROR" in line
                )
            )
            print()
            print("  You should create it manually by invoking `createdb`.")
            print("  Then, execute:")
            print()
            print(
                f"    {psql_cmd} {flags}"
                f' -c "GRANT ALL PRIVILEGES ON DATABASE {current_db} TO {user};"'
                f" {current_db}"
            )
            print()

# We only test the connection to the main database, since
# the test database may not exist in production
try:
    with status(f"Testing database connection to [{db}]"):
        if not test_db(db):
            raise RuntimeError()

except RuntimeError:
    print(
        textwrap.dedent(
            f"""
        !!! Error accessing database:

        The most common cause of database connection errors is a
        misconfigured `pg_hba.conf`.

        We tried to connect to the database with the following parameters:

          database: {db}
          username: {user}
          host:     {host}
          port:     {port}

        The postgres client exited with the following error message:

        {'-' * 78}
        {p.stderr.decode('utf-8').strip()}
        {'-' * 78}

        Please modify your `pg_hba.conf`, and use the following command to
        check your connection:

          {test_cmd + db}
        """
        )
    )
    sys.exit(1)

print()
