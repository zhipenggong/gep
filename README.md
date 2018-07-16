# gep
gep tool includes some helper scripts for Graphics Event Profiler

## Prerequisites
1. Python 3
2. Python pandas library

## Usage
1. capture the ftrace on the target system.
* enable ftrace through enable-trace.sh
* run test case for a while
* copy /sys/kernel/debug/tracing/trace to your local folder
2. parse the captured ftrace and generate trace.zip.
* gep.py ftrace
3. open trace.zip through chrome://tracing.
