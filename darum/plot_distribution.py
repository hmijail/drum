#! python3

import argparse
import math
import re
import sys
# from matplotlib import table
from quantiphy import Quantity
import logging as log
from math import inf, nan
import os
import numpy as np
import pandas as pd
from darum.log_readers import Details, readLogs
from quantiphy import Quantity
import holoviews as hv  # type: ignore
import hvplot           # type: ignore
from hvplot import hvPlot
from holoviews import opts
from bokeh.models.tickers import FixedTicker, CompositeTicker, BasicTicker
from bokeh.models import NumeralTickFormatter, HoverTool
from bokeh.util.compiler import TypeScript
from bokeh.settings import settings
import os
import glob
import panel as pn

def smag(i) -> str:
    return f"{Quantity(i):.3}"

def dn_is_excluded(dn, exclude_list):
    for e in exclude_list:
        if e.lower() in dn.lower():
            return True
    return False



class NumericalTickFormatterWithLimit(NumeralTickFormatter):
    fail_min = 0

    def __init__(self, fail_min:int, **kwargs):
        super().__init__(**kwargs)
        NumericalTickFormatterWithLimit.fail_min = fail_min
        NumericalTickFormatterWithLimit.__implementation__ = TypeScript(
"""
import {NumeralTickFormatter} from 'models/formatters/numeral_tick_formatter'

export class NumericalTickFormatterWithLimit extends NumeralTickFormatter {
    static __name__ = '""" + __name__ + """.NumericalTickFormatterWithLimit'
    FAIL_MIN=""" + str(int(fail_min)) + """

    doFormat(ticks: number[], _opts: {loc: number}): string[] {
        const formatted = []
        const ticks2 = super.doFormat(ticks, _opts)
        for (let i = 0; i < ticks.length; i++) {
            if (ticks[i] < this.FAIL_MIN) {
                formatted.push(ticks2[i])
            } else {
                formatted.push('FAILED')
            }
        }
        return formatted
    }
}
""")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('paths', nargs='*', help="File/s to plot. If absent, tries to plot the latest file in the current dir.")
    parser.add_argument("-v", "--verbose", action="count", default=0)
    parser.add_argument("-p", "--recreate-pickle",action="store_true")
    parser.add_argument("-n", "--nbins", default=50)
    #parser.add_argument("-d", "--RCspan", type=int, default=10, help="The span maxRC-minRC (as a % of max) over which a plot is considered interesting")
    parser.add_argument("-x", "--exclude", action='append', default=[], help="DisplayNames matched by this regex will be excluded from plot")
    #parser.add_argument("-o", "--only", action='append', default=[], help="Only plot DisplayNames with these substrings")
    parser.add_argument("-t", "--top", type=int, default=5, help="Plot only the top N most interesting. Default: %(default)s")
    parser.add_argument("-s", "--stop", default=False, action='store_true', help="Process the data but stop before plotting.")
    # parser.add_argument("-a", "--IAmode", default=False, action='store_true', help="Whether Isolated Assertions mode was used during verification. Used only to check consistency of results.")
    parser.add_argument("-l", "--limitRC", type=Quantity, default=None, help="The RC limit that was used during verification. Used only to check consistency of results. Default: %(default)s")
    parser.add_argument("-b", "--bspan", type=int, default=0, help="A function's histogram will only be plotted if it spans => BSPAN bins. Default: %(default)s")

    args = parser.parse_args()

    numeric_level = log.WARNING - args.verbose * 10
    log.basicConfig(level=numeric_level,format='%(asctime)s-%(levelname)s:%(message)s',datefmt='%H:%M:%S')

    if not args.paths:
        # Get the path of the latest file in the current directory
        latest_file = max(glob.glob("*"), key=os.path.getmtime)
        if latest_file.endswith(".json"):
            log.info("Plotting latest file in current dir: {os.path.basename(latest_file)}")
            args.paths.append(latest_file)
        else:
            sys.exit("Error: No file given, and latest file is not JSON.")

    results = readLogs(args.paths, args.recreate_pickle)

    # PROCESS THE DATA

    # Calculate the max-min span for each DisplayName, and the global maxRC, minRC, minFail
    maxRC = -inf
    minRC = inf
    maxRC_ABs = -inf
    minRC_ABs = inf
    minOoR = inf # min RC of the OoR entries
    minFailures = inf # min RC of the failed entries
    maxFailures = -inf # max RC of the failed entries
    df = pd.DataFrame( columns=["minRC", "maxRC", "span", "successes", "OoRs","failures","AB","loc","comment","displayName","postOoR", "postFailure"])
    df.index.name="element"

    ABs_present = False
    for k,v in results.items():
        if v.AB>0:
            ABs_present = True
            break

    for k,v in results.items():
        # for ig in args.exclude:
        #     if ig in k:
        #         log.debug(f"Excluding {k}")
        #         continue
        minRC_entry = min(v.RC, default=inf)
        minRC = min(minRC, minRC_entry)
        maxRC_entry = max(v.RC, default=-inf)
        maxRC = max(maxRC, maxRC_entry)
        minOoR_entry = min(v.OoR, default=inf)
        minOoR = min(minOoR,minOoR_entry)
        minFailures_entry = min(v.failures, default=inf)
        minFailures = min(minFailures,minFailures_entry)
        maxFailures_entry = max(v.failures, default=-inf)
        maxFailures = max(maxFailures,maxFailures_entry)
        if v.AB>0:
            # maxRC and minRC include non-ABs, so they aren't useful in IA mode
            minRC_ABs = min(minRC_ABs, minRC_entry)
            maxRC_ABs = max(maxRC_ABs, maxRC_entry)
        comment = ""

        # if a limit was given, we can do some fine grained checks
        if args.limitRC is not None and (v.AB>0 or (not ABs_present and v.AB==0)):
            # any RC > limitRC should be in the OoRs, not in the RCs
            # but beware, in IAmode, the vRs' RC is the sum of its ABs, so they can legitimately have RCs > limitRC
            if maxRC_entry > args.limitRC:
                sys.exit(f"LimitRC={args.limitRC} but {k}({v.AB=}) has maxRC={Quantity(maxRC_entry)}. Should be OoR! ")
            if minOoR_entry < args.limitRC:
                log.warning(f"MinOoR for {k} is {min(v.OoR)}, should be > {args.limitRC=}")
        # Calculate the % span between max and min
        span = (maxRC_entry-minRC_entry)/minRC_entry if minRC_entry != 0 else 0
        info = f"{k:40} {len(v.RC):>10} {smag(minRC_entry):>8}    {smag(maxRC_entry):>6} {span:>8.2%}"
        log.debug(info)
        lincol = "" if v.line == 0 else f":{v.line}:{v.col}"
        df.loc[k] = {
            "successes": len(v.RC),
            "minRC" : minRC_entry,
            "maxRC" : maxRC_entry,
            "span" : span,
            "OoRs" : len(v.OoR),
            "failures" : len(v.failures),
            "AB" : v.AB,
            "loc"   : f"{v.filename}{lincol}",
            "comment": comment,
            "displayName": v.displayName
        }

    minFailures = Quantity(minFailures)
    minOoR = Quantity(minOoR)
    # assert maxRC < minFail

    df["weighted_span"] = df["span"] * df["minRC"]

    if ABs_present:
        # if an AB isn't successful, tag the following ones in its displayName as poisoned
        df.sort_values(["displayName","AB"], ascending=False,kind='stable', inplace=True)
        DNs = set(df["displayName"].values)

        # poisonDN = None
        for d in DNs:
            df_OoRABs = df[(df.displayName==d) & (df.AB>0) & (df.OoRs>0)]
            if not df_OoRABs.empty:
                for a in df_OoRABs.AB:
                    df.loc[(df.displayName==d) & (df.AB>a),"postOoR"] += 1

            df_failedABs = df[(df.displayName==d) & (df.AB>0) & (df.failures>0)]
            if not df_failedABs.empty:
                for a in df_failedABs.AB:
                    df.loc[(df.displayName==d) & (df.AB>a),"postFailure"] += 1

            # for a in sorted(df[df["displayName"]==d]["AB"].values):
            #     if a == 0:
            #         continue
            #     row_df = df[(df["displayName"]==d) & (df["AB"]==a)]
            #     if row_df.at["failures"]>0 or row_df.at["OoRs"]>0:
            #         df[df["displayName"]==d & df["AB"]>a]["comment"] += "❓"

            # if df.loc[i,"AB"]==0:
            #     poisonDN = None
            # else:
            #     if df.loc[i,"displayName"] == poisonDN:
            #         df.loc[i,"comment"] += "❓"
            #     else:
            #         if df.loc[i,"failures"]>0 or df.loc[i,"OoRs"]>0:
            #             curAB = df.loc[i,"AB"]
            #             poisonDN = df.loc[i,"displayName"]

    df.sort_values(["failures","OoRs","weighted_span"], ascending=False,kind='stable', inplace=True)#.drop("weighted_span")

    # IA logs contain both vrs and vcrs. Separate them.
    df_ABs = df[df["AB"]>0]
    if df_ABs.empty:
        df_vrs = None
        df = df
    else:
        df_vrs = df[df["AB"] == 0]
        df = df_ABs

    df.reset_index(inplace=True)
    df['element_ordered'] = [f"{i} {s}" for i,s in zip(df.index,df["element"])]

    if args.limitRC is None:
        if minOoR < inf:
            mRC = minRC_ABs if ABs_present else minRC
            if minFailures < inf:
                mRC = max(minFailures,mRC)
            log.warning(f"Logs contain OoR results, but no limitRC was given. Minimum OoR RC found = {minOoR}.")
            assert minOoR > mRC, f"LimitRC must have been <= {minOoR}, yet some results are higher: minRC={mRC}, {minFailures=}"
            OoRstr = f"OoR > {minOoR}"
        else:
            OoRstr = ""
    else:
        # we did some checking at the single-result-level while digesting the logs; here we can do global checks
        m = maxRC_ABs if ABs_present else maxRC
        if args.limitRC < m:
            log.warn(f"{args.limitRC=}, yet some results are higher: {m}")
        if  maxFailures > args.limitRC:
            log.info(f"{maxFailures=} is greater than {args.limitRC=}")
        assert args.limitRC < minOoR, f"{args.limitRC=}, yet some OoR results are lower: {minOoR=}"
        if minOoR < inf and  minOoR > args.limitRC * 1.5:
            # was a purposefully low limit given just to silence the warnings?
            log.warning(f"The given LimitRC is quite smaller than the min OoR found = {minOoR}. Might be incorrect.")
        OoRstr = f"OoR > {args.limitRC}"

    failstr: str = OoRstr #"FAILED"# + fstr

    # PREPARATORY CALCULATIONS TO PLOT THE RESULTS

    # When plotting all histograms together, the result distribution might cause some DNs' bars
    # to fall too close together; the plot is not helpful then.
    # So let's remove such histograms.
    # For that, first we need to calculate all the histograms.
    # And for that, we need to decide their bins.
    # So get the min([minRCs]) and max([maxRCs]) of the top candidates.
    df["excluded"] = df["element"].map(lambda dn: dn_is_excluded(dn, args.exclude)).astype(bool)

    minRC_plot = min(df[~df["excluded"]].iloc[0:args.top]["minRC"])
    maxRC_plot = max(df[~df["excluded"]].iloc[0:args.top]["maxRC"])

    # The histograms have the user-given num of bins between minRC_plot and maxRC_plot,
    # + filler to the left until x=0, + 2 bins if there are fails (margin and fails bar)
    with np.errstate(invalid='ignore'): # silence RuntimeWarnings for inf values
        # those values could be in min/maxRC_plot if all plots are for funcs that failed for all random seeds
        bins = np.linspace(Quantity(minRC_plot),Quantity(maxRC_plot), num=args.nbins+1)
    bin_width = bins[1]-bins[0]

    log.info(f"{args.nbins=}, range {smag(minRC_plot)} - {smag(maxRC_plot)}, bin width {smag(bin_width)}")
    plotting_fails = (minOoR != inf) or (minFailures != inf)
    bin_margin = bins[-1] + 3 * bin_width
    bin_fails = bin_margin + 3 * bin_width
    bins_with_fails = np.append(bins,[bin_margin,bin_fails])

    labels_plotted = []
    bins_plot = bins_with_fails if plotting_fails else bins
    bin_centers = 0.5 * (bins_plot[:-1] + bins_plot[1:])
    bin_labels = [smag(b) for b in bin_centers]
    if plotting_fails:
        bin_labels = bin_labels[0:-2] + ["",failstr ]
    hist_df = pd.DataFrame(index = bin_centers)
    plotted = 0
    for i,row in df.iterrows():
        if row.excluded:
            row.comment += "⛔️"
            continue
        dnab = row.element
        d = results[dnab]
        nfails = len(d.OoR)+len(d.failures)
        counts, _ = np.histogram(d.RC,bins=bins)
        if plotting_fails:
            counts = np.append(counts,[0,nfails])

        # remove uninteresting plots: those without fails that would span less than <bspan> bins
        nonempty_bins = []
        for b,c in enumerate(counts):
            if c != 0:
                nonempty_bins.append(b)
        bin_span = nonempty_bins[-1]-nonempty_bins[0]

        if (nfails > 0) or (bin_span >= args.bspan):
            labels_plotted.append(dnab)
            hist_df[dnab] = counts
            with np.errstate(divide='ignore'): # to silence the errors because of log of 0 values
                hist_df[dnab+"_log"] = np.log10(counts)
            hist_df[dnab+"_log"] = hist_df[dnab+"_log"].apply(
                lambda l: l if l!=0 else 0.2    # log10(1) = 0, so it's barely visible in plot. log10(2)=0.3. So let's plot 1 as 0.2
                )
            hist_df[dnab+"_RCbin"] = bin_labels # for the hover tool
            row.comment+="📊" #f"F={len(d.failures)} O={len(d.OoR)}"
            plotted += 1
        else:
            #row.comment+=f"{bin_span=}"
            pass
        if plotted >= args.top:
            break

    print(df.drop(columns=["element_ordered","AB","excluded","displayName"])
            .rename(columns={
                "span"          : "RC span %",
                "weighted_span" : "minRC * span"
                })
            .head(args.top)
            .to_string (formatters={
                    'maxRC':smag ,
                    'minRC':smag,
                    #'OoRs':smag,
                    #'failures':smag,
                    "RC span %":lambda d:f"{d:>8.2%}"
                    },
                #max_rows=8
                )
            )

    can_plot = not np.isnan(bin_width)

    if args.stop:
        log.info("Stopping as requested.")
        return(0)

    # HOLOVIEWS



    hv.extension('bokeh')
    renderer = hv.renderer('bokeh')
    # settings.log_level('debug')
    # settings.py_log_level('debug')
    # settings.validation_level('all')

    if can_plot:
        histplots_dict = {}
        jitter = (bin_width)/len(labels_plotted)/3
        for i,dn in enumerate(labels_plotted):
            eo = df[df["element"]==dn]["element_ordered"].values[0]
            h = hv.Histogram(
                    (bins_plot+i*jitter,
                        hist_df[dn+"_log"],
                        hist_df[dn],
                        hist_df[dn+"_RCbin"]
                        ),
                    kdims=["RC"],
                    vdims=["LogQuantity", "Quantity", "RCbin"]
                )
            histplots_dict[eo] = h

        hover = HoverTool(tooltips=[
            ("Element", "@Element"),
            ("ResCount bin", "@RCbin"),
            ("Quantity", "@Quantity"),
            ("Log(Quantity)", "@LogQuantity"),
            ])


        bticker = BasicTicker(min_interval = 10**math.floor(math.log10(bin_width)), num_minor_ticks=0)

        hists = hv.NdOverlay(histplots_dict)#, kdims='Elements')
        hists.opts(
            opts.Histogram(alpha=0.9,
                            responsive=True,
                            height=500,
                            tools=[hover],
                            show_legend=True,
                            muted=True,
                            backend_opts={
                            "xaxis.bounds" : (0,bins_plot[-1]+bin_width),
                            "xaxis.ticker" : bticker
                                },
                            autorange='y',
                            ylim=(0,None),
                            xlim=(0,bins_plot[-1]+bin_width),
                            xlabel="RC bins",
                            padding=((0.1,0.1), (0, 0.1)),
                ),
            #,logy=True # histograms with logY have been broken in bokeh for years: https://github.com/holoviz/holoviews/issues/2591
            opts.NdOverlay(show_legend=True,)
            )

        # A vertical line separating the fails bar
        # disabled because it disables the autoranging of the histograms
        # vline = hv.VLine(bin_centers[-2]).opts(
        #     opts.VLine(color='black', line_width=3, autorange='y',ylim=(0,None))
        # )
        # vspan = hv.VSpan(bin_centers[-2],bin_centers[-1]).opts(
        #     opts.VSpan(color='red', autorange='y',ylim=(0,None),apply_ranges=False)
        # )

        # hists = hists * vspan


        ####### SPIKES

        # A JavaScript function to customize the hovertool
        from bokeh.models import CustomJSHover

        RCFfunc = CustomJSHover(code='''
                var value;
                var modified;
                if (value > ''' + str(int(maxRC_plot)) + ''') {
                    modified = "''' + failstr + '''";
                } else {
                    modified = value.toString();
                }
                return modified
        ''')

        nlabs = len(labels_plotted)
        spikes_dict = {}
        for i,dn in enumerate(labels_plotted):
            eo = df[df["element"]==dn]["element_ordered"].values[0]
            RC = results[dn].RC
            # Represent the failures / OoRs with a spike in the last bin
            if results[dn].OoR != [] or results[dn].failures != []:
                RC.append(bin_centers[-1])
            hover2 = HoverTool(
                        tooltips=[
                            ("Element", dn),
                            ("ResCount", "@RC{custom}"),
                            ],
                        formatters={
                            "@RC" : RCFfunc,
                            "dn"  : 'numeral'
                        }
                    )
            spikes_dict[eo] = hv.Spikes(RC,kdims="RC").opts(position=nlabs-i-1,tools=[hover2],xaxis="bottom")

        yticks = [(nlabs-i-0.5, list(spikes_dict.keys())[i]) for i in range(nlabs)]#-1,-1,-1)]
        spikes = hv.NdOverlay(spikes_dict).opts(
            yticks = yticks
            )

        spikes.opts(
            opts.Spikes(spike_length=1,
                        line_alpha=1,
                        responsive=True,
                        height=50+nlabs*20,
                        color=hv.Cycle(),
                        ylim=(0,nlabs),
                        autorange=None,
                        yaxis='right',
                        backend_opts={
                            "xaxis.bounds" : (0,bins_plot[-1]+bin_width)
                            },
                        ),
            opts.NdOverlay(show_legend=False,
                            click_policy='mute',
                            autorange=None,
                            ylim=(0,nlabs),
                            xlim=(0,bins_plot[-1]+bin_width),
                            padding=((0.1,0.1), (0, 0.1)),
                        ),
            #opts.NdOverlay(shared_axes=True, shared_datasource=True,show_legend=False)
            )

    # TABLE/S

    # df["minRC"] = df["minRC"].apply(smag)
    # df["maxRC"] = df["maxRC"].apply(smag)
    # df["span"] = df["span"].apply(lambda d:f"{d:>8.2%}")
    df["span"] = df["span"].apply(lambda d: nan if np.isnan(d) else int(d*10000)/100)
    table_plot = hv.Table(df.drop(columns=["element_ordered","AB","excluded","displayName"])
                        .rename(
                            columns={
                                "span":"RC span (%)",
                                "weighted_span" : "minRC * span"
                                }),
                        kdims="element"
                    ).opts(height=260,width=1000)

    if df_vrs is not None:
        # df_vrs["minRC"] = df_vrs["minRC"].apply(smag)
        # df_vrs["maxRC"] = df_vrs["maxRC"].apply(smag)
        # df_vrs["span"] = df_vrs["span"].apply(lambda d:f"{d:>8.2%}")
        df_vrs["span"] = df_vrs["span"].apply(lambda d:nan if np.isnan(d) else int(d*10000)/100)
        table_vrs = hv.Table(df_vrs.drop(columns=["AB","displayName"]).rename(
                            columns={
                                "span":"RC span (%)",
                                "weighted_span" : "minRC * span"
                                }),
                        kdims="element"
                    ).opts(height=310,width=1000)
        table_plot = ( table_plot +
                    hv.Div("<h2>Per-function totals (in Isolated Assertions mode):</h2>").opts(height=50) +
                    table_vrs)
        # table_plot.opts(
        #     opts.Table(
        #         backend_opts={
        #             "autosize_mode" : "fit_viewport"
        #         },
        #     )
        # )

    if can_plot:
        plot = hists + spikes + table_plot #+ hist #+ violin
        mf = NumericalTickFormatterWithLimit(bin_margin, format="0.0a")

        plot.opts(
        #     #opts.Histogram(responsive=True, height=500, width=1000),
            # opts.Layout(sizing_mode="scale_both", shared_axes=True, sync_legends=True, shared_datasource=True)
            opts.NdOverlay(
                click_policy='mute',
                autorange='y',
                xformatter=mf,
                legend_position="right",
                responsive=True
                )
        )
        plot.opts(shared_axes=True)
    else:
        plot = table_plot

    plot.cols(1)

    # fig = hv.render(plot)
    # #hb = fig.traverse(specs=[hv.plotting.bokeh.Histogram])

    # fig.xaxis.bounds = (0,bin_fails)

    title = "".join(args.paths)
    plotfilepath = "".join(args.paths)+".html"

    try:
        os.remove(plotfilepath)
    except:
        pass

    #renderer.save(plot, 'plot')
    # from bokeh.resources import INLINE
    hv.save(plot, plotfilepath, title=title) #resources='inline')
    #hvplot.show(plot)
    #plot.save(plotfilepath)#, resources=INLINE)

    print(f"Created file {plotfilepath}")
    os.system(f"open {plotfilepath}")

    # Repeat the warning
    if args.limitRC is None:
        if minOoR < inf:
            log.warning(f"There are OoR results, but no limitRC was given. Min failed RC found = {smag(minOoR)}")


    #webbrowser.open('plot.html')

    # ls = hv.link_selections.instance()
    # lplot = ls(plot)
    # hv.save(lplot, 'lplot.html')
    # os.system("open lplot.html")

    return 0


# for easier debugging
if __name__ == "__main__":
    main()
