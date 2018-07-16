#!/usr/bin/python3
import os, sys
import re
import collections
import json
import copy
import zipfile
import argparse
import pandas

bb_timing_records = []
ENGINE_NAMES = ["Render", "VDBOX1", "BLT", "VEBOX", "VDBOX2"]
inject_events = collections.defaultdict(list)
json_fd = None;
trace_events = []
ftrace_filters = ["sched", "tracing_mark_write", "irq_handler_"]
log_filters = ["gen8_de_irq_handler", "inject_preempt_context", "execlists_submit_ports", "unwind_incomplete_requests"]
thread_names = {}
i915_gem_requests = {}
start_timestamp = 0.0        #in seconds
PID_NAMES = {
    "GPU Engines" : 999999,
    "GPU Frequency" : -100
}
multiplier = 0.0
cpuref = 0
gpuref = 0


class SetEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        return json.JSONEncoder.default(self, obj)

class duration_event:
    def __init__(self, name, args, timestamp, tid, pid):
        self.timestamp = timestamp
        self.thread_id = tid
        self.pid = pid
        self.name = name
        self.args = args
        self.dur = 0
    def write_json(self):
        node = {}
        node["name"] = self.name
        node["ph"] = "X"
        node["ts"] = self.timestamp
        node["pid"] = self.pid
        node["tid"] = self.thread_id
        node["dur"] = self.dur
        node["args"] = self.args
        trace_events.append(node)

class instant_event:
    def __init__(self, name, args, timestamp, tid, pid):
        self.timestamp = timestamp
        self.thread_id = tid
        self.pid = pid
        self.name = name
        self.args = args
        self.scope = 't'
    def write_json(self):
        node = {}
        node["name"] = self.name
        node["ph"] = "i"
        node["ts"] = self.timestamp
        node["pid"] = self.pid
        node["tid"] = self.thread_id
        node["s"] = self.scope
        node["args"] = self.args
        trace_events.append(node)

class counter_event:
    def __init__(self, name, args, timestamp, tid, pid):
        self.timestamp = timestamp
        self.thread_id = tid
        self.pid = pid
        self.name = name
        self.args = args
    def write_json(self):
        node = {}
        node["name"] = self.name
        node["ph"] = "C"
        node["pid"] = self.pid
        node["tid"] = self.thread_id
        node["ts"] = self.timestamp
        node["args"] = self.args
        trace_events.append(node)

class i915_gem_request:
    def __init__(self, fence_ctx, seqno, timestamp):
        self.fence_ctx = fence_ctx
        self.seqno = seqno
        self.queue_time = timestamp
        self.global_seqnos = []
        self.preempted = 0
        self.ports = []
        self.counts = []
        self.submits = []
        self.unwinds = []

'''
return cpu time in us
'''
def transform_gpu_to_cpu_time(cpu_ref, gpu_ref, gpu_time):
    cputime = (cpu_ref + (gpu_time - gpu_ref) * multiplier / 1000)
    return float("%.3f" % cputime)

def summary_bb_timing(df):
    ctx_grouped = df.groupby(["engine", "ctx"])
    bb_timing = ctx_grouped["dur"].describe()
    del bb_timing['std']
    del bb_timing['25%']
    del bb_timing['50%']
    del bb_timing['75%']
    bb_timing["count"] = bb_timing["count"].astype('int')
    print(bb_timing)

    
def calcute_bb_timing():
    gpu_utils = []
    df = pandas.DataFrame(bb_timing_records)
    engine_grouped = df.groupby(["engine"])
    pandas.options.display.float_format = '{:,.2f}'.format
    engines = df["engine"].unique()
    for r in engines:
        min_time = transform_gpu_to_cpu_time(cpuref, gpuref, engine_grouped["start"].min().loc[r])
        max_time = transform_gpu_to_cpu_time(cpuref, gpuref, engine_grouped["end"].max().loc[r])
        total_time = max_time - min_time              #in us
        sum = engine_grouped["dur"].sum().loc[r]
        print(("%s utilitzation is %d/%d = %.2f") % (ENGINE_NAMES[r], sum, total_time, sum * 100.0/ total_time))
        gpu_u = {}
        gpu_u['engine'] = r
        gpu_u['sum'] = sum
        gpu_u['util'] = sum * 100.0/ total_time
        gpu_utils.append(gpu_u)


    gpu_util = pandas.DataFrame(gpu_utils).set_index('engine')
    #print(gpu_util)
    #gpu_util.to_csv(csv_file)
    #df.to_csv("data")
    print("\n", "=" * 5, "BB Timing - all (in us)", "=" * 5)
    summary_bb_timing(df)
    lf = df[df.dur <= ((2 * multiplier) / 1000)]
    if (len(lf) > 0):
        print("\n", "=" * 5, "BB Timing - (<2 cycles)  (in us)", "=" * 5)
        summary_bb_timing(lf)
    print()
    print("\n", "=" * 5, "BB Timing - (>2 cycles)  (in us)", "=" * 5)
    summary_bb_timing(df[df.dur > ((2 * multiplier) / 1000)])

