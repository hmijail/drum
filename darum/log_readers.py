import csv
import json
import logging as log
from math import ceil, floor, log10
import re
from datetime import datetime as dt, timedelta as td
import os
import pickle
import sys
from typing import Tuple

def shortenDisplayName(dn:str) -> str:
    new: str = dn.replace(" (well-formedness)","") # WF is almost everywhere, so omit it; better just mention anything non-WF
    new = new.replace(" (correctness)","[C]")
    return new.strip()

class Details: # gathers the results of multiple iterations of verifying a single AB
    def __init__(self) -> None:
        self.displayName: str = "" # without AB
        self.RC: list[int] = []
        self.OoR: list[int] = []   #OutOfResources
        self.failures: list[int] = []
        #self.RC_max: int     #useful for the table
        #self.RC_min: int
        self.loc: str = ""
        self.filename: str = ""
        self.description: str = ""
        self.AB: int = 0 # in IA mode, there's ABs with a number (vcRs) and non-ABs with num 0 (the vRs that sum the RCs of the vcRs)

type resultsType = dict[str, Details] # displayName_with_AB:Details

def mergeResults(r:resultsType, rNew:resultsType):
    if len(rNew) == 0:
        log.warning(f"no results in rNew")
        exit(1)
    for k in rNew:
        if k in r:
            r[k].RC.extend(rNew[k].RC)
            r[k].OoR.extend(rNew[k].OoR)
            r[k].failures.extend(rNew[k].failures)
        else:
            r[k] = rNew[k]

def check_locations_ABs(locations) -> None:
    # checks across the whole file
    for loc,RStoABs in locations.items():
        if len(RStoABs) == 1:
            continue # only 1 rseed, so nothing to compare to check
        ABs_first = None
        # Ensure that, for each location, the ABs stay the same in every run
        for r,ABs in RStoABs.items():
            if ABs_first == None:
                ABs_first = ABs
                # some locations can accumulate many ABs
                # if len(ABs) > 1:
                #     log.debug(f"{loc} has {len(ABs)} ABs: {ABs}")
                continue
            if ABs_first != ABs:
                log.warn(f"{loc} has changing ABs. Until now it was {ABs_first}. But for rseed {r}, it's {ABs}")

def readCSV(fullpath) -> resultsType:
    """Reads the CSV file into the global usages map"""
    raise NotImplementedError("CSV reading needs fixing")
    # needs to be changed to return a resultsType like readJSON does
    # only reason to use CSV is for Dafny <4.5
    rows = 0
    global results
    with open(fullpath) as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            rows += 1
            dn = shortenDisplayName(row['TestResult.DisplayName'])
            rc = row['TestResult.ResourceCount']
            results[dn] = results.get(dn,[]) + [int(rc)]
    log.info(f"{fullpath} :{rows} rows")
    return rows


