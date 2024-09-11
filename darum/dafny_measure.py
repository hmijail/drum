#! python3
"""
Ease bookkeeping of dafny's measure-complexity runs 
by storing the log file with the args in the filename
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
# import subprocess as sp
import sys
import time
import logging
from datetime import datetime as dt, timedelta as td
import psutil
from quantiphy import Quantity
from typing import NoReturn
from sh import Command
from functools import partial

from darum import plot_distribution



def main():
    parser = argparse.ArgumentParser(description="Run dafny's measure-complexity and store the verification args in the filename of the resulting log file for easier bookkeeping.")
    parser.add_argument("dafnyfiles", nargs="+", help="The dafny file(s) to verify.")
    parser.add_argument("-e", "--extra_args", default="", help="A quoted string of extra arguments to pass to dafny")
    parser.add_argument("-d", "--dafnyexec", default="dafny", help="The dafny executable")
    parser.add_argument("-r", "--rseed", default=str(int(time.time())),help="The random seed. By default is seeded with the current time.")
    parser.add_argument("-i", "--iter", default="10", help="Number of iterations. Default=%(default)s")
    parser.add_argument("-f", "--format", default="json", help=argparse.SUPPRESS) # CVS needs updating
    parser.add_argument("-s", "--filter-symbol", help="Only verify symbols containing this substring.")
    parser.add_argument("-l", "--limitRC", type=Quantity, default=Quantity("10M"), help="The Resource Count limit. Accepts magnitudes (K,M,G...). Default=%(default)s")
    parser.add_argument("-a", "--isolate-assertions",action="store_true")
    parser.add_argument("-c", "--verify-included-files",action="store_true", help="Verify included files")
    parser.add_argument("-z", "--z3-path", help="Path to Z3")
    parser.add_argument("-o", "--output_dir", default="darum", help="Directory to store the results. Default=%(default)s")
    parser.add_argument("-v", "--verbose", action="count", default=0)
    parser.add_argument("-n", "--no-plotting",action="store_true", help="Do not plot after the verification")

    args = parser.parse_args()

    logging.basicConfig() #level=numeric_level,format='%(levelname)s:%(message)s')
    logger = logging.getLogger(__name__)
    numeric_level = max(logging.DEBUG, logging.WARNING - args.verbose * 10)
    logger.setLevel(numeric_level)

    try:
        os.makedirs(args.output_dir)
    except:
        pass
    IAstr = "_IA" if args.isolate_assertions else ""
    VIFstr = "_VIF" if args.verify_included_files else ""
    dafnyfiles_str = ""
    source_dict  = {}
    for df in args.dafnyfiles:
        dfb = os.path.basename(df)
        # with open(df, "rb") as f:
        #     digest = hashlib.file_digest(f, "md5")
        with open(df, "r") as f:
            src= f.read()
        digest = hashlib.md5(bytes(src, encoding="utf-8"))
        hash = digest.hexdigest()
        dfsplit = os.path.splitext(dfb)
        filenamehash = f"{dfsplit[0]}.H{hash[0:4]}{dfsplit[1]}"
        source_dict[filenamehash]=src
        dafnyfiles_str += f"_{dfsplit[0]}_H{hash[0:4]}"
        # take a snapshot of this input file, adding the same hash piece as in the log
        dfcopy = os.path.join(args.output_dir,filenamehash)
        if not os.path.exists(dfcopy):
            shutil.copy2(df,dfcopy)
    z3str = f"_Z{Path(args.z3_path).name}" if args.z3_path else ""
    symbol = f"_s{args.filter_symbol}" if args.filter_symbol else ""
    dafnyexec= os.path.basename(args.dafnyexec)
    argstring4filename = f"{dafnyexec}{dafnyfiles_str}_IT{args.iter}_L{args.limitRC}{IAstr}{VIFstr}{z3str}{symbol}_{args.extra_args}".replace("/","").replace("-","").replace(":","").replace(" ","")
    d = dt.now()
    dstr = d.strftime('%m%d-%H%M%S')
    logfilename = os.path.join(args.output_dir, dstr + "_" + argstring4filename)
    # for convenience, take another snapshot of each single-input-file with the same full filename as the log
    # if len(args.dafnyfiles)==1:
    #     df= args.dafnyfiles[0]
    #     dfsplit = os.path.splitext(df)
    #     shutil.copy2(df,logfilename+dfsplit[1])
    #log.debug(f"filename={filename}")
    #shell_line = fr"{args.dafnyexec} measure-complexity --log-format csv\;LogFileName='{filename}' {args.extra_args} {args.dafnyfile}"

    arglist = [
        # args.dafnyexec,
        "measure-complexity",
        "--random-seed", args.rseed,
        "--iterations", args.iter,
        "--log-format", f"{args.format};LogFileName={logfilename}.{args.format}",
        "--resource-limit", str(int(args.limitRC)),
        "--isolate-assertions" if args.isolate_assertions else "",
        "--verify-included-files" if args.verify_included_files else "",
        *(["--solver-path", args.z3_path] if args.z3_path else []),
        *(["--filter-symbol", args.filter_symbol] if args.filter_symbol else []),
        *args.extra_args.split(),
        *args.dafnyfiles
        ]
    logger.debug(f"Executing:{args.dafnyexec} {' '.join(arglist)}")
    # sys.stdout.flush()
    # sys.stderr.flush()
    # os.execvp(args.dafnyexec, arglist )

    #pitfalls: bufsize; blocking,

    import atexit
    def killProc():
        logger.debug("Killing the subprocess' group...")
        dafny_proc.kill_group()
    atexit.register(killProc)

    def process_output(stream, store, line):
        # nonlocal iteration_tstamp
        nonlocal iteration_tstamp
        nonlocal iteration_times
        if "Starting verification of iteration" in line or "The total consumed resources are" in line:
            now = dt.now()
            if iteration_tstamp is not None:
                delta = int((now - iteration_tstamp).total_seconds())
                l = f"Iteration took {delta} s."
                print(l)
                store.append(l)
                iteration_times.append(delta)
            iteration_tstamp = now
        l = len(line)
        # if l>0:
        prefix = f'{dt.now().strftime('%H:%M:%S')}: ' if args.verbose>2 else ""
        stream.write(prefix + line)
        store.append(line)
        # else:
        #     log.warn("")


    stdout = []
    # stderr = []

    dafny = Command(args.dafnyexec)

    iteration_tstamp = None
    iteration_times = []
    dafny_proc = dafny(arglist,_out=partial(process_output, sys.stdout, stdout), _bg=True, _err_to_out=True, _ok_code=[0,1,2,3,4],_return_cmd=True, _new_session=True)
    # p = sp.Popen(arglist, bufsize=-1, stdout=sp.PIPE, stderr=sp.PIPE, text=True, process_group=0)
    # os.set_blocking(p.stdout.fileno(), False)
    # os.set_blocking(p.stderr.fileno(), False)
    pgid = dafny_proc.pgid 
    logger.debug(f"{pgid=}")

    procs_old = []
    while dafny_proc.is_alive():
        procs = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                proc_pgid = os.getpgid(proc.info['pid'])
                if pgid == proc_pgid:
                    procs.append(proc)
            except:
                pass
        if procs != procs_old:
            logger.info(f"""Child procs: {[f"{proc.info['pid']}({proc.info['name']})" for proc in procs]}""" )
            procs_old = procs
        time.sleep(1)

    dafny_proc.wait()
    atexit.unregister(killProc)

    exit_code = dafny_proc.exit_code
    logger.debug(f"{pgid=}, {exit_code=}")

    print()
    line = f"{iteration_times=}"
    print(line)
    stdout.append(line)
    # if a log file was created, add our own data to it
    if exit_code in [0,2,3,4]:
        with open(f"{logfilename}.{args.format}") as jsonfile:
            try:
                j = json.load(jsonfile)
                verificationResults = j["verificationResults"]
            except:
                logger.error("No verificationResults!")
        d = {}
        d['files']=source_dict
        d['output']=stdout
        d['cmd']=[args.dafnyexec] + arglist
        j["darum"]=d
        with open(f"{logfilename}.{args.format}",mode='w') as jsonfile:
            json.dump(j,jsonfile)
        print(f"Generated augmented logfile at {logfilename}.{args.format}")

    print("\n-----------------------------------------------------------------------------------\n")

    # Check for leaked Z3 processes
    d = dt.now()
    leaked_procs_old = []
    leaked_procs_found = False
    while True:
        elapsed = int((dt.now()-d).total_seconds())
        leaked_procs = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                proc_pgid = os.getpgid(proc.info['pid'])
                if pgid == proc_pgid:
                    leaked_procs.append(proc)
            except:
                pass
        if leaked_procs == []:
            break
        leaked_procs_found = True
        if leaked_procs != leaked_procs_old and elapsed>1:
            for proc in leaked_procs:
                logger.warn(f"Leaked process: {proc.info['name']} PID={proc.info['pid']}")
            leaked_procs_old = leaked_procs
        time.sleep(1)
    if leaked_procs_found and elapsed>1:
        logger.warn(f"Leaked processes finished after {elapsed} secs")

    if (args.no_plotting):# or (exit_code not in [0,1,2,3,4]):
        return exit_code

    pd = Command("plot_distribution")
    pd_args = [
        f"{logfilename}.{args.format}",
        *([f"-{"v"*args.verbose}"] if args.verbose>0 else []),
        *(["--force-IAmode"] if args.isolate_assertions else []),
        *(["--limitRC", str(args.limitRC)] if args.limitRC is not None else []),
    ]

    print(pd(pd_args,_err_to_out=True))

    return exit_code
