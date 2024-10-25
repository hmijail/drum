#! python3

import argparse
#from matplotlib import table
import panel as pn
from quantiphy import Quantity
import logging as log
from math import inf, nan
import os
import numpy as np
import pandas as pd
from darum.log_readers import Details, readLogs
from quantiphy import Quantity
from pathlib import Path

from bokeh.models import NumeralTickFormatter, HoverTool
from bokeh.util.compiler import TypeScript
from bokeh.models.widgets.tables import NumberFormatter


def smag(i) -> str:
    return f"{Quantity(i):.3}"

def dn_is_excluded(dn, exclude_list):
    for e in exclude_list:
        if e.lower() in dn.lower():
            return True
    return False

def row_from_Details(v: Details):
    minRC_entry = min(v.RC, default=0)
#    minRC = min(minRC, minRC_entry)
    maxRC_entry = max(v.RC, default=0)
#    maxRC = max(maxRC, maxRC_entry)
    # minOoR_entry = min(v.OoR, default=0)
#    minOoR = min(minOoR,minOoR_entry)
    # minFailures_entry = min(v.failures, default=0)
#    minFailures = min(minFailures,minFailures_entry)

    #comment = ""

    # Calculate the % span between max and min
    span = (maxRC_entry-minRC_entry)/minRC_entry if minRC_entry != 0 else 0
    # info = f"{k:40} {len(v.RC):>10} {smag(minRC_entry):>8}    {smag(maxRC_entry):>6} {span:>8.2%}"
    # log.debug(info)
    return {
        "success": len(v.RC),
        "minRC" : minRC_entry,
        "maxRC" : maxRC_entry,
        "span" : span,
        "OoR" : len(v.OoR),
        "fail" : len(v.failures),
        "AB" : v.AB,
        #"comment": comment
    }


