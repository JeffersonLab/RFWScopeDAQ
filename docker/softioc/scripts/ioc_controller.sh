#!/bin/sh

# This should be launched in the background.  Give the softIOC time to start up.
sleep 5

cavs="R1M1 R1M2 R1M3 R1M4 R1M5 R1M6 R1M7 R1M8"

set_to_periodic() {
  pvs=""
  for cav in $cavs
  do
    pvs="$pvs ${cav}WFSCOPrun"
  done
  # shellcheck disable=SC2086
  caget $pvs | grep -- -1 | tr -s ' ' | while read -r pv val
  do
    caput "$pv" 0 > /dev/null
  done
}

update_waveforms () {
  val="$(date +%s | rev | cut -c1) $(seq 2 8192)"
  waveforms="IMES QMES GMES PMES GASK PASK CRFP CRFPP CRRP CRRPP GLDE PLDE DETA2 CFQE2 DFQES"
  for cav in $cavs
  do
    for wf in $waveforms
    do
      # We just need the process timestamps to match the sequencer change timestamps.
      # This is pretty fast without setting the whole waveform and hitting them all in the background at once.  Added
      # 5ms sleep to keep from overwhelming the soft IOC
      caput -a ${cav}WFS${wf} 1 $val > /dev/null &
      sleep 0.005
    done
  done
}

update_sequencer() {
  val=$1
  for cav in $cavs
  do
    caput "${cav}WFSCOPstp" "$val" > /dev/null
  done
}

set_start_time() {
  val=$(date +"%Y-%m-%d %H:%M:%S.000001")
  for cav in $cavs
  do
    caput "${cav}WFSharvTake" "$val" > /dev/null
  done
}

set_end_time() {
  val=$(date +"%Y-%m-%d %H:%M:%S.000001")
  for cav in $cavs
  do
    caput "${cav}WFSharvDa" "$val" > /dev/null
  done
}

i=0
update_sequencer 128
while true
do
  # Only sleep longer during the data collection
  set_to_periodic
  if [ $i = "0" ] ; then
    update_sequencer 128
    sleep 0.1
    i=1
  elif [ $i = "1" ] ; then
    update_sequencer 256
    set_start_time
    sleep 0.1
    # Takes a few seconds.  No extra delay needed.
    update_waveforms
    i=2
  else
    update_sequencer 512
    set_end_time
    sleep 0.1
    i=0
  fi
done
