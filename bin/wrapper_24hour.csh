#!/bin/csh

# req ops - the hard way
set tmpfile=`/cs/prohome/bin/reqExec ops`
source $tmpfile
rm -f tmpfile

# make sure a zone was included
#if ( "$1" == "" ) then
#	echo "missing zone (ex. \"R1O\")"
#	exit
#endif


foreach zone ("R1N")
	echo $zone
	# set signal to check RF on
	set signal="${zone}XKDOUT1r"
	# check value
	set return_value=`caget -t $signal`
	echo $return_value

	# check if a value was returned (signal not mistyped)
	if ( "$return_value" != "" ) then
		# if value 7 = all cavities off, skip; otherwise run script
		if ( $return_value != 7 ) then
			# run script
			/usr/csite/pubtools/bin/python3.7 /usr/csmuser/tsm/python/epics/v5.9/main.py -z=$zone -t=1
	
			# tar up the data and move it to /data/waveforms dir
			echo tar -cvf /data/waveforms/$zone_`date +"%Y_%m_%d_%H%M"`.tar /tmp/c100-rfw-scope-data/$zone* 
	
			# rm tmp files
			echo rm -rf /tmp/c100-rfw-scope-data/$zone*
	
			# zip it up to save space
			echo gzip /data/waveforms/$zone_`date +"%Y_%m_%d_%H%M"`.tar
	
			# copy file over to CUE for Monibor 
			#scp -p /usr/opsdata/waveforms/c100/$1_`date +"%Y_%m_%d"`.tar.gz jlabl1:/group/felteam/C100_DATA/
		else
			echo "Zone turned off, skipping"
		endif
	else
		echo "Signal ${1}XKDOUT1r unreachable, skipping"
	endif
end

exit