'''
gvt workload 0-89    [000] ....   196.196106: i915_gep_read_req: 		
'''
def thread_info(line): 
    index = line.find('[')
    thread_info = line[:index]
    line = line[index:]
    items = line.split()
    timestamp = items[2][:-1]

    index = thread_info.rfind("-")
    thread_id = int(thread_info[index + 1 :])
    thread_name = thread_info[: index]

    thread_names[thread_id] = thread_name
    return thread_name, thread_id, float(timestamp) * 1000000, line

def param_to_hash(params):
    params_hash = {}
    for param in params:
        key, val = param.split('=')
        params_hash[key] = val

    return params_hash

def find_submit_time(submits, early_unwind, later_unwind):
    for t in submits:
        if t > early_unwind and t < later_unwind:
            return t
    print('Failed to find submit time', submits, early_unwind, later_unwind)
    return 0
 
'''
stress_wayland-452   [000] ....   221.118768: i915_gep_read_req: pid=203 vgpu_id=0 hw_ctx=3 fence.ctx=29 seqno=10492 global_seqno=23866 engine=0 prio=1024 preempted=0 cpu_time=3377d23ea6 gpu_time=fe4e0609 submit=fe48ddd1 resubmit=fe49138b start=fe48e879 end=fe4939a5
'''
def i915_gep_read_req(fp, line):
    global max_duration, cpuref, gpuref
    thread_name, thread_id, timestamp, line = thread_info(line)
    items = line.split()
    params = param_to_hash(items[5:])
    cputime     = float(items[2][:-1]) * 1000000            # in us
    gputime     = int(params['gpu_time'], 16)               # in cycle
    gpustart    = int(params['start'], 16)                  # in cycle
    gpuend      = int(params['end'], 16)                    # in cycle
    gpudur      = (gpuend - gpustart) * multiplier / 1000   # in us
    engine      = int(params["engine"])

    request = i915_gem_requests.get(params['fence_ctx'] + '-' + params['seqno'])
    if request is None:
        return
    preempted   = int(request.preempted)
    if cpuref == 0:
        cpuref = cputime
        gpuref = gputime

    start = transform_gpu_to_cpu_time(cpuref, gpuref, gpustart)     # in us
    end = transform_gpu_to_cpu_time(cpuref, gpuref, gpuend)

    node = {}
    node["name"] = " ctx=" + params["fence_ctx"] + " seqno=" + params["seqno"] + " pid=" + params["pid"]
    node["ph"]   = "X"
    node["ts"] = ("%.3f") % start
    node["dur"]  = ("%.3f") % gpudur
    node["tid"]  = ENGINE_NAMES[engine]
    node["pid"]  = PID_NAMES["GPU Engines"]
    args = {}
    args["vgpu"] = params["vgpu_id"]
    args["prio"] = params["prio"]
    args["global_seqno"] = params["global_seqno"]
    args["preempted"] = preempted
#    args["guest_context"] = params["guest_context"]
#    args["guest_seqno"] = params["guest_seqno"]
    args["submit"] = []

    for i in range(len(request.submits)):
        args["submit"].append('global_seqno=%d submit=%.3f port=%d count=%d' % 
                    (request.global_seqnos[i], (request.submits[i]/1000000 - start_timestamp) * 1000, request.ports[i], request.counts[i]))
    submit_times = request.submits  # in us
    unwind_times = request.unwinds  # in us
    submit_times.sort()
    unwind_times.sort() 
    node["args"] = args

    node_ts = []                    # in us
    node_dur = []                   # in us
    if preempted != 0:
        '''
        inject_times = []
        for t in inject_events[engine]:
            if t > gpustart and t < gpuend:
                inject_times.append(t)
        if len(inject_times) != int(params["preempted"]):
            print("Preempted times does not match")
            print(line)

        if request.preempted != int(params["preempted"]):
            print("Preempted times does not match")
            print(line)
        '''
        tmp_unwinds = [0.0] + unwind_times + [end]
        for i in range(len(unwind_times) + 1):
            tmp_submit = find_submit_time(submit_times, tmp_unwinds[i], tmp_unwinds[i + 1])
            node_ts.append(tmp_submit)
            node_dur.append(tmp_unwinds[i + 1] - tmp_submit)

        node_ts[0] = start
        node["dur"] = "%.3f" % node_dur[0]
        args["total duration"] = "%.3f us" % (sum(node_dur))

        for i in range(1, len(node_ts)):
            node1 = copy.deepcopy(node)
            node1["ts"] = ("%.3f") % (node_ts[i])       #in us
            node1["dur"] = ("%.3f") % (node_dur[i])     #in us
            trace_events.append(node1)
    else:
        node_ts.append(start)
        node_dur.append(gpudur)

    args["total duration"] = "%.3f us" % (sum(node_dur))
    trace_events.append(node)

    record = {}
    record["engine"] = engine
