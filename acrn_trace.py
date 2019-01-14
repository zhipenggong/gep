#!/usr/bin/python3
import os, sys
import re
import collections
import json
import copy
import zipfile
import argparse
import pandas
import subprocess

cpu_num = 4

vm_exits = []
vm_exit = [None] * cpu_num
vmlinux_dir = ''
functions = [{}] * cpu_num

tsc_hz = 1881600000

exit_reasons = {
    0x00000000 : '0x00000000',
    0x00000001 : 'EXTERNAL_INTERRUPT',
    0x00000002 : '0x00000002',
    0x00000003 : '0x00000003',
    0x00000004 : '0x00000004',
    0x00000005 : '0x00000005',
    0x00000006 : '0x00000006',
    0x00000007 : 'INTERRUPT_WINDOW',
    0x00000008 : '0x00000008',
    0x00000009 : '0x00000009',
    0x0000000A : 'CPUID',
    0x0000000B : '0x0000000B',
    0x0000000C : '0x0000000C',
    0x0000000D : '0x0000000D',
    0x0000000E : '0x0000000E',
    0x0000000F : '0x0000000F',
    0x00000010 : '0x00000010',
    0x00000011 : '0x00000011',
    0x00000012 : 'VMCALL',
    0x00000013 : '0x00000013',
    0x00000014 : '0x00000014',
    0x00000015 : '0x00000015',
    0x00000016 : '0x00000016',
    0x00000017 : '0x00000017',
    0x00000018 : '0x00000018',
    0x00000019 : '0x00000019',
    0x0000001A : '0x0000001A',
    0x0000001B : '0x0000001B',
    0x0000001C : 'CR_ACCESS',
    0x0000001D : '0x0000001D',
    0x0000001E : 'IO_INSTRUCTION',
    0x0000001F : 'RDMSR',
    0x00000020 : 'WRMSR',
    0x00000021 : '0x00000021',
    0x00000022 : '0x00000022',
    0x00000024 : '0x00000024',
    0x00000025 : '0x00000025',
    0x00000027 : '0x00000027',
    0x00000028 : '0x00000028',
    0x00000029 : '0x00000029',
    0x0000002B : '0x0000002B',
    0x0000002C : 'APIC_ACCESS',
    0x0000002D : 'VIRTUALIZED_EOI',
    0x0000002E : '0x0000002E',
    0x0000002F : '0x0000002F',
    0x00000030 : 'EPT_VIOLATION',
    0x00000031 : 'EPT_MISCONFIGURATION',
    0x00000032 : '0x00000032',
    0x00000033 : '0x00000033',
    0x00000034 : '0x00000034',
    0x00000035 : '0x00000035',
    0x00000036 : 'WBINVD',
    0x00000037 : 'XSETBV',
    0x00000038 : 'APIC_WRITE',
    0x00000039 : '0x00000039',
    0x0000003A : '0x0000003A',
    0x0000003B : '0x0000003B',
    0x0000003C : '0x0000003C',
    0x0000003D : '0x0000003D',
    0x0000003E : '0x0000003E',
    0x0000003F : '0x0000003F',
    0x00000040 : '0x00000040',
}

def extract_function(cpu, guest_rip):
    if not guest_rip.startswith('0xffff'):
        return
    if cpu >= 1:
        cpu = 1

    if functions[cpu].get(guest_rip) is not None:
        return functions[cpu].get(guest_rip)

    if cpu == 0:
        vmlinux = vmlinux_dir + 'out/sos_kernel/vmlinux'
    else:
        vmlinux = vmlinux_dir + 'out/uos_kernel/vmlinux'
    cmd = 'addr2line -e %s -f %s' % (vmlinux, guest_rip)
    output = subprocess.check_output(cmd, shell=True)
    lines = output.split()
    func = str(lines[0], 'utf-8')
    functions[cpu][guest_rip] = func
    print(guest_rip, func)
    return func

max_ts = 0
    
