echo x86-tsc >/sys/kernel/debug/tracing/trace_clock
echo 100000 > /sys/kernel/debug/tracing/buffer_size_kb
echo 1 > /sys/kernel/debug/tracing/events/sched/sched_switch/enable
echo 1 > /sys/kernel/debug/tracing/events/sched/sched_wakeup/enable
echo 1 > /sys/kernel/debug/tracing/events/irq/irq_handler_entry/enable
echo 1 > /sys/kernel/debug/tracing/events/irq/irq_handler_exit/enable
echo 1 > /sys/kernel/debug/tracing/events/irq/softirq_entry/enable
echo 1 > /sys/kernel/debug/tracing/events/irq/softirq_exit/enable
echo 1 > /sys/kernel/debug/tracing/events/workqueue/enable
echo 1 > /sys/kernel/debug/tracing/tracing_on