def readJSON(fullpath: str, paranoid=True) -> resultsType:
    #reads 1 file (possibly containing multiple verification runs)
    results: resultsType = {}

    with open(fullpath) as jsonfile:
        try:
            j = json.load(jsonfile)
            verificationResults = j["verificationResults"]
        except:
            sys.exit("No verificationResults!")
    log.debug(f"{fullpath}: {len(verificationResults)} verificationResults")
    if len(verificationResults) == 0:
        return results
    
    # A JSON verification log contains a list of verificationResults (vR), from all the iterations.
    # Verification iterations are only distinguishable because the randomseed changes.
    # Each vR corresponds to a function, method...
    # and contains its Display Name, overall Resource Count, verification outcome and the vcResults (Assertion Batches)
    #   Each AB contains its number (vcNum), outcome, Resource Count, and a list of assertions
    # If "isolate assertions", split_here, etc were NOT used, then the AB list in a vR will (usually?) contain only 1 AB
    # Conversely, if those are used, then the AB list in a vR will contain multiple ABs
    # So the 2 extremes are: 1 AB with all the assertions, or multiple ABs with 1 assertion each.
    # Assertions contain the filename, line, col, and description.
    # In plots we work at the level of ABs. So if there is more than 1 assertion in 1 AB, then we don't try to represent their locations in the plots/tables.
    # ABs are numbered from 1 onwards.
    #
    # How this translates to our output:
    # The vR stores the summary info for its ABs. Gets AB number 0. Doesn't contain locations, so we pick it from the first of the vR's ABs that contains an assert.
    # We store each AB's info separately. So there's AB0, 1,... n
    # If an AB contains only 1 assert, we store its filename:line:col. If there's more than 1 assert, we only store filename:*.*.
    # Dafny by default reports at the vR level, and we keep that spirit. 
    # AB0 doesn't appear in the "element name", since the vR is not an AB anyway. And lib clients will probably want to ignore AB1 if that's the only one.

    locations: dict[tuple,dict[int,dict[str,str]]] = {} # relate (file,line,col) to {randomseed:{displayname_AB:description}}; allows to compare results per file position
        # the idea is that a given location, across all randomseeds, should have the same ABs and same results/descriptions

    for vr in verificationResults:
        shortDN = shortenDisplayName(vr["name"])
        vr_RC = vr["resourceCount"]

        # the rseed is only present in the vcrs, so get it from the first one
        # we won't store it, it's only used for sanity checking and error reporting
        try:
            vr_rseed = vr['vcResults'][0]['randomSeed']
        except:
            # logs made by `dafny verify` contain no randomSeed
            vr_rseed = None

        det = results.get(shortDN, Details())
        det.AB = 0
        det.displayName = shortDN # they only differ in ABs
        if vr["outcome"] == "Correct":
            det.RC.append(vr_RC)
        elif vr["outcome"] == "OutOfResource":
            det.OoR.append(vr_RC)
            #assert vr["outcome"] != "Errors", f"{vr["name"]}, rseed={vr_rseed} has error outcome!"
        elif vr["outcome"] == "Errors":
                #log.info(f"{vr["name"]}, rseed={vr_rseed} has error outcome")
            det.failures.append(vr_RC)
        else:
            sys.exit(f"{shortDN}.outcome == {vr["outcome"]}: unknown case!")

        vcRs = vr['vcResults']

        #find the filename. The first vcr might have an empty list of assertions (for example in IA mode), so keep trying others.
        filename = None
        for vcr in vcRs:
            try:
                filename = vcr['assertions'][0]["filename"]
                break
            except:
                pass
        assert filename is not None

        det.filename = filename
        results[shortDN] = det

        # We will check that the vr's RC equals the sum of the vcrs' RCs.
        vcrs_RC = []

        ABmax = max([vcr['vcNum'] for vcr in vcRs])
        ABdigits = floor(log10(ABmax)+1) # e.g. log10(99) = 1.x, needs 2 digits
        
        skipping_reason = None
        for vcr in vcRs:
            #TODO tag post-fails, post-OoRs
            #TODO are we diagnosing the case of failed AB vs successful top? Or, failed top vs successful AB?
            assert vr_rseed == vcr["randomSeed"], f"rseed mismatch: {vr_rseed} vs {vcr["randomSeed"]} in {shortDN}"

            # There's multiple ABs. Each AB contains a single assertion
            ABn = vcr['vcNum']
            display_name_AB: str =f"{shortDN} B{ABn:0{ABdigits}}"

            if skipping_reason is not None:
                if skipping_reason=="Fail" and vcr["outcome"] != "Valid":
                    # this situation should be equivalent to "assume False && assert X", so should never fail??
                    log.warn(f"Skipping after an AB failed, yet {display_name_AB}=={vr["outcome"]}")
                continue

            det = results.get(display_name_AB)
            if det is None:
                det = Details()
                det.AB = ABn
                det.displayName = shortDN

            # Extract the filename, location and descriptions
            if len(vcr['assertions'])==0:
                # e.g. every AB1 in IAmode
                if det.loc == "":
                    det.filename = filename #assumed, but what else could it be?
                    det.loc = '-'
                    det.description = '-'
                else:
                    assert det.loc == '-'
            elif len(vcr['assertions'])==1:
                asst = vcr['assertions'][0]
                if det.loc == "":
                    # first appearance
                    det.filename = asst['filename']
                    det.loc = f"{asst['line']}:{asst['col']}"
                    det.description = asst['description']
                else:
                    # just double-check that previous appearances with this display_name + AB are consistent
                    assert det.filename == asst['filename']
                    assert det.loc == f"{asst['line']}:{asst['col']}"
                    assert det.description == asst['description']
            else:
                # more than 1 assertion. Store the line range.
                if det.loc == "":
                    det.filename = filename
                    lines = sorted([asst['line'] for asst in vcr['assertions']])
                    lines_str = f"L{lines[0]}"
                    if lines[0]!=lines[-1]:
                        lines_str+=f"-{lines[-1]}"
                    det.loc=lines_str
                    det.description = '*'
                else:
                    assert det.description == '*'

            # store the location and the ABs in there to check if they stay consistent
            location_current = (det.filename, display_name_AB, det.loc)
            l = locations.get(location_current,{})
            l2 = l.get(vr_rseed,{})
            l2[ABn]=det.description
            l[vr_rseed]=l2
            locations[location_current] = l

            # store the RCs according to result
            vcr_RC = vcr['resourceCount']
            if vcr["outcome"] == "OutOfResource" :
                assert vr["outcome"] == "OutOfResource", f"{display_name_AB}==OoR, {shortDN}=={vr["outcome"]}: unexpected!"
                det.OoR.append(vcr_RC)
                results[display_name_AB] = det
                log.debug(f"{display_name_AB}==OoR, skipping remaining {ABmax-ABn} ABs in {shortDN}")
                skipping_reason = "OoR"
            elif vcr["outcome"] == "Invalid":
                assert vr["outcome"] == "Errors", f"{display_name_AB}==Invalid, {shortDN}=={vr["outcome"]}: unexpected!"
                det.failures.append(vcr_RC)
                results[display_name_AB] = det
                log.debug(f"{display_name_AB}==Invalid, skipping remaining {ABmax-ABn} ABs in {shortDN}")
                skipping_reason = "Fail"
            elif vcr["outcome"] == "Valid":
                det.RC.append(vcr_RC)
                results[display_name_AB] = det
                vcrs_RC.append(vcr_RC)
            else:
                sys.exit(f"{display_name_AB}.outcome == {vcr["outcome"]}: unexpected!")

        if skipping_reason is None: # we reached the end of this vR without fails
            assert sum(vcrs_RC) == vr_RC, f"{shortDN}.RC={vr_RC}, but the sum of the vcrs' RCs is {sum(vcrs_RC)}"
            assert vr["outcome"] == "Correct", f"{shortDN}=={vr["outcome"]} but all its ABs were Valid!"
        else:
            #log.debug(f"Did not check the sum(vcrs_RC)")
            pass
        
    if paranoid:
        check_locations_ABs(locations)

    return results



