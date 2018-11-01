# Graphics Event Profiler
Graphics Event Profiler(gep) is mainly for gpu performance tuning,
which includes two parts: kernel patches and helper scripts.

## Sample
Please browse the sample to check whether the tool meets your requirement.
1. Open sample.zip through chrome://tracing.
2. Navigate through keyboard and mouse
* w/s: Zoom in/out
* a/d: Pan left/right

## Kernel Patches
Please apply the kernel patches at kernel-patches folder

## Prerequisites for scripts
1. Python 3
* On Ubuntu, run this command
```
sudo apt install python3
```
2. Python pandas library
* On Ubuntu, run this command
```
sudo pip3 install pandas
```

## Quick Start
1. capture the ftrace on the target system.
* enable ftrace through enable-trace.sh
* run test case for a while
* copy /sys/kernel/debug/tracing/trace to your local folder
2. parse the captured ftrace and generate trace.zip.
* gep.py ftrace
3. open trace.zip through chrome://tracing.

## Note
gep.py output explanation:
1. Engine Utilitzation
* Total batch buffer execution time vs total elapsed time.
2. BB Timing
* Batch buffer timing summary for each engine and context.
