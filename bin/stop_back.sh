#!/bin/bash

terminate_process_tree() {
    local pid="$1"
    local signal="${2:-TERM}"


    if [[ ! "$pid" =~ ^[0-9]+$ ]]; then
        echo "Error: Invalid PID ${pid}"
        return 1
    fi

    local children
    children=$(pgrep -P "$pid")

    for child in $children; do
        terminate_process_tree "$child" "$signal"
    done

    if kill -0 "$pid" 2>/dev/null; then
        echo "killing process $pid"
        kill -"$signal" "$pid"
    fi
}

pid_input_file=${1:-"backend/.backend_pid"}

if [[ -f "$pid_input_file" ]]; then
  parent_pid=$(<"$pid_input_file")
else
  echo "Error: pid file {$pid_input_file} does not exist"
  return 1
fi

terminate_process_tree $parent_pid && rm -iv $pid_input_file && rm -i backend_${parent_pid}.log
