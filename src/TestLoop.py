import os
import subprocess
import re
import sys

OUTPUT_PATH = "output/liDARPT/run_3/"

def run_python_code(full_path):
    speed = None
    unitDist = None

    if "sw-geo" in full_path:
        speed = 70.0
        unitDist = 3.0
    elif "sw-schlee" in full_path:
        speed = 65.0
        unitDist = 1.5
    elif "markt-karl" in full_path:
        unitDist = 2.0
        speed = 65.0
    else:
        raise ValueError

    buf = full_path.split("/")[-2]
    length_word = buf.split("_")[0]

    env = os.environ.copy()  # start with the current environment
    # env["PYTHONPATH"] = ('/nix/store/czzsi5zryrkj0281lj5rrma7pprrk1ys-python3-3.10.16/lib/python3.10/site-packages'
    #                      ':/nix/store/3lvv1prnj16i5b3cj561ndzcb9xrp0h2-python3.10-pip-24.0/lib/python3.10/site'
    #                      '-packages')
    env["LD_LIBRARY_PATH"] = ("/HOME/s388381/liDARP/venv/bin:/nix/store/w2m5p0fb6pmqq6dz2jqlvnyw7n4vcbpx-curl-8.12.1/lib/:/nix"
                  "/store/hh698a2nnpqr47lh52n26wi8fiah3hid-gcc-13.3.0-lib/lib")

    network_name = re.split(r"[\\/]", full_path)[-3]
    output_path_all = os.path.join(str(OUTPUT_PATH), str(network_name), str(length_word))
    subprocess.run([sys.executable, "src/scripts/IOHandler.py", "input/config.json", full_path, str(speed), str(unitDist), output_path_all], env=env)



def walk_and_run(directory):
    for root, dirs, files in os.walk(directory):
        for file_name in files:
            full_path = os.path.join(root, file_name)
            print("Found file: ", full_path)
            run_python_code(full_path)


os.chdir("/HOME/s388381/liDARPT")
walk_and_run(r"input/requests/random_requests")