def readLogs(paths, read_pickle = False, write_pickle = False) -> resultsType:

    results: resultsType = {}
    files = 0
    # to be un/pickled: [files, results]

    t0 = dt.now()
    picklefilepath = "".join(paths)+"v2.pickle"
    if os.path.isfile(picklefilepath) and read_pickle:
        with open(picklefilepath, 'rb') as pf:
            [files, results] = pickle.load(pf)
        print(f"Loaded pickle: {files} files {(dt.now()-t0)/td(seconds=1)}")
        return results
    else:

        for p in paths:
            # os.walk doesn't accept files, only dirs; so we need to process single files separately
            log.debug(f"root {p}")
            if os.path.isfile(p):
                ext = os.path.splitext(p)[1]
                if ext == ".json":
                    results_read = readJSON(p)
                elif ext == ".csv":
                    results_read = readCSV(p)
                else:
                    sys.exit(f"Unknown file extension {ext} in {p}")
                mergeResults(results, results_read)
                files += 1
                continue
            files_before_root = files
            for dirpath, dirnames, dirfiles in os.walk(p):
                files_before = files
                for f in dirfiles:
                    if not ".json" in f:
                        continue
                    files +=1
                    fullpath = os.path.join(dirpath, f)
                    log.debug(f"file {files}: {fullpath}")
                    ext = os.path.splitext(fullpath)
                    if ext == ".json":
                        results_read = readJSON(fullpath)
                    elif ext == ".csv":
                        results_read = readCSV(fullpath)
                    else:
                        sys.exit(f"Unknown file format: {fullpath}")
                    mergeResults(results, results_read)

            if files_before_root == files:
                print(f"no files found in {p}")
                exit(1)


        log.info(f"Processed {files} files in {(dt.now()-t0)/td(seconds=1)}")

        if write_pickle:
            with open(picklefilepath, "wb") as pf:
                pickle.dump([files, results], pf)
        return results