class NumericalTickFormatterWithLimit(NumeralTickFormatter):
    min_fail = 0
    min_OoR = 0

    def __init__(self, min_OoR, min_fail, **kwargs):
        super().__init__(**kwargs)
        assert min_OoR < min_fail
        NumericalTickFormatterWithLimit.min_fail = min_fail
        NumericalTickFormatterWithLimit.min_OoR = min_OoR
        NumericalTickFormatterWithLimit.__implementation__ = TypeScript(
"""
import {NumeralTickFormatter} from 'models/formatters/numeral_tick_formatter'

export class NumericalTickFormatterWithLimit extends NumeralTickFormatter {
    static __name__ = '""" + __name__ + """.NumericalTickFormatterWithLimit'
    MIN_FAIL=""" + str(int(min_fail)) + """
    MIN_OOR=""" + str(int(min_OoR)) + """
    doFormat(ticks: number[], _opts: {loc: number}): string[] {
        const formatted = []
        const ticks2 = super.doFormat(ticks, _opts)
        for (let i = 0; i < ticks.length; i++) {
            if (ticks[i] < this.MIN_OOR) {
                formatted.push(ticks2[i])
            } else if (ticks[i] < this.MIN_FAIL) {
                formatted.push('OoR')
            } else {
                formatted.push('FAIL')
            }
        }
        return formatted
    }
}
""")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('path_normal', nargs='+')
    parser.add_argument('-i','--path_IA', nargs='+')
    parser.add_argument("-v", "--verbose", action="count", default=0)
    #parser.add_argument("-p", "--recreate-pickle", default=, action="store_true")
    # parser.add_argument("-n", "--nbins", default=50)
    # #parser.add_argument("-d", "--RCspan", type=int, default=10, help="The span maxRC-minRC (as a % of max) over which a plot is considered interesting")
    # parser.add_argument("-x", "--exclude", action='append', default=[], help="DisplayNames matched by this regex will be excluded from plot")
    # #parser.add_argument("-o", "--only", action='append', default=[], help="Only plot DisplayNames with these substrings")
    parser.add_argument("-t", "--top", type=int, default=20, help="Plot only the top N most interesting")
    # parser.add_argument("-s", "--stop", default=False, action='store_true', help="Process the data but stop before plotting")
    # parser.add_argument("-a", "--IAmode", default=False, action='store_true', help="Isolated Assertions mode. Used only for sanity checking.")
    parser.add_argument("-l", "--limitRC", type=Quantity, default=None, help="The RC limit used during verification. Used only for sanity checking.")
    # parser.add_argument("-b", "--bspan", type=int, default=0, help="The minimum bin span for a histogram to be plotted")

    args = parser.parse_args()

    numeric_level = log.WARNING - args.verbose * 10
    log.basicConfig(level=numeric_level,format='%(asctime)s-%(levelname)s:%(message)s',datefmt='%H:%M:%S')

    product = Path(args.path_normal[0]).name

    log.debug(f"logs_normal={args.path_normal}")
    results_normal = readLogs(args.path_normal)#, args.recreate_pickle)
    log.debug(f"logs_IA={args.path_IA}")
    results_IA = readLogs(args.path_IA)#, args.recreate_pickle)

    # PROCESS THE DATA

    ABs_present = False
    vr_past_limitRC = ""
    df_IA = pd.DataFrame( columns=["minRC", "maxRC", "span", "success", "OoR","fail","AB"])
    df_IA.index.name="Element"

    for k,v in results_IA.items():
        if v.AB>0:
            # we want to make sure that these are results from an IA run
            ABs_present = True
            # but we only care for the function-level results
            continue
        df_IA.loc[k] = row_from_Details(v)

    assert ABs_present

    df_IA.drop(columns=["AB"],inplace=True)
    df_IA["score"] = df_IA["span"] * df_IA["minRC"]
    # df_IA = df_IA.sort_values(["failures","OoRs","score"], ascending=False,kind='stable')
    # df_IA.reset_index(inplace=True)
    # df_IA['Element_ordered'] = [f"{i} {s}" for i,s in zip(df_IA.index,df_IA["Element"])]
    colnames = [e for e in df_IA.columns.values if e != "Element"]
    colnames_IA = [c + " IA" for c in colnames]
    renamer = {c:c_IA for c, c_IA in zip(colnames, colnames_IA)}
    df_IA.rename(columns=renamer, inplace=True)

    df = pd.DataFrame( columns=["minRC", "maxRC", "span", "success", "OoR","fail","AB"])
    df.index.name="Element"
    for k,v in results_normal.items():
        if v.AB!=0:
            continue
        if k not in df_IA.index.values:
            #we only want the same funcs that were contained in the IA file
            continue
        df.loc[k] = row_from_Details(v)
    df.drop(columns=["AB"], inplace=True)
    df["score"] = df["span"] * df["minRC"]
    df = df.sort_values(["fail","OoR","score"], ascending=False,kind='stable')
    dfc =pd.concat([df, df_IA], axis=1)

    df = dfc
    df.reset_index(inplace=True)
    df['Element_ordered'] = [f"{i} {s}" for i,s in zip(df.index,df["Element"])]

    maxRC = max(max(df["maxRC"]),max(df["maxRC IA"]))
    minRC = min(min(df["minRC"]),min(df["minRC IA"]))
    RCmargin1 = maxRC * 1.2
    RCOoR = maxRC * 1.4
    RCmargin2 = maxRC * 1.6
    RCfailure = maxRC * 1.8
    sep = 1.01 #separation between spikes/markers faked into the OoR/fail areas



    # HOLOVIEWS

    import holoviews as hv # type: ignore
    # import hvplot
    # from hvplot import hvPlot
    from holoviews import opts
    # from bokeh.models.tickers import FixedTicker, CompositeTicker, BasicTicker

    hv.extension('bokeh')
    renderer = hv.renderer('bokeh')


    ####### SPIKES

    # A JavaScript function to customize the hovertool
    from bokeh.models import CustomJSHover
    RCFfunc = CustomJSHover(code='''
            var value;
            var modified;
            if (value > ''' + str(int(RCmargin2)) + ''') {
                modified = "FAILED";
            } else if (value > ''' + str(int(RCmargin1)) + ''') {
                modified = "OoR";
            } else {
                modified = value.toString();
            }
            return modified
    ''')

    labels_plotted = df["Element"].values[:args.top]
    nlabs = len(labels_plotted)
    spikes_dict = {}
    scatter_dict = {}
    for i,dn in enumerate(labels_plotted):
        eo = df.loc[df["Element"]==dn,"Element_ordered"].values[0]
        RCs_IA = results_IA[dn].RC
        RCs_normal = results_normal[dn].RC
        # Represent the failures / OoRs with a spike/dot at x=RCfailure
        for n in range(0,len(results_IA[dn].OoR)):
            RCs_IA.append(RCOoR*pow(sep, n))
        for n in range(0,len(results_IA[dn].failures)):
            RCs_IA.append(RCfailure*pow(sep, n))
        for n in range(0,len(results_normal[dn].OoR)):
            RCs_normal.append(RCOoR*pow(sep, n))
        for n in range(0,len(results_normal[dn].failures)):
            RCs_normal.append(RCfailure*pow(sep, n))

        hover2 = HoverTool(
                    tooltips=[
                        ("Func", eo + " IA"),
                        ("ResCount", "@RC{custom}"),
                        ],
                    formatters={
                        "@RC" : RCFfunc,
                        #"dn"  : 'numeral'
                        }
                )
        hover3 = HoverTool(
                    tooltips=[
                        ("Func", "@Name"),
                        ("ResCount", "@RC{custom}"),
                        ],
                    formatters={
                        "@RC" : RCFfunc,
                        #"dn"  : 'numeral'
                        }
                )
        spikes_dict[eo] = hv.Spikes(RCs_IA,kdims="RC").opts(position=nlabs-i-1,tools=[hover2],xaxis="bottom", logx = True)
        scatter_dict[eo] = hv.Scatter((
                RCs_normal,
                [nlabs-i-0.5]*len(RCs_normal),
                [eo]*len(RCs_normal)
                ),
            kdims="RC",
            vdims=["y", "Name"]
            ).opts(
                    tools=[hover3],
                    xaxis="bottom",
                    logx = True,
                    marker='x',
                    size=10,
                    show_grid=True,
                    xlabel="Log(RC)",
                    ylabel="Func"
                )

    yticks = [(nlabs-i-0.5, list(spikes_dict.keys())[i]) for i in range(nlabs)]#-1,-1,-1)]
    spikes = hv.NdOverlay(spikes_dict).opts(
        yticks = yticks
        )
    scatter = hv.NdOverlay(scatter_dict).opts(
        yticks = yticks
        )

    spikes.opts(
        opts.Spikes(spike_length=1,
                    #line_alpha=1,
                    responsive=True,
                    height=100+nlabs*20,
                    color=hv.Cycle(),
                    ylim=(0,nlabs+1),
                    #autorange=None,
                    yaxis='right',
                    backend_opts={
                        # "xaxis.bounds" : (0,RCfailure)
                        },
                    title="X = normal mode    | = Isolated Assertions mode",
                    show_legend=False,
                    ),

        opts.NdOverlay(show_legend=False,
                        click_policy='mute',
                        autorange=None,
                        ylim=(0,nlabs+1),
                        #xlim=(3000,RCfailure),
                        padding=(0.05),
                        fontscale=1.5
                    ),
        #opts.NdOverlay(shared_axes=True, shared_datasource=True,show_legend=False)
        )

    scatter.opts(
        opts.Scatter(
                responsive=True,
                height=100+nlabs*20,
                color=hv.Cycle(),
                size=20,
                #ylim=(0,nlabs),
                #autorange=None,
                yaxis='right',
                #backend_opts={
                    #"xaxis.bounds" : (0,bins_plot[-1]+bin_width)
                #    },
                show_legend=False,
                ),
        opts.NdOverlay(show_legend=False,
            click_policy='mute',
            autorange=None,
            ylim=(0,nlabs),
            #xlim=(3000,RCfailure),
            padding=(0.05),
        ),

    )

    vspan = hv.VSpan(RCmargin1).opts(
        opts.VSpan(color='#FF000030',show_legend=False) # transparent red
    )
    vspan = vspan * hv.VSpan(RCmargin2).opts(
        opts.VSpan(color='#FF000030',show_legend=False)
    )

    # TABLE

    df.drop(columns=["Element_ordered"], inplace=True)
    df["span"] = df["span"].apply(lambda d: nan if np.isnan(d) else int(d*10000)/100)
    df["span IA"] = df["span IA"].apply(lambda d: nan if np.isnan(d) else int(d*10000)/100)
    df["minRC"] = df["minRC"].apply(lambda x: x if abs(x)<inf else "-")
    df["minRC IA"] = df["minRC IA"].apply(lambda x: x if abs(x)<inf else "-")
    df["maxRC"] = df["maxRC"].apply(lambda x: x if abs(x)<inf else "-")
    df["maxRC IA"] = df["maxRC IA"].apply(lambda x: x if abs(x)<inf else "-")
    df["success"] = df["success"].apply(lambda x: x if x!=0 else "-")
    df["success IA"] = df["success IA"].apply(lambda x: x if x!=0 else "-")
    df["OoR"] = df["OoR"].apply(lambda x: x if x!=0 else "-")
    df["OoR IA"] = df["OoR IA"].apply(lambda x: x if x!=0 else "-")
    df["fail"] = df["fail"].apply(lambda x: x if x!=0 else "-")
    df["fail IA"] = df["fail IA"].apply(lambda x: x if x!=0 else "-")

    df.rename(columns={
            "span":"RCspan%",
            "span IA":"RCspan% IA",
        },inplace=True)

    print(df)

    bokeh_formatters = {
        'minRC': NumberFormatter(format='0,0', text_align = 'right'),
        'maxRC': NumberFormatter(format='0,0', text_align = 'right'),
        # 'RCspan%': NumberFormatter(format='0.00', text_align = 'right'),
        'score': NumberFormatter(format='0,0', text_align = 'right'),
        'success': NumberFormatter(format='0,0', text_align = 'right'),
        'fail': NumberFormatter(format='0,0', text_align = 'right'),
        'OoR': NumberFormatter(format='0,0', text_align = 'right'),
    }
    bf_keys = list(bokeh_formatters.keys())
    for k in bf_keys:
        bokeh_formatters[k+" IA"]=NumberFormatter(format='0,0', text_align = 'right')

    table = pn.widgets.Tabulator(df,
            pagination=None,
            frozen_columns=['index'],
            disabled=True,
            layout='fit_data_table',
            selectable=False,
            text_align={"diag":"center"},
            formatters=bokeh_formatters,
            height=300) #give a glimpse of more rows

    # table = hv.Div("<h2>Normal mode:</h2>").opts(height=50) + table


    hvplot = scatter * spikes * vspan
    # hvplot.cols(1)

    mf = NumericalTickFormatterWithLimit(RCmargin1, RCfailure, format="0.0a")

    hvplot.opts(
    #     #opts.Histogram(responsive=True, height=500, width=1000),
        # opts.Layout(sizing_mode="scale_both", shared_axes=True, sync_legends=True, shared_datasource=True)
        opts.NdOverlay(
            click_policy='mute',
            autorange='y',
            xformatter=mf,
            #legend_position="right",
            responsive=True,
            show_legend=False,
            )
    )

    pane_title = pn.pane.Markdown(f"# {product}")
    table_title = pn.pane.Markdown(f"## Comparison normal mode vs IA mode")
    plot = pn.Column(pane_title, hvplot, table_title, table)

    # plot.opts(shared_axes=True)

    # fig = hv.render(plot)
    # #hb = fig.traverse(specs=[hv.plotting.bokeh.Histogram])

    # fig.xaxis.bounds = (0,bin_fails)

    #title = "".join(args.paths)
    plotfilepath = product+".html"

    try:
        os.remove(plotfilepath)
    except:
        pass

    plot.save(plotfilepath)#, title=title)


    print(f"Created file {plotfilepath}")
    os.system(f"open {plotfilepath}")

    # Repeat the warning
    # if args.limitRC is None:
    #     if minOoR < inf:
    #         log.warning(f"There are OoR results, but no limitRC was given. Min OoR found = {smag(minOoR)}")


    #webbrowser.open('plot.html')

    # ls = hv.link_selections.instance()
    # lplot = ls(plot)
    # hv.save(lplot, 'lplot.html')
    # os.system("open lplot.html")


# for easier debugging
if __name__ == "__main__":
    main()