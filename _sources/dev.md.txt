# Developer notes

## Testing

To execute the test suite:

- Install ChromeDriver from [https://sites.google.com/a/chromium.org/chromedriver/home](https://sites.google.com/a/chromium.org/chromedriver/home)
- Install Chrome or Chromium
- To run all tests: `make test`
- To run a single test: `./tools/test_frontend.py skportal/tests/frontend/<test_file>.py::test_<specific_test>`

On Linux, the tests can be run in "headless" mode (no browser display):

- Install xfvb (`sudo apt-get install xfvb`)
- `make test_headless`

## Debugging

- Run `make log` to watch log output
- Run `make stop` to stop any running web services.
- Run `make attach` to attach to output of webserver, e.g. for use with `pdb.set_trace()`
- Run `make check-js-updates` to see which Javascript packages are eligible for an upgrade.

## Database

All interactions with the database are performed by way of SQLAlchemy using the
Pyscopg2 backend. Some standard but not necessarily obvious usage patterns we
make use of include:

- Logic for connecting to the DB, refreshing tables, etc. is found in `baselayer/model_utils.py`:

```
from baselayer.app.env import load_env
from baselayer.models import DBSession, init_db
env, cfg = load_env()
init_db(**cfg['database'])
```

- The session object controls various DB state operations:

```
DBSession().add(obj)  # add a new object into the DB
DBSession().commit()  # commit modifications to objects
DBSession().rollback()  # recover after a DB error
```

- Generic logic applicable to any model is included in the base model class `baselayer.app.models.Base` (`to_dict`, `__str__`, etc.), but can be overridden within a specific model
- Models can be selected directly (`User.query.all()`), or more specific queries can be constructed via the session object (`DBSession().query(User.id).all()`)
- Convenience functionality:
  - Join relationships: some multi-step relationships are defined through joins using the `secondary` parameter to eliminate queries from the intermediate table; e.g., `User.acls` instad of `[r.acls for r in User.roles]`
  - [Association proxies](http://docs.sqlalchemy.org/en/latest/orm/extensions/associationproxy.html): shortcut to some attribute of a related object; e.g., `User.permissions` instead of `[a.id for a in User.acls]`
  - [Joined loads](http://docs.sqlalchemy.org/en/latest/orm/loading_relationships.html): this allows for a single query to also include child/related objects; often used in handlers when we know that information about related objects will also be needed.
  - `to_json()`: often from a handler we return an ORM object, which gets converted to JSON via `json_util.to_json(obj.to_dict())`. This also includes the attributes of any children that were loaded via `joinedload` or by accessing them directly. For example:
    - `User.query.first().to_dict()` will not contain information about the user's permissions
    - `u = User.query.first(); u.acls; u.to_dict()` does include a list of the user's ACLs

## New SQL Alchemy 2.0 style select statements

To start a session without verification (i.e., when not committing to DB):

```
with DBSession() as session:
  ...
```

The context manager will make sure the connection is closed when exiting context.

To use a verified session that checks all rows before committing them:

```
with VerifiedSession(user_or_token) as session:
  ...
  session.commit()
```

This does the same checks that are performed when calling `self.verify_and_commit()`.
Each handler class can also call `self.Session()` as a stand-in for `VerifiedSession(self.current_user)`:

```
with self.Session as session:
  ...
  session.commit()
```

To quickly get rows from a table using the new "select" methods, use one of these (replace `User` with any class):

```
user = User.get(id_or_list, user_or_token, mode='read', raise_if_none=False, options=[])
all_users = User.get_all(user_or_token, mode='read', raise_if_none=False, options=[], columns=None)
stmt = User.select(user_or_token, mode='read', options=[], columnns=None)
```

The `get` and `get_all` functions open a session internally and retrieve the objects specified,
if they are accessible to the user. In the case of `get`, if any of the IDs given (as a scalar or list)
are not accessible to do not exist in the DB, the function returns None, or raises an `AccessError`
(if `raise_if_none=True` is specified). The `get_all` just retrieves all rows that are accessible from that table.
Note that these two methods will produce an object _not associated with the external session, if any_.
Thus, if the call is made while an external context is used,
the object has to be added to that session before it can, e.g., load additional relationships,
or be saved, or do any other operation that involves the database.
As an example:

```
with self.Session() as session:
  user = User.get(user_id, self.current_user, mode='read')
  session.add(user)  # must have this to load additional relationships
  tokens = user.tokens  # will fail if user is not in session
```

On the other hand, the `select` function will return
a select statement object that only selects rows that are accessible.
This statement can be further filtered with `where()` and executed using the session:

```
with VerifiedSession(user_or_token) as session:
  stmt = User.select(user_or_token).where(User.id == user_id)
  user = session.execute(stmt).scalars().first()  # returns a tuple with one object
  # can also call session.scalars(stmt).first() to get the object directly
  user.name = new_name
  session.commit()
```

If not using `commit()`, the call to `VerifiedSession(user_or_token)`
can be replaced with `DBSession()` with no arguments.

## Standards

We use ESLint to ensure that our JavaScript & JSX code is consistent and conforms with recommended standards.

- Install ESLint using `make lint-install`. This will also install a git pre-commit hook so that any commit is linted before it is checked in.
- Run `make lint` to perform a style check

## Upgrading Javascript dependencies

The `./tools/check_js_updates.sh` script uses
[`npm-check`](https://github.com/dylang/npm-check) to search updates
for packages defined in `package.json`. It then provides an
interactive interface for selecting new versions and performing the upgrade.
