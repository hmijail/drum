#! python3
"""
Ease bookkeeping of dafny's measure-complexity runs 
by storing the log file with the args in the filename
"""

import argparse
import hashlib
import os
from pathlib import Path
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
    parser.add_argument("dafnyfiles", nargs="+", help="The dafny file(s) to verify.")
    parser.add_argument("-e", "--extra_args", default="", help="Extra arguments to pass to dafny")
    parser.add_argument("-d", "--dafnyexec", default="dafny", help="The dafny executable")
    parser.add_argument("-r", "--rseed", default=str(int(time.time())),help="The random seed. By default is seeded with the current time.")
    parser.add_argument("-i", "--iter", default="10", help="Number of iterations. Default=%(default)s")
    parser.add_argument("-f", "--format", default="json", help=argparse.SUPPRESS) # CVS needs updating
    parser.add_argument("-l", "--limitRC", type=Quantity, default=Quantity("10M"), help="The Resource Count limit. Accepts magnitudes. Default=%(default)s")
    parser.add_argument("-a", "--isolate-assertions",action="store_true", help="Isolate assertions")
    parser.add_argument("-c", "--verify-included-files",action="store_true", help="Verify included files")
    parser.add_argument("-z", "--z3-path", help="Path to Z3")
    parser.add_argument("-o", "--output_dir", default="", help="Directory to store the results. Defaults to current dir")
    parser.add_argument("-v", "--verbose", action="count", default=0)

    args = parser.parse_args()

    numeric_level = log.WARNING - args.verbose * 10
    log.basicConfig(level=numeric_level,format='%(levelname)s:%(message)s')


    IAstr = "IA" if args.isolate_assertions else ""
    VIFstr = "VIF" if args.verify_included_files else ""
    if len(args.dafnyfiles) > 1:
        log.warning("Hashing only the first file!")
    with open(args.dafnyfiles[0], "rb") as f:
        digest = hashlib.file_digest(f, "md5")
    hash = digest.hexdigest()
    dafnyfiles_str = "-".join([os.path.splitext(os.path.basename(f))[0] for f in args.dafnyfiles])+f"{hash[0:4]}"
    z3str = f"Z{Path(args.z3_path).name}" if args.z3_path else ""
    argstring4filename = f"{args.dafnyexec}_{dafnyfiles_str}_IT{args.iter}_L{args.limitRC}_{IAstr}_{VIFstr}_{z3str}_{args.extra_args}".replace("/","").replace("-","").replace(":","").replace(" ","")
    d = dt.now()
    dstr = d.strftime('%Y%m%d-%H%M%S')
    filename = os.path.join(args.output_dir, dstr + "_" + argstring4filename)
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
        *(["--solver-path", args.z3_path] if args.z3_path else []),
        *args.extra_args.split(),
        *args.dafnyfiles
        ]
    log.info(f"Executing:{args.dafnyexec} {' '.join(arglist)}")
    sys.stdout.flush()
    sys.stderr.flush()
    os.execvp(args.dafnyexec, arglist )