#    record["pid"] = params['pid']
    record["ctx"] = params['fence_ctx']
    record["dur"] = sum(node_dur)                   # in us
    record["start"] = gpustart                      # in cycle
    record["end"] = gpuend                          # in cycle
    bb_timing_records.append(record)	

'''
weston-204   [000] ....  5630.695055: i915_gem_request_add: dev=0, ring=0, ctx=29, seqno=333715, global=0
'''
def i915_gem_request_add(fp, line):
    thread_name, thread_id, timestamp, line = thread_info(line)
    items = line.split()
    args = items[5:]
    ie = instant_event("i915_gem_request_add", args, timestamp, thread_id, thread_id)
    ie.write_json()
    params = param_to_hash(items[5:])
    key = params['ctx'][:-1] + '-' + params['seqno'][:-1]
    if key in i915_gem_requests:
        print('Request is already added: ' + key)
        return
    request = i915_gem_request(params['ctx'], params['seqno'], timestamp)
    i915_gem_requests[key] = request

'''
weston-212   [000] d.s2  2007.747787: i915_gem_request_in: dev=0, ring=0, ctx=29, seqno=118649, global=237297, port=0
'''
def i915_gem_request_in(fp, line):
    thread_name, thread_id, timestamp, line = thread_info(line)
    items = line.split()
    args = items[5:]
    ie = instant_event("i915_gem_request_in", args, timestamp, thread_id, thread_id)
    ie.write_json()


def inject_preempt_context(fp, line):
    thread_name, thread_id, timestamp, line = thread_info(line)
    items = line.split()
    args = items[5:]
    ie = instant_event("inject_preempt_context", args, timestamp, thread_id, thread_id)
    ie.write_json()
    engine = int(items[5].split('=')[1])
    inject_events[engine].append(timestamp)

def vblank(fp, line):
    thread_name, thread_id, timestamp, line = thread_info(line)
    items = line.split()
    args = items[6:]
    ie = instant_event("vblank", args, timestamp, thread_id, thread_id)
    ie.scope = 'g'
    ie.write_json()

'''
gvt workload 0-89    [000] ..s1    65.909560: gep_log: execlists_submit_ports pid=89 hw_ctx=4 fence_ctx=5 seqno=2043 global=6973 port=0 count=1 submit_time=4cadd34d
'''
def execlists_submit_ports(fp, line):
    thread_name, thread_id, timestamp, line = thread_info(line)
    items = line.split()
    params = param_to_hash(items[5:])
    args = {}
    args["_key"] = "ctx=%s seqno=%s pid=%s" % (params["fence_ctx"], params["seqno"], params["pid"])
    args["port"] = params["port"]
    args["count"] = params["count"]
    args["pid"] = params["pid"]
    args["global_seqno"] = params["global"]
    ie = instant_event("execlists_submit_ports " + args["_key"], args, timestamp, thread_id, thread_id)
    ie.write_json()
    key = params['fence_ctx'] + '-' + params['seqno']
    request = i915_gem_requests.get(key)
    if request is None:
        return
    request.global_seqnos.append(int(params['global']))
    request.ports.append(int(params['port']))
    request.counts.append(int(params['count']))
    request.submits.append(timestamp)

'''
systemd-journal-171   [000] d.s1    75.562377: gep_log: unwind_incomplete_requests: fence_ctx=5 seqno=2044
'''
def unwind_incomplete_requests(fp, line):
    thread_name, thread_id, timestamp, line = thread_info(line)
    items = line.split()
    params = param_to_hash(items[5:])
    key = params['fence_ctx'] + '-' + params['seqno']
    request = i915_gem_requests.get(key)
    if request is None:
        return
    request.preempted += 1
    request.unwinds.append(timestamp)

'''
kworker/0:1-16    [000] ....   109.512448: intel_gpu_freq_change: new_freq=517
'''
def intel_gpu_freq_change(fp, line):
    thread_name, thread_id, timestamp, line = thread_info(line)
    items = line.split()
    thread_id = PID_NAMES["GPU Frequency"]
    args = {items[4].split("=")[0]: int(items[4].split("=")[1])}
    ce = counter_event("gpu_freq", args, timestamp, thread_id, thread_id)
    ce.write_json()


