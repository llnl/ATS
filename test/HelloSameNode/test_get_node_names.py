#!/usr/bin/env python3

import subprocess
import sys
import re

def get_node_names():
    """
    Parse the output of 'flux resource list' and return a list of node names in allocation order.
    """
    try:
        out = subprocess.check_output("flux resource list", shell=True).decode()
    except Exception as e:
        print(f"Error running 'flux resource list': {e}")
        sys.exit(1)

    node_names = []
    # Look for NODELIST field in the output
    for line in out.splitlines():
        if re.search(r'NODELIST', line):
            # The next line should contain the node list
            continue
        m = re.search(r'(rzadams\[[0-9,-]+\]|rzadams[0-9]+)', line)
        if m:
            nodelist = m.group(1)
            # Expand bracket notation, e.g. rzadams[1010-1013]
            bracket = re.match(r'([a-zA-Z]+)\[([0-9,-]+)\]', nodelist)
            if bracket:
                base = bracket.group(1)
                rng = bracket.group(2)
                for part in rng.split(','):
                    if '-' in part:
                        start, end = map(int, part.split('-'))
                        node_names.extend([f"{base}{i}" for i in range(start, end+1)])
                    else:
                        node_names.append(f"{base}{part}")
            else:
                node_names.append(nodelist)
    return node_names

def get_node_name(rel_index):
    nodes = get_node_names()
    if rel_index < 0 or rel_index >= len(nodes):
        raise IndexError(f"Relative index {rel_index} out of range (0-{len(nodes)-1})")
    return nodes[rel_index]

def main():
    nodes = get_node_names()
    print("Allocated nodes in order:")
    for idx, n in enumerate(nodes):
        print(f"  [{idx}] {n}")

    if len(sys.argv) > 1:
        try:
            rel_index = int(sys.argv[1])
        except ValueError:
            print("Usage: flux_node_mapper.py <relative_index>")
            sys.exit(1)
    else:
        rel_index = int(input(f"Enter relative node index (0-{len(nodes)-1}): "))

    try:
        node_name = get_node_name(rel_index)
        print(f"Node {rel_index} maps to: {node_name}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
