#/bin/bash
#
# This script updates all submodules to their tracking branch (or, if
# unspecified, master).
#

echo "--- Updating submodules"
git submodule foreach --quiet \
'
  BRANCH=$(git config -f $toplevel/.gitmodules submodule.$name.branch \
           || echo master)
  echo "* $name -> origin/$BRANCH"
  git pull --quiet origin $BRANCH
  git checkout --quiet $BRANCH
'
echo "--- End submodule update"
