#!/bin/sh

# This should be launched in the background.  Give the softIOC time to start up.
sleep 5

cavs="R1M1 R1M2 R1M3 R1M4 R1M5 R1M6 R1M7 R1M8"

function update_sequencer {
  val=$1
  for cav in $cavs
  do
    caput ${cav}WFSCOPstp $val > /dev/null
  done
}

function set_start_time {
  val=`date +"%Y-%m-%d %H:%M:%S.%N"`
  for cav in $cavs
  do
    caput ${cav}WFSharvTake $val > /dev/null
  done
}

function set_end_time {
  val=`date +"%Y-%m-%d %H:%M:%S.%N"`
  for cav in $cavs
  do
    caput ${cav}WFSharvDa $val > /dev/null
  done
}

i=0
update_sequencer 128
while true
do
  # Only sleep longer during the data collection
  if [ $i == "0" ] ; then
    update_sequencer 128
    sleep 0.1
    i=1
  elif [ $i == "1" ] ; then
    update_sequencer 256
    sleep 1.7
    i=2
  else
    update_sequencer 512
    sleep 0.1
    i=0
  fi
done
