"""Process-flow overview for the report's tools section: how the HBM tools fit together, from DRAM wafer to stack.

Drawn from process descriptions in working notes (not distributed: tsv_etch, tsv_cmp_reveal, temp_bond_debond,
thinning, microbump_litho, singulation, stacking_tcb, molding), which cite SK hynix and Amkor. Uses no Atlas data.
"""
from pathlib import Path
import textwrap
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, Circle
from sme_analysis import charts, manifest

HERE = Path(__file__).parent
# A stage is (number, name, where, items). Items: ('tool', label) is a tool covered in the report; ('pair', (a, b)) two tools
# used together; ('step', label) another step, for context; ('alt', label) a later-generation alternative; ('out', label) the product.
STAGES = [
    ('1','Front-end DRAM','Memory cells and wiring',[('tool','Deposition'),('pair',('Track','Lithography')),('tool','Etch'),
        ('tool','Ion implant'),('tool','Thermal'),('tool','Cleaning'),('tool','CMP')]),
    ('2','TSV formation','After the transistors',[('step','Via pattern (lithography)'),('tool','Etch (Bosch deep silicon)'),
        ('tool','Insulation, barrier and seed'),('tool','ECP fill (copper)'),('tool','CMP (copper overburden)'),('step','Then the wiring layers')]),
    ('3','Front-side bumps','On the full wafer',[('tool','Microbump lithography'),('tool','Microbump plating'),('step','Resist strip, seed etch, reflow')]),
    ('4','Thin and reveal','Wafer on a carrier',[('step','Edge trim'),('tool','Temporary bond'),('tool','Thinning (back-grind)'),
        ('tool','CMP reveal (with etch)'),('tool','Back-side bumps: microbump litho and plating'),('tool','De-bond')]),
    ('5','Stack and mold','Onto a base-die wafer',[('tool','Dicing (core dies)'),('tool','Thermo-compression bonding'),
        ('alt','or hybrid bonding (later generations)'),('tool','Molding'),('step','Grind, then dice into stacks'),('out','12-high HBM3E stack')]),
]
COLS = [(.08,1.26),(1.5,1.0),(2.66,.94),(3.76,1.02),(4.94,.98)]  # x, width (inches); column 1 leaves room for the loop
EDGE, BOX, STEP_INK, FILL, WAFER, DARK = '#8a8984', '#ffffff', '#6b6a66', '#efeeea', '#d6d4ce', '#5a5955'
NOTES = ('Simplified via-middle flow, as SK hynix describes it. The front-end loop repeats for each layer, hundreds of steps in all. TSV formation '
         'and both rounds of bumping reuse lithography, deposition and plating. The base die is also made in a DRAM fab. Memory test is not shown.')

def wrap(label, width):return textwrap.wrap(label,max(10,int(width*21)),break_on_hyphens=False)

def item_height(kind, label, width):
    if kind=='pair':return .19
    n=len(wrap(label,width-.08));return (.1+.095*n) if kind!='step' else (.05+.095*n)

def icon(ax, stage, x, y, w):
    """Side view of the wafer or stack at the end of each stage, roughly to scale in spirit only."""
    cx=x+w/2;ww=.78;l=cx-ww/2
    if stage in '123':
        ax.add_patch(Rectangle((l,y+.12),ww,.1,facecolor=WAFER,edgecolor=EDGE,lw=.4))
        ax.add_patch(Rectangle((l,y+.12),ww,.025,facecolor=DARK,lw=0))
        if stage in '23':
            for i in range(6):ax.add_patch(Rectangle((l+.08+i*.12,y+.12),.012,.065,facecolor='#b87333',lw=0))
        if stage=='3':
            for i in range(6):ax.add_patch(Circle((l+.086+i*.12,y+.115),.016,facecolor='#9a9893',lw=0))
    elif stage=='4':
        ax.add_patch(Rectangle((l,y+.17),ww,.06,facecolor='#c9c7c1',edgecolor=EDGE,lw=.4))
        ax.add_patch(Rectangle((l,y+.155),ww,.015,facecolor='#e9e1c9',lw=0))
        ax.add_patch(Rectangle((l,y+.13),ww,.025,facecolor=WAFER,edgecolor=EDGE,lw=.4))
        for i in range(6):
            ax.add_patch(Rectangle((l+.08+i*.12,y+.13),.012,.025,facecolor='#b87333',lw=0))
            ax.add_patch(Circle((l+.086+i*.12,y+.127),.012,facecolor='#9a9893',lw=0))
        ax.text(cx,y+.2,'carrier',fontsize=5,color=STEP_INK,ha='center',va='center')
    else:
        bw=.5;bl=cx-bw/2
        ax.add_patch(Rectangle((bl-.06,y+.005),bw+.12,.235,facecolor='#f4f3ef',edgecolor=EDGE,lw=.4))
        ax.add_patch(Rectangle((bl-.04,y+.2),bw+.08,.03,facecolor='#c9c7c1',lw=0))
        for k in range(5):
            yy=y+.165-k*.038;ax.add_patch(Rectangle((bl,yy),bw,.022,facecolor=WAFER,edgecolor=EDGE,lw=.3))
            for i in range(5):ax.add_patch(Rectangle((bl+.05+i*.1,yy+.022),.012,.016,facecolor='#9a9893',lw=0))

