# Usage

The premiere application of `baselayer` is
[SkyPortal](https://skyportal.io).  Several pieces of functionality
have been implemented there, but have not been backported to
`baselayer` yet.  Please refer to the SkyPortal documentation, and if
you see a feature you'd like to use, file an issue so we can bring it
in.

## Permissions

Access to resources in Skyportal is controlled in two ways:
- *Roles* are sets of site-wide permissions (*ACLs*) that allow a user to perform certain actions: e.g, create a new user, upload spectra, post comments, etc.
- *Groups* are sets of sources that are accessible to members of that group
    - Members can also be made an *admin* of the group, which gives them group-specific permissions to add new users, etc.
    - The same source source can belong to multiple groups

## Adding roles to users

- User permissions can be managed on the `/users/` page  # TODO not fully implemented

## Adding users to groups

- Groups membership can be managed on the `/groups/` page  # TODO not fully implemented
