"""Static charts for vault notes (PNG). Emphasis form: one accent hue for the series the story is about, gray for context.

Specs follow the house data-viz method: thin surface gaps between touching fills, recessive hairline axes,
text in ink tokens (never the series colour), sparing direct labels, one y-axis.
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

SURFACE = '#fcfcfb'
INK = '#0b0b0b'
INK_2 = '#52514e'
INK_3 = '#8a8984'
ACCENT = '#2a78d6'      # categorical slot 1 (blue), the emphasised series
ACCENT_DARK = '#184f95'  # blue step 600, range whisker on the accent fill
CONTEXT = '#d9d8d3'     # de-emphasis gray for the context series
GRID = '#e6e5e0'
FONTS = ['Helvetica Neue', 'Helvetica', 'Arial', 'DejaVu Sans']

def _style():
    plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':FONTS,'font.size':9,'axes.edgecolor':GRID,
                         'axes.labelcolor':INK_2,'xtick.color':INK_2,'ytick.color':INK_2,'figure.facecolor':SURFACE,'axes.facecolor':SURFACE})

def marimekko(cols, path, title, subtitle, source, width_label='market size'):
    """cols: list of dicts with label, market (USD m), share, share_min, share_max; drawn in the given order.

    Column width = market size; the accent fill rises from the baseline to the domestic share, the gray remainder is
    imports. A thin darker whisker marks the share range. Labels sit above the column when the share is small.
    """
    _style()
    fig=plt.figure(figsize=(11,6.8),dpi=200);ax=fig.add_axes([0.06,0.24,0.92,0.54])
    total=sum(c['market'] for c in cols);gap=total*0.0035;x=0
    for c in cols:
        w=c['market']-gap;s=c['share']
        ax.add_patch(FancyBboxPatch((x,0),w,s,boxstyle='square,pad=0',fc=ACCENT,ec='none'))
        ax.add_patch(FancyBboxPatch((x,s+0.004),w,1-s-0.004,boxstyle='square,pad=0',fc=CONTEXT,ec='none'))
        mid=x+w/2
        if c.get('share_min') is not None and c['share_max']-c['share_min']>0.005:
            ax.plot([mid,mid],[c['share_min'],c['share_max']],color=ACCENT_DARK if c['share_min']<s else INK_2,lw=1.2,solid_capstyle='round',zorder=3)
            for yy in (c['share_min'],c['share_max']):ax.plot([mid-w*0.12,mid+w*0.12],[yy,yy],color=ACCENT_DARK,lw=1.2,zorder=3)
        # Share label: at the foot of the accent fill when it is tall enough (clear of the whisker), else above the range.
        lab=f'{s:.0%}';inside=s>0.1 and w>total*0.025
        top=max(s,c.get('share_max') or s)
        ax.text(mid,0.025 if inside else top+0.025,lab,ha='center',va='bottom',color='white' if inside else INK,fontsize=10,fontweight='bold')
        size=f'${c["market"]/1e3:.1f}bn'
        if w<total*0.05:
            # Narrow column: one vertical label (name and size) keeps neighbours from colliding.
            ax.text(mid,-0.03,f'{c["label"]}  {size}',ha='center',va='top',rotation=90,color=INK,fontsize=8.5)
        else:
            name=c.get('short',c['label']);n=name.count('\n')+1
            ax.text(mid,-0.03,name,ha='center',va='top',color=INK,fontsize=9,linespacing=1.15)
            ax.text(mid,-0.03-0.052*n,size,ha='center',va='top',color=INK_3,fontsize=8)
        x+=c['market']
    ax.set_xlim(0,total);ax.set_ylim(0,1);ax.set_xticks([])
    ax.set_yticks([0,0.25,0.5,0.75,1]);ax.set_yticklabels(['0%','25%','50%','75%','100%'])
    for sp in ('top','right','bottom'):ax.spines[sp].set_visible(False)
    ax.spines['left'].set_color(GRID);ax.tick_params(axis='y',length=0)
    fig.text(0.06,0.955,title,fontsize=13,fontweight='bold',color=INK,ha='left',va='top',linespacing=1.3)
    fig.text(0.06,0.875,subtitle+f' Column width = {width_label}.',fontsize=9,color=INK_2,ha='left',va='top')
    # Legend: swatch beside ink text, two series.
    lx=0.06;ly=0.83
    for colr,text in ((ACCENT,'Domestic vendors (share of China market, with estimates)'),(CONTEXT,'Imports')):
        fig.patches.append(FancyBboxPatch((lx,ly-0.004),0.012,0.018,boxstyle='round,pad=0,rounding_size=0.002',fc=colr,ec='none',transform=fig.transFigure,figure=fig))
        fig.text(lx+0.017,ly+0.005,text,fontsize=8.5,color=INK_2,va='center');lx+=0.017+0.0062*len(text)+0.03
    fig.patches.append(FancyBboxPatch((lx,ly+0.004),0.012,0.0015,boxstyle='square,pad=0',fc=ACCENT_DARK,ec='none',transform=fig.transFigure,figure=fig))
    fig.text(lx+0.017,ly+0.005,'Range (low/high cases)',fontsize=8.5,color=INK_2,va='center')
    fig.text(0.06,0.035,source,fontsize=7.5,color=INK_3,ha='left',va='bottom',wrap=True)
    fig.savefig(path,facecolor=SURFACE);plt.close(fig)
