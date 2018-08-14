set -x
UOS_COMMAND="/root/run.sh"
SOS_IP=192.168.1.101
UOS_IP=192.168.1.103

#ssh root@192.168.1.101 "echo > /sys/kernel/debug/tracing/trace; dmesg -c; echo 1 > /sys/kernel/debug/tracing/tracing_on;"
#ssh root@192.168.1.103 "echo > /sys/kernel/debug/tracing/trace; dmesg -c; echo 1 > /sys/kernel/debug/tracing/tracing_on;"
ssh root@192.168.1.101 "echo x86-tsc >/sys/kernel/debug/tracing/trace_clock"
ssh root@192.168.1.101 "/root/enable_trace"
#ssh root@192.168.1.103 "echo x86-tsc >/sys/kernel/debug/tracing/trace_clock"
ssh root@192.168.1.103 "/root/enable_trace"

#ssh root@192.168.1.103 $UOS_COMMAND > log_uos 2>&1 &
ssh root@192.168.1.101 "/root/acrntrace -c -i 500 -r 64" > log_trace 2>&1 &
#sleep 5
sleep 0.2
ssh root@192.168.1.101 "/root/capture-trace.sh"
ssh root@192.168.1.103 "echo > /sys/kernel/debug/tracing/trace"
#ssh root@192.168.1.103 "/root/run.sh"

#ssh root@192.168.1.103 "echo 0 > /sys/kernel/debug/tracing/tracing_on"
ssh root@192.168.1.101 "killall acrntrace"
#ssh root@192.168.1.101 "chmod +x -R /tmp/acrntrace/*"
ssh root@192.168.1.101 "echo 0 > /sys/kernel/debug/tracing/tracing_on"
ssh root@192.168.1.103 "echo 0 > /sys/kernel/debug/tracing/tracing_on"
sleep 5
#ssh root@192.168.1.103 "killall glmark2-es2-wayland"


ssh root@192.168.1.101 "cp /sys/kernel/debug/tracing/trace /root/trace"
ssh root@192.168.1.103 "cp /sys/kernel/debug/tracing/trace /root/trace"

scp root@192.168.1.101:/root/trace  trace_sos
scp root@192.168.1.103:/root/trace  trace_uos
for((i = 0; i < 4; i++))
do
	scp -r root@192.168.1.101:~/$i .
	./acrntrace_format.py formats $i > $i.txt
done

#./acrn_trace.py
./gep.py trace_sos
#./ket_simple.py trace_uos
#./ket_simple.py trace_sos

#./gep.py trace_sos
