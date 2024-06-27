#! python3
"""
Ease bookkeeping of dafny's measure-complexity runs 
by storing the log file with the args in the filename
"""

import argparse
import os
import subprocess as sp
import sys
#from shlex import quote
import time
import logging as log
import enum
from datetime import datetime as dt, timedelta as td
from quantiphy import Quantity
from typing import NoReturn

def shell(str, **kwargs):
    """Convenient way to run a CLI string and get its exit code, stdout, stderr.."""
    r = sp.run(str, shell=True, capture_output=True, text=True, **kwargs)
    #print(r)
    return r

def main() -> NoReturn:
    parser = argparse.ArgumentParser(description="Run dafny's measure-complexity and store the verification args in the filename of the resulting log file for easier bookkeeping.")
    parser.add_argument("dafnyfile")
    parser.add_argument("-e", "--extra_args", default="", help="Extra arguments to pass to dafny")
    parser.add_argument("-d", "--dafnyexec", default="dafny", help="The dafny executable")
    parser.add_argument("-r", "--rseed", default=str(int(time.time())),help="The random seed. By default is seeded with the current time.")
    parser.add_argument("-i", "--iter", default="10", help="Number of iterations. Default=%(default)s")
    parser.add_argument("-f", "--format", default="json", help=argparse.SUPPRESS) # bitrotten
    parser.add_argument("-l", "--limitRC", type=Quantity, default=Quantity("10M"), help="The Resource Count limit. Accepts magnitudes. Default=%(default)s")
    parser.add_argument("-a", "--isolate-assertions",action="store_true")
    parser.add_argument("-c", "--verify-included-files",action="store_true")

    args = parser.parse_args()


    loglevel = "debug"
    numeric_level = getattr(log, loglevel.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError('Invalid log level: %s' % loglevel)
    log.basicConfig(level=numeric_level,format='%(levelname)s:%(message)s')

    IAstr = "IA" if args.isolate_assertions else ""
    VIFstr = "VIF" if args.verify_included_files else ""
    argstring4filename = f"{args.dafnyexec}_{args.dafnyfile}_IT{args.iter}_L{args.limitRC}_{IAstr}_{VIFstr}_{args.extra_args}".replace("/","").replace("-","").replace(":","").replace(" ","")
    d = dt.now()
    dstr = d.strftime('%Y%m%d-%H%M%S')
    filename = "TestResults/" + dstr + "_" + argstring4filename
    #log.debug(f"filename={filename}")
    #shell_line = fr"{args.dafnyexec} measure-complexity --log-format csv\;LogFileName='{filename}' {args.extra_args} {args.dafnyfile}"
    #log.info(f"Executing:{args.dafnyexec} {cli_args}")

    arglist = [
        args.dafnyexec,
        "measure-complexity",
        "--random-seed",
        args.rseed,
        "--iterations",
        args.iter,
        "--log-format",
        f"{args.format};LogFileName={filename}.{args.format}",
        "--resource-limit",
        str(int(args.limitRC)),
        "--isolate-assertions" if args.isolate_assertions else "",
        "--verify-included-files" if args.verify_included_files else "",
        *args.extra_args.split(),

        args.dafnyfile
        ]
    log.info(f"Executing:{args.dafnyexec} {' '.join(arglist)}")
    sys.stdout.flush()
    sys.stderr.flush()
    os.execvp(args.dafnyexec, arglist )

