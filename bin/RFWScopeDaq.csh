#!/cs/dvlhome/apps/r/RFWScopeDaq/dvl/support/csueLib/bin/csueLaunch /bin/csh -f
# DO NOT MODIFY ABOVE LINE - it is managed automatically
set csueAppName="RFWScopeDaq"
set csueVer="dvl"
# USE THESE GLOBALS TO BUILD PATHS TO SUPPORT OR FILEIO
# (Leave them here for automatic management)
#
# The following code creates a variable which holds the path to
# the current version of the application ($csueAppPath).
# It can be used to build  paths to the support directory or
# fileio directories.
#
# This code may be stripped out if it is not needed.
#
# set lowercase [string range [string tolower $csueAppName] 0 0]
set env=$HBASE
set csueAppPath="$env/apps/r/$csueAppName/$csueVer"
#
# End of Template Code

# Append any arguments passed from command-line using $argv
exec python3.11 $csueAppPath/bin/main.py $argv
