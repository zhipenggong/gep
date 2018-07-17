echo 200000 > /sys/kernel/debug/tracing/buffer_size_kb
echo 1 > /sys/kernel/debug/tracing/events/sched/sched_switch/enable
echo 1 > /sys/kernel/debug/tracing/events/sched/sched_wakeup/enable
echo 1 > /sys/kernel/debug/dri/0/i915_gep_enable
echo 1 > /sys/kernel/debug/tracing/events/i915/enable
echo 1 > /sys/kernel/debug/tracing/events/drm/drm_log/enable
