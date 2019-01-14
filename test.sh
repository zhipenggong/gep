set -x
SOS=root@10.239.153.160

adb root
adb push enable-trace-uos.sh /sdcard
adb push copy-trace.sh /sdcard
scp enable-trace.sh $SOS:~/
#scp copy-trace.sh $SOS:~/
scp acrntrace $SOS:/data

ssh $SOS "/root/enable-trace.sh"
ssh $SOS "cd /data;/data/acrntrace -c -i 500 -r 16" &
sleep 0.2
ssh $SOS "echo > /sys/kernel/debug/tracing/trace"

adb shell sh /sdcard/enable-trace-uos.sh
echo "!!!Start the test, please press the button within 20 seconds!!!"
sleep 30
ssh $SOS "kill \`pgrep acrntrace\`"
ssh $SOS "echo 0 > /sys/kernel/debug/tracing/tracing_on"
adb shell sh /sdcard/copy-trace.sh
adb pull /data/trace trace_uos

ssh $SOS "cp /sys/kernel/debug/tracing/trace /data/trace"
scp $SOS:/data/trace  trace_sos
sleep 5
for((i = 0; i < 4; i++))
do
	scp -r $SOS:/data/$i .
	./acrntrace_format.py formats $i > $i.txt
done

./gep.py trace_sos
#./gep.py trace_uos
