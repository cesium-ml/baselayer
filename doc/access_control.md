# Access control

## Introduction

Apps built on baselayer can restrict, row by row and user by user, which records of a table a user can create, read, update, and delete. These policies are enforced in the API layer by a row-level security (RLS) framework built on the SQLAlchemy ORM. With it, developers can

- Be sure that access policies will be consistently enforced when protected records are accessed in an API transaction
- Efficiently filter database queries by RLS accessibility to ensure that API endpoints only return records that users can access
- Take advantage of vectorization to efficiently apply policy checks and filters to bulk record queries
- Define arbitrarily complex, relational, and scalable row-level CRUD access policies on any table
- Implement different policies for different types of access on a single type of record

**Note:** The framework does not use PostgreSQL's own row-level security.

## Architecture and design

Policies are defined on SQLAlchemy mapped classes. Each class has a single policy for each of the create, read, update, and delete access modes. Records are read- and create-public by default, and update- and delete-restricted (i.e., only accessible to users with the "System admin" ACL) by default. Join tables made with `join_model` are also update- and delete-restricted by default, but they can (by default) be created or read by any user that can read both their left and right records. These defaults can be overridden on any mapped class.

When a handler brings an instance of a mapped class into a verified session (`self.Session()` in a handler, or `VerifiedSession(user_or_token)`), either by a query or by adding a new instance, the ORM tracks changes to the instance's state. When the session is committed, the permission checker introspects it and gets the sets of records that were read, updated, deleted, or created during the transaction. It then checks that every record was accessed in an allowable way. If it finds a violation, it raises an `AccessError`: the transaction is not committed, and the handler responds with HTTP status code 403 and a message that identifies the rows where an access policy was violated. If no access policies are violated, the transaction is committed.

With `security.strict: false` in the config, a violation only logs a warning and the transaction is committed anyway.

This design ensures that every object pulled into a verified session has its access policy checked in a consistent way. In most cases, the developer only needs to define a policy on a mapped class, then commit the handler's session to ensure that the policy is applied. Sessions opened with `DBSession()` or `new_session()` skip that check (see [Choosing a session](dev.md#choosing-a-session)).

## Create a new policy

Policies are instances of `UserAccessControl`, defined in `baselayer/app/models.py`. The only method of `UserAccessControl` that subclasses must provide is `select_accessible_rows`:

```python
class UserAccessControl:

    def select_accessible_rows(self, cls, user_or_token, columns=None):
        """Construct a Select object that, when executed, returns the rows of a
        specified table that are accessible to a specified user or token.

        Parameters
        ----------
        cls : `baselayer.app.models.DeclarativeMeta`
            The mapped class of the target table.
        user_or_token : `baselayer.app.models.User` or `baselayer.app.models.Token`
            The User or Token to check.
        columns : list of sqlalchemy.Column, optional, default None
            The columns to retrieve from the target table. If None, queries
            the mapped class directly and returns mapped instances.

        Returns
        -------
        sqlalchemy select object
        """

        raise NotImplementedError
```

`select_accessible_rows` constructs (but does not execute) a select statement on the table that `cls` is mapped to. The statement returns the rows of that table that `user_or_token` can access.

To construct a new policy, subclass `UserAccessControl` and override `select_accessible_rows`.

### Predefined policies

Baselayer provides these policies in `baselayer.app.models`:

- `public`: grants access to anyone.
- `restricted`: grants access only to users or tokens with the "System admin" ACL.
- `AccessibleIfUserMatches(relationship_chain)`: grants access to the users pointed to by a relationship of the record, or by a chain of relationships such as `"group.users"`, and to users with the "System admin" ACL. `accessible_by_owner`, `accessible_by_created_by`, and `accessible_by_user` are ready-made instances.
- `AccessibleIfRelatedRowsAreAccessible(**properties_and_modes)`: grants access only if the related records are also accessible, e.g. `AccessibleIfRelatedRowsAreAccessible(created_by="read")`.
- `CustomUserAccessControl(query_or_query_generator)`: grants access to the rows returned by a select statement, or by a function of `cls` and `user_or_token` that returns one.

### Examples

The `public` policy is defined as:

```python
class Public(UserAccessControl):
    """A record accessible to anyone."""

    def select_accessible_rows(self, cls, user_or_token, columns=None):
        if columns is not None:
            return sa.select(*columns).select_from(cls)
        return sa.select(cls)


public = Public()
```

The following `accessible_to_owner` policy will grant record access to any user that matches the `User` pointed to by the `owner` relationship of `cls`, with access automatically granted to users with the "System admin" ACL:

```python
from baselayer.app.models import AccessibleIfUserMatches

accessible_to_owner = AccessibleIfUserMatches("owner")
```

Bitwise operations can be used to compose access policies. The `accessible_to_owner_or_last_modified_by` policy below grants access to any user that matches the `User` pointed to by the `owner` relationship of `cls` or the `last_modified_by` relationship of `cls`:

```python
accessible_to_owner_or_last_modified_by = AccessibleIfUserMatches(
    "owner"
) | AccessibleIfUserMatches("last_modified_by")
```

Policies can be custom (potentially complex and relational) database queries. This policy only permits access to departments in which all employees are managers:

```python
from baselayer.app.models import CustomUserAccessControl

CustomUserAccessControl(
    sa.select(Department)
    .join(Employee)
    .group_by(Department.id)
    .having(sa.func.bool_and(Employee.is_manager.is_(True)))
)
```

## Binding policies to classes

To bind a policy to a class, set the `create`, `read`, `update`, or `delete` attribute of the class to the policy, depending on which access mode you want the policy to apply to:

```python
Note.delete = accessible_by_owner
```

The above will ensure that only the owner of a note (or anyone with the "System admin" ACL) can delete the note.

## Convenience methods

Mapped classes provide methods to check access to their records and to retrieve only the records a user can access:

(a) Can the `User` `user` update the `Note` `note`?

```python
note.is_accessible_by(user, mode="update")
```

(b) Retrieve notes with IDs [1, 3] if they are updatable by `user`, raising an `AccessError` if either does not exist:

```python
Note.get_if_accessible_by([1, 3], user, raise_if_none=True, mode="update")
```

(c) Retrieve all notes that `user` can read:

```python
Note.get_records_accessible_by(user, mode="read")
```

(d) Construct a select statement for all notes that `user` can delete, then filter it further:

```python
stmt = Note.select(user, mode="delete").where(Note.created_at < cutoff)
deletable_notes = session.scalars(stmt).all()
```

See also `get` and `get_all` in the [developer notes](dev.md#new-sql-alchemy-20-style-select-statements).
