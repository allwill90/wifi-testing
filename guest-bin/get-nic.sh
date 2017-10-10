#!/usr/bin/env bash

set -eo pipefail

NIC=$(nmcli device status | grep -i wifi | awk '{print $1}')
# NIC=$(iw dev | awk '$1=="Interface"{print $2}')

echo $NIC