#!/bin/csh

# req ops - the hard way
set tmpfile=`/cs/prohome/bin/reqExec ops`
source $tmpfile
rm -f tmpfile

# make sure a zone was included
if ( "$1" == "" ) then
	echo "missing zone (ex. \"R1O\")"
	exit
endif

# set signal to check RF on
#signal="${1}5RFONr"
set signal="${1}XKDOUT1r"
# check value
set return_value=`caget -t $signal`

# check if a value was returned (signal not mistyped)
if ( "$return_value" != "" ) then
	# if value 7 = all cavities off, skip; otherwise run script
	if ( $return_value != 7 ) then
		# run script
		/usr/csite/pubtools/bin/python3.7 /usr/csmuser/tsm/python/epics/v5.9.1/main.py -z=$1 -t=10
		# tar up the data and move it to c100 dir
		tar -cvf /usr/opsdata/waveforms/c100/$1_`date +"%Y_%m_%d"`.tar /tmp/c100-rfw-scope-data/$1* 
		# zip it up to save space
		gzip /usr/opsdata/waveforms/c100/$1_`date +"%Y_%m_%d"`.tar
		# rm tmp files
		rm -rf /tmp/c100-rfw-scope-data/$1*
		# copy file over to CUE for Monibor 
		scp -p /usr/opsdata/waveforms/c100/$1_`date +"%Y_%m_%d"`.tar.gz jlabl1:/group/felteam/C100_DATA/
	else
		echo "Zone turned off, skipping"
	endif
else
	echo "Signal ${1}XKDOUT1r unreachable, skipping"
endif
exit
