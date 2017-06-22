#/bin/bash
#
# This script updates all submodules to their tracking branch (or, if
# unspecified, master).
#

echo "--- Updating submodules"
git submodule update --remote
git submodule foreach -q --recursive \
      'echo "* $name";\
       git checkout \
         $(git config -f $toplevel/.gitmodules submodule.$name.branch || echo master)'
echo "--- End submodule update"