def process_flow(path):
    charts._style();w=6.0;top=.62;hdr=.5;ic=.3;gap=.07
    heights=[sum(item_height(k,l if k!='pair' else '',cw) for k,l in items)+gap*(len(items)-1) for (_,_,_,items),(_,cw) in zip(STAGES,COLS)]
    body=top+hdr+ic+.08;band=.5;nl=textwrap.wrap(NOTES,128);h=body+max(heights)+.16+band+.12+len(nl)*.12+.2
    fig=plt.figure(figsize=(w,h),dpi=200);ax=fig.add_axes([0,0,1,1]);ax.set_xlim(0,w);ax.set_ylim(h,0);ax.axis('off')
    ax.text(.08,.2,'How the HBM tools fit together: from DRAM wafer to 12-high stack',fontsize=10,color=charts.INK,va='center')
    ax.text(.08,.43,'Boxes are the tools this report covers, in process order; grey text marks other steps',fontsize=7.5,color=charts.INK_2,va='center')
    for i,((num,name,where,items),(x,cw)) in enumerate(zip(STAGES,COLS)):
        ax.text(x,top+.12,f'{num}  {name}',fontsize=7.6,fontweight='bold',color=charts.INK,va='center')
        ax.text(x,top+.32,where,fontsize=6.3,color=charts.INK_2,va='center')
        if i<len(STAGES)-1:
            nx=COLS[i+1][0];ax.annotate('',xy=(nx-.05,top+.12+hdr+ic/2),xytext=(x+cw+.03,top+.12+hdr+ic/2),arrowprops=dict(arrowstyle='-|>',color=EDGE,lw=.8,mutation_scale=7))
        icon(ax,num,x,top+hdr,cw-(.16 if num=='1' else 0))
        y=body;bw=cw-(.16 if num=='1' else 0);first=y
        for j,(kind,label) in enumerate(items):
            ih=item_height(kind,label if kind!='pair' else '',bw)
            if kind=='pair':
                hw=(bw-.04)/2
                for k,lab in enumerate(label):
                    ax.add_patch(FancyBboxPatch((x+k*(hw+.04),y),hw,ih,boxstyle='round,pad=0,rounding_size=.03',facecolor=BOX,edgecolor=EDGE,lw=.6))
                    ax.text(x+k*(hw+.04)+hw/2,y+ih/2,lab,fontsize=6.3,color=charts.INK,ha='center',va='center')
            elif kind=='step':
                ax.text(x+bw/2,y+ih/2,'\n'.join(wrap(label,bw-.08)),fontsize=6,style='italic',color=STEP_INK,ha='center',va='center',linespacing=1.15)
            else:
                ax.add_patch(FancyBboxPatch((x,y),bw,ih,boxstyle='round,pad=0,rounding_size=.03',facecolor=FILL if kind=='out' else BOX,
                                            edgecolor=charts.INK if kind=='out' else EDGE,lw=.6,linestyle=(0,(3,2)) if kind=='alt' else '-'))
                ax.text(x+bw/2,y+ih/2,'\n'.join(wrap(label,bw-.08)),fontsize=6.3,color=STEP_INK if kind=='alt' else charts.INK,ha='center',va='center',
                        linespacing=1.15,fontweight='bold' if kind=='out' else 'normal',style='italic' if kind=='alt' else 'normal')
            if j<len(items)-1 and items[j+1][0]!='alt':
                ax.annotate('',xy=(x+bw/2,y+ih+gap-.005),xytext=(x+bw/2,y+ih+.005),arrowprops=dict(arrowstyle='-|>',color=EDGE,lw=.6,mutation_scale=5))
            y+=ih+gap
        if num=='1':
            lx=x+bw+.08;ax.plot([x+bw+.02,lx,lx,x+bw+.02],[y-gap-.1,y-gap-.1,first+.1,first+.1],color=EDGE,lw=.7)
            ax.annotate('',xy=(x+bw+.01,first+.1),xytext=(lx,first+.1),arrowprops=dict(arrowstyle='-|>',color=EDGE,lw=.7,mutation_scale=6))
            ax.text(lx+.05,(first+y-gap)/2,'repeated for each layer',fontsize=5.6,style='italic',color=STEP_INK,rotation=90,ha='center',va='center')
    by=body+max(heights)+.16
    ax.add_patch(FancyBboxPatch((.08,by),w-.16,band,boxstyle='round,pad=0,rounding_size=.04',facecolor=FILL,edgecolor='none'))
    ax.text(.18,by+.13,'Process control underpins every stage',fontsize=7.3,fontweight='bold',color=charts.INK,va='center')
    ax.text(.18,by+.23,'Inspection and metrology of films, patterns and defects in the front end; via depth, voids and copper recess for TSVs;\nbump height, warpage and X-ray checks in packaging',
            fontsize=6.2,color=charts.INK_2,va='top',linespacing=1.3)
    y=by+band+.12
    for line in nl:ax.text(.08,y+.06,line,fontsize=6.6,style='italic',color=charts.INK_2,va='center');y+=.12
    ax.text(.08,y+.1,'Chart: Hamish Low • Source: IAPS, based on process descriptions from SK hynix, Amkor and equipment vendors',fontsize=6.6,color=charts.INK_3,va='center')
    fig.savefig(path,facecolor='#ffffff',dpi=200);plt.close(fig)

def run(atlas, out, preview=None):
    process_flow(out/'process_flow.png')
    manifest.write(out,'hbm_process_flow',[atlas],[],'Diagram drawn from process descriptions in working notes; no Atlas data used.')
    return {'stages':len(STAGES),'tools':sum(1 for *_,items in STAGES for k,_ in items if k in ('tool','pair','alt'))}