def parse_cpu(trace_file):
    global vm_exit, vm_exits
    with open(trace_file) as f:
        next(f)
        for line in f:
            items = line.split()
            cpu = int(items[0][3:])
            evid = int(items[1], 16)
            ts = int(items[2])
            if ts > tsc_hz * 10:
                continue
            
            desc = line[line.find(items[2]) + len(items[2]):]
            if vm_exit[cpu] is None:
                if 'vmexit' in desc:
                    reason = int(items[7][:-1], 16)
                    #func = extract_function(cpu, params[4])
                    vm_exit[cpu] = {'exit_ts' : ts, 'cpu' : cpu, 'guest_rip' : items[10][:-1], 'reason' : exit_reasons[reason], 'desc' : ''}
            else:
                args = vm_exit[cpu]
                if (ts < args['exit_ts']):
                    vm_exit[cpu] = None
                    continue
                #if 'timer' in desc:
                #    continue

                if 'vmenter' in desc:
                    if vmlinux_dir is not None and 'VMEXIT_EXTERNAL_INTERRUPT' !=  args['reason']:
                        args['func'] = extract_function(cpu, args['guest_rip'])
                    args['enter_ts'] = ts
                    args['delta'] = args['enter_ts'] - args['exit_ts']
                    vm_exits.append(args)
                    vm_exit[cpu] = None
                else:
                    args['desc'] += desc.strip() + '; '

def parse_ept(cpu_df, reason, csv_file):
    ept = cpu_df[cpu_df.reason == reason].groupby(['func', 'desc'])
    df = ept['delta'].describe()[['count', 'mean', 'min', 'max']]
    df['Total'] = df['count'] * df['mean']
    df.to_csv(csv_file)
    
def parse_vmexit(trace_dir):
    for i in range(cpu_num):
        trace_file = '%s/%d.txt' % (trace_dir, i)
        parse_cpu(trace_file)
    return vm_exits

def parse(trace_dir):
    df = pandas.DataFrame(parse_vmexit(trace_dir))

    pandas.options.display.float_format = '{:,.0f}'.format
    cpu_group = df.groupby(['cpu'])
    print(cpu_group['exit_ts'].describe()[['count', 'min', 'max']])
    
    reason_group = df.groupby(['reason'])
    print(reason_group['delta'].describe()[['count', 'mean', 'min', 'max']])
    summary_csv = 'vm_exit_summary.csv'    
    pandas.DataFrame(['Total']).to_csv(summary_csv, index=False, header=False)
    reason_group['delta'].describe()[['count', 'mean', 'min', 'max']].to_csv(summary_csv, mode='a')
    
    #parse_ept(df[df.cpu != 0], 'VMEXIT_EPT_VIOLATION_GVT', 'wp.csv')
    #parse_ept(df[df.cpu != 0], 'VMEXIT_EPT_VIOLATION', 'violation.csv')
    
    print("Generating vm_exit.csv")
    for i in range(cpu_num):
        print("=============cpu=%d================" % i)
        df_cpu = df[df.cpu == i]
        cpu_reason_group = df_cpu.groupby(['reason'])
        print(cpu_reason_group['delta'].describe()[['count', 'mean', 'min', 'max']])
        pandas.DataFrame(['cpu: %d' % i]).to_csv(summary_csv, mode='a', index=False, header=False)
        cpu_reason_group['delta'].describe()[['count', 'mean', 'min', 'max']].to_csv(summary_csv, mode='a')
        df_cpu.to_csv('vm_exit_%d.csv' % i, index=False)

    df.sort_values('exit_ts', inplace=True)
    df = df.reset_index(drop=True)
    df.to_csv('vm_exit.csv', index=False)
    return

if __name__ == "__main__":
    trace_file = None

    parser = argparse.ArgumentParser()
    parser.add_argument("trace_dir", help="trace dir to be parsed")
    parser.add_argument("vmlinux_dir", nargs='?', help="vmlinux dir to extract functions")
    args = parser.parse_args()
    print(args)

    if not os.path.isdir(args.trace_dir):
        print("Input dir does not exist!")
        exit(1)
    vmlinux_dir = args.vmlinux_dir
    parse(args.trace_dir)