def parse_trace(trace_file):
    print("parse ftrace...")
    fp = open(trace_file)
    while True:
        line = fp.readline()
        if not line:
            break
        if "i915_gep_read_req" in line:
            i915_gep_read_req(fp, line)
        elif "i915_gem_request_add:" in line:
            i915_gem_request_add(fp, line)
        elif "i915_gem_request_in" in line:
            i915_gem_request_in(fp, line)
        elif "gen8_de_irq_handler vblank" in line:
            vblank(fp, line)
        elif "inject_preempt_context" in line:
            inject_preempt_context(fp, line)
        elif "execlists_submit_ports" in line:
            execlists_submit_ports(fp, line)
        elif "unwind_incomplete_requests" in line:
            unwind_incomplete_requests(fp, line)
        elif "intel_gpu_freq_change" in line:
            intel_gpu_freq_change(fp, line)
    fp.close()

def open_json():
    global json_fd
    try:
        json_fd = open("gpu_trace.json", "w")
    except Exception as e:
        print(e)
        sys.exit(1)
    json_fd.write("{\n\t\"traceEvents\": [")

def close_json():
    json_fd.write("\n\t],\n")
    json_fd.write("\t" + '"displayTimeUnit": "ms"' + "\n}\n")
    json_fd.close()

def dump_json():
    print("dump json file...")
    gpu_trace = {}
    gpu_trace["traceEvents"] = trace_events
    for name, pid in PID_NAMES.items():
        trace_events.append({"name": "process_name", "ph":"M", "pid":pid, "args": {"name":name}})
        trace_events.append({"name": "process_sort_index", "ph":"M", "pid":pid, "args": {"sort_index":pid}})
        if name == "GPU Engines":
            trace_events.append({"name": "thread_sort_index", "ph":"M", "pid":pid, "tid": "Render", "args": {"sort_index":-1}})
    for pid, name in thread_names.items():
        trace_events.append({"name": "process_name", "ph":"M", "pid":pid, "args": {"name":name}})
        trace_events.append({"name": "process_sort_index", "ph":"M", "pid":pid, "args": {"sort_index":pid}})
    with open('gpu_trace.json', 'w') as outfile:
        json.dump(gpu_trace, outfile, indent=2, sort_keys=True, cls=SetEncoder)

def cut_ftrace(trace_file):
    global start_timestamp
    print("cut ftrace...")
    fp = open(trace_file)
    cut_fp = open("cut.ftrace", "w")
    first_record = True
    while True:
        line = fp.readline()
        if not line:
            break
        if not line.startswith('#') and first_record:
            items = line.split()
            new_line = line[:line.find(":") + 2] + "tracing_mark_write: trace_event_clock_sync: parent_ts=%s\n" % items[3][:-1]
            start_timestamp = float(items[3][:-1])
            cut_fp.write(new_line)
            first_record = False
        elif line.startswith('#'):
            cut_fp.write(line)
        elif 'gep_log: B' in line:
            line = line.replace("gep_log", "tracing_mark_write")
            cut_fp.write(line)
        elif 'gep_log: E' in line:
            line = line.replace("gep_log", "tracing_mark_write")
            cut_fp.write(line)
        else:
            for filter in ftrace_filters:
                if filter in line:
                    cut_fp.write(line)

def generate_zipfile(trace_file):
    filename = os.path.splitext(os.path.basename(trace_file))[0] + '.zip'
    z = zipfile.ZipFile(filename,'w',zipfile.ZIP_DEFLATED)
    if os.path.isfile("cut.ftrace"):
        z.write("cut.ftrace")
    if os.path.isfile("gpu_trace.json"):
        z.write('gpu_trace.json')
    z.close()
    print('Generate chrome trace file:', filename)

def init(platform):
    global multiplier
    if platform == "skl":
        multiplier = 83.333
    else:
        multiplier = 52.083
    del bb_timing_records[:]

def parse(trace_file):
    cut_ftrace(trace_file)
    parse_trace(trace_file)
    calcute_bb_timing()
    dump_json()
    generate_zipfile(trace_file)
    return

if __name__ == "__main__":
    trace_file = None

    parser = argparse.ArgumentParser()
    parser.add_argument("trace_file", help="trace file to be parsed")
    parser.add_argument("--skl", help="for skl platform", action='store_true')
    args = parser.parse_args()
    print(args)

    if not os.path.isfile(args.trace_file):
        print("Input file does not exist!")
        exit(1)

    if args.skl:
        platform = "skl"
    else:
        platform = "bxt"

    init(platform)
    parse(args.trace_file)
